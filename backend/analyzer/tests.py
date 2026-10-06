from decimal import Decimal
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from . import services as s

SAMPLE = Path(__file__).resolve().parent.parent / "sample.csv"


def row(**kw):
    base = dict(expense_id="E1", date="2026-01-05", description="x", category="Food", paid_by="Aman",
                amount="100", currency="INR", split_type="equal", participants="Aman;Bhavna", split_values="")
    base.update(kw)
    return base


class ParsingTests(SimpleTestCase):
    def test_three_date_formats_and_invalid_date(self):
        for text in ("2026-01-05", "05/01/2026", "05 Jan 2026"):
            self.assertEqual(s.parse_date(text).isoformat(), "2026-01-05")
        with self.assertRaises(s.RowError):
            s.parse_date("31/02/2026")

    def test_amount_symbols_usd_and_bad_values(self):
        self.assertEqual(s.parse_amount("₹ 12,000", "INR")[1], 1_200_000)
        self.assertEqual(s.parse_amount("$30", "USD")[1], 30 * 83 * 100)
        for bad in ("abc", "0", ""):
            with self.assertRaises(s.RowError):
                s.parse_amount(bad, "INR")

    def test_currency_blank_is_inr_other_is_bad(self):
        self.assertEqual(s.parse_currency(""), "INR")
        with self.assertRaises(s.RowError):
            s.parse_currency("EUR")

    def test_names_are_normalized(self):
        self.assertEqual(s.normalize_name(" bhavna "), "Bhavna")


class CleaningTests(SimpleTestCase):
    def test_blank_category_becomes_uncategorized(self):
        good, bad = s.clean_rows([row(category="")])
        self.assertEqual(good[0]["category"], "Uncategorized")

    def test_duplicate_id_keeps_later_row(self):
        good, bad = s.clean_rows([row(amount="100"), row(amount="200")])
        self.assertEqual(len(good), 1)
        self.assertEqual(good[0]["amount"], 20000)
        self.assertEqual(bad[0]["row"], 2)

    def test_same_person_twice_is_bad(self):
        good, bad = s.clean_rows([row(participants="Aman;aman")])
        self.assertEqual(len(bad), 1)


class SplitTests(SimpleTestCase):
    def test_equal_split_extra_paisa_goes_alphabetically(self):
        shares = s.allocate(100000, {p: s.Fraction(1, 3) for p in ("Chirag", "Aman", "Bhavna")})
        self.assertEqual(shares, {"Aman": 33334, "Bhavna": 33333, "Chirag": 33333})

    def test_percent_extra_paisa_goes_to_biggest_rounding_loss(self):
        # E012: 4000.01 split 33.33 / 33.33 / 33.34 -> Divya loses the most, so she gets the extra paisa
        shares = s.compute_shares("percent", 400001, Decimal("4000.01"), ["Aman", "Bhavna", "Divya"], "33.33;33.33;33.34")
        self.assertEqual(sum(shares.values()), 400001)
        self.assertEqual(shares, {"Aman": 133320, "Bhavna": 133320, "Divya": 133361})

    def test_exact_and_percent_must_add_up(self):
        with self.assertRaises(s.RowError):
            s.compute_shares("exact", 150000, Decimal("1500"), ["A", "B"], "1000;400")
        with self.assertRaises(s.RowError):
            s.compute_shares("percent", 120000, Decimal("1200"), ["A", "B"], "60;30")

    def test_refund_is_negative(self):
        shares = s.compute_shares("equal", -200000, Decimal("-2000"), ["Aman", "Bhavna", "Chirag"], "")
        self.assertEqual(sum(shares.values()), -200000)


class SettleTests(SimpleTestCase):
    def test_settlement_zeroes_everyone(self):
        balances = [
            {"person": "A", "balance": 500}, {"person": "B", "balance": -700},
            {"person": "C", "balance": 300}, {"person": "D", "balance": -100},
        ]
        net = {b["person"]: b["balance"] for b in balances}
        pays = s.settle(balances)
        self.assertEqual(pays[0], {"from": "B", "to": "A", "amount": 500})
        for p in pays:
            net[p["from"]] += p["amount"]
            net[p["to"]] -= p["amount"]
        self.assertTrue(all(v == 0 for v in net.values()))


class EndToEndTests(SimpleTestCase):
    def test_sample_csv(self):
        result = s.analyze_csv(SAMPLE.read_bytes())
        self.assertEqual((result["summary"]["good_rows"], result["summary"]["bad_rows"]), (8, 8))
        self.assertEqual(result["summary"]["total_spend"], 2510001)
        self.assertEqual([b["row"] for b in result["bad_rows"]], [3, 7, 8, 9, 12, 13, 16, 17])
        self.assertEqual(sum(b["balance"] for b in result["balances"]), 0)
        pays = [(p["from"], p["to"], p["amount"]) for p in result["settlements"]]
        self.assertEqual(pays, [("Bhavna", "Aman", 559847), ("Bhavna", "Chirag", 157140), ("Divya", "Chirag", 125944)])

    def test_missing_column_raises(self):
        with self.assertRaises(s.CSVError):
            s.analyze_csv(b"a,b\n1,2\n")


class ApiTests(SimpleTestCase):
    def test_upload_ok(self):
        f = SimpleUploadedFile("sample.csv", SAMPLE.read_bytes(), content_type="text/csv")
        res = self.client.post("/api/analyze/", {"file": f})
        self.assertEqual(res.status_code, 200)
        self.assertIn("settlements", res.json())

    def test_missing_and_wrong_file_give_clear_errors(self):
        self.assertEqual(self.client.post("/api/analyze/", {}).status_code, 400)
        f = SimpleUploadedFile("notes.txt", b"hello")
        res = self.client.post("/api/analyze/", {"file": f})
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.json())
