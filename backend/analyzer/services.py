
import io
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from fractions import Fraction
from math import floor

import pandas as pd

REQUIRED_COLUMNS = [
    "expense_id", "date", "description", "category", "paid_by",
    "amount", "currency", "split_type", "participants", "split_values",
]
USD_TO_INR = 83
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d %b %Y")
SPLIT_TYPES = ("equal", "exact", "percent")


class CSVError(ValueError):
   


class RowError(ValueError):
    


# ---------- small parsers ----------

def normalize_name(raw):
    return " ".join(str(raw).split()).title()


def parse_date(raw):
    text = str(raw).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise RowError(f"Invalid date '{text}'")


def parse_currency(raw):
    code = str(raw).strip().upper()
    if code == "":
        return "INR"
    if code in ("INR", "USD"):
        return code
    raise RowError(f"Unsupported currency '{str(raw).strip()}'")


def parse_decimal(raw, what="Amount"):
    cleaned = re.sub(r"[₹$,\s]|rs\.?", "", str(raw), flags=re.I)
    if not re.fullmatch(r"-?\d+(\.\d+)?", cleaned):
        raise RowError(f"{what} '{str(raw).strip()}' is not a number")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise RowError(f"{what} '{str(raw).strip()}' is not a number")


def parse_amount(raw, currency):
    """Return (value in original currency as Decimal, total in paise as int)."""
    value = parse_decimal(raw)
    if value == 0:
        raise RowError("Amount is zero")
    rate = USD_TO_INR if currency == "USD" else 1
    paise = int((value * 100 * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if paise == 0:
        raise RowError("Amount is too small")
    return value, paise


def parse_participants(raw):
    names = [normalize_name(p) for p in str(raw).split(";") if p.strip()]
    if not names:
        raise RowError("No participants")
    if len(set(names)) != len(names):
        raise RowError("Same person listed twice in participants")
    return names


# ---------- split logic ----------

def allocate(total_paise, weights):
    """Split total_paise by weights {name: Fraction (sum = 1)} into whole paise.

    Everyone gets the rounded-down share; leftover paise go one each to the people
    who lost the most in rounding (ties: alphabetical order). Sum is always exact.
    """
    sign = -1 if total_paise < 0 else 1
    total = abs(total_paise)
    exact = {name: Fraction(total) * w for name, w in weights.items()}
    shares = {name: floor(x) for name, x in exact.items()}
    leftover = total - sum(shares.values())
    order = sorted(exact, key=lambda n: (-(exact[n] - shares[n]), n))
    for name in order[:leftover]:
        shares[name] += 1
    return {name: sign * v for name, v in shares.items()}


def compute_shares(split_type, total_paise, amount_value, participants, raw_values):
    """Return {person: paise owed}. Raises RowError for invalid split data."""
    if split_type == "equal":
        weights = {p: Fraction(1, len(participants)) for p in participants}
        return allocate(total_paise, weights)

    parts = [v for v in str(raw_values).split(";")]
    if len(parts) != len(participants) or any(not v.strip() for v in parts):
        raise RowError("split_values count does not match participants")
    values = [parse_decimal(v, "Split value") for v in parts]

    if split_type == "percent":
        if any(v < 0 for v in values):
            raise RowError("Percent values cannot be negative")
        if sum(values) != 100:
            raise RowError(f"Percent values add up to {sum(values).normalize():f}, not 100")
        weights = {p: Fraction(v) / 100 for p, v in zip(participants, values)}
    else:  # exact
        if sum(values) != amount_value:
            raise RowError(f"Exact values add up to {sum(values).normalize():f}, not the total {amount_value.normalize():f}")
        if any(v * amount_value < 0 for v in values):
            raise RowError("Exact values have the wrong sign")
        weights = {p: Fraction(v) / Fraction(amount_value) for p, v in zip(participants, values)}
    return allocate(total_paise, weights)


# ---------- cleaning ----------

def clean_row(row):
    """Validate one row (dict of strings). Returns a clean expense dict or raises RowError."""
    paid_by = normalize_name(row["paid_by"])
    if not paid_by:
        raise RowError("Missing paid_by")
    split_type = str(row["split_type"]).strip().lower()
    if split_type not in SPLIT_TYPES:
        raise RowError(f"Unknown split_type '{row['split_type']}'")

    day = parse_date(row["date"])
    currency = parse_currency(row["currency"])
    amount_value, total = parse_amount(row["amount"], currency)
    participants = parse_participants(row["participants"])
    shares = compute_shares(split_type, total, amount_value, participants, row["split_values"])
    category = str(row["category"]).strip().title() or "Uncategorized"

    return {
        "expense_id": str(row["expense_id"]).strip(),
        "date": day.isoformat(),
        "month": day.strftime("%Y-%m"),
        "description": str(row["description"]).strip(),
        "category": category,
        "paid_by": paid_by,
        "amount": total,
        "currency": currency,
        "split_type": split_type,
        "shares": shares,
    }


def clean_rows(records):
    """records: list of dict rows. Returns (good_expenses, bad_rows).

    Row numbers match the CSV file (header is row 1).
    """
    last_seen = {}
    for idx, rec in enumerate(records):
        eid = str(rec["expense_id"]).strip()
        if eid:
            last_seen[eid] = idx

    good, bad = [], []
    for idx, rec in enumerate(records):
        row_no = idx + 2
        eid = str(rec["expense_id"]).strip()
        try:
            if not eid:
                raise RowError("Missing expense_id")
            if last_seen[eid] != idx:
                raise RowError(f"Duplicate expense_id '{eid}': replaced by a later row (row {last_seen[eid] + 2})")
            good.append(clean_row(rec))
        except RowError as exc:
            bad.append({"row": row_no, "expense_id": eid, "reason": str(exc), "raw": dict(rec)})
    return good, bad


# ---------- balances, settlement, totals ----------

def compute_balances(expenses):
    paid, owed = defaultdict(int), defaultdict(int)
    for e in expenses:
        paid[e["paid_by"]] += e["amount"]
        for person, share in e["shares"].items():
            owed[person] += share
    people = sorted(set(paid) | set(owed))
    rows = [{"person": p, "paid": paid[p], "owed": owed[p], "balance": paid[p] - owed[p]} for p in people]
    assert sum(r["balance"] for r in rows) == 0, "balances must add up to 0"
    return rows


def settle(balances):
    """Biggest debtor pays biggest creditor until everyone is at 0."""
    debts = {r["person"]: -r["balance"] for r in balances if r["balance"] < 0}
    credits = {r["person"]: r["balance"] for r in balances if r["balance"] > 0}
    payments = []
    while debts and credits:
        debtor = sorted(debts, key=lambda p: (-debts[p], p))[0]
        creditor = sorted(credits, key=lambda p: (-credits[p], p))[0]
        amount = min(debts[debtor], credits[creditor])
        payments.append({"from": debtor, "to": creditor, "amount": amount})
        debts[debtor] -= amount
        credits[creditor] -= amount
        if debts[debtor] == 0:
            del debts[debtor]
        if credits[creditor] == 0:
            del credits[creditor]
    return payments


def monthly_totals(expenses):
    totals = defaultdict(int)
    for e in expenses:
        totals[(e["month"], e["category"])] += e["amount"]
    return [{"month": m, "category": c, "total": t} for (m, c), t in sorted(totals.items())]


# ---------- entry point ----------

def read_csv_bytes(data):
    try:
        df = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False, encoding="utf-8-sig", skipinitialspace=True)
    except pd.errors.EmptyDataError:
        raise CSVError("The file is empty.")
    except (pd.errors.ParserError, UnicodeDecodeError):
        raise CSVError("This does not look like a valid CSV file.")
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise CSVError("Missing required column(s): " + ", ".join(missing))
    if df.empty:
        raise CSVError("The file has no data rows.")
    return df[REQUIRED_COLUMNS].fillna("").to_dict("records")


def analyze_csv(data):
    records = read_csv_bytes(data)
    good, bad = clean_rows(records)
    balances = compute_balances(good)
    return {
        "summary": {
            "total_rows": len(records),
            "good_rows": len(good),
            "bad_rows": len(bad),
            "total_spend": sum(e["amount"] for e in good),
        },
        "bad_rows": bad,
        "balances": balances,
        "settlements": settle(balances),
        "monthly_totals": monthly_totals(good),
    }
