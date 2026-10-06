# SplitSmart Expense Analyzer

Upload a messy expense CSV, clean it, and see who owes whom.

- **Live frontend:** `<add Netlify/Vercel link>`
- **Live backend:** `<add Vercel link>`  (health check: `GET /`)

## Stack
Django + Django REST Framework + pandas (backend), React + Vite + Tailwind (frontend).

## Run locally

Backend:
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py runserver        # http://127.0.0.1:8000
python manage.py test             # run the tests
```

Frontend:
```bash
cd frontend
cp .env.example .env              # VITE_API_URL points to the backend
npm install
npm run dev
```
Upload `backend/sample.csv` to try it.

## API
`POST /api/analyze/` with multipart field `file` returns `summary`, `bad_rows`, `balances`, `settlements`, `monthly_totals`.
All money in the response is in **paise** (integers). Wrong or missing files return `400 {"error": "..."}`.

## How it works
- `analyzer/services.py` holds all logic (parsing, cleaning, splitting, balances, settlement). `views.py` only handles the upload.
- Money is stored as integer paise, so there are no floating point errors. When a split does not divide evenly, the extra paisa goes to the person who lost the most in rounding (ties: alphabetical).
- Settlement: the person who owes the most pays the person owed the most, repeated until everyone is at 0.
- Rules implemented: name normalization, 3 date formats, symbol/comma stripping, USD x 83, blank currency = INR, blank category = Uncategorized, duplicate `expense_id` (later row wins), same person twice in a row is bad, exact/percent sums checked, negative amount = refund.
- Bad row numbers match the CSV file (header is row 1).

## Deploy
- Backend: Vercel, Root Directory = `backend`. Set `SECRET_KEY` env var.
- Frontend: Netlify or Vercel, Root Directory = `frontend`, env `VITE_API_URL` = backend URL.

## Not finished / known limits
- The person filter applies to balances, settlements and bad rows. Monthly totals are for everyone.
- Only INR and USD are supported; any other currency is a bad row by design.
- CORS is open to all origins (fine for this stateless demo).
