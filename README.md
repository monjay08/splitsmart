# SplitSmart Expense Analyzer

A small app that reads a messy expense CSV, cleans it, and shows who owes whom.

**Live links** (I will fill these after deploying)
- Frontend: add link here
- Backend: add link here

## Tech
Django, Django REST Framework, pandas, React, Tailwind

## Run it locally

Backend
```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py test
python manage.py runserver
```

Frontend (in a second terminal)
```
cd frontend
copy .env.example .env
npm install
npm run dev
```
Then open http://localhost:5173 and upload `backend/sample.csv`.

## API
`POST /api/analyze/` takes a CSV in the form field `file` and returns bad rows, balances, settlements and monthly totals. Money is in paise. A wrong or missing file gives a 400 error with a message.

## How it works
- All logic is in `backend/analyzer/services.py`. The view only takes the upload and calls it.
- Money is kept in paise (whole numbers) so there are no decimal errors.
- If a split leaves an extra paisa, it goes to the person who lost the most in rounding. If tied, alphabetical order.
- To settle up, the person who owes the most pays the person who is owed the most, repeated until everyone is at 0.
- Bad rows show their CSV row number and a reason.

## What I did not finish
- The person filter works on balances, settlements and bad rows, but not on monthly totals.
- Only INR and USD are supported. Any other currency is marked as a bad row.