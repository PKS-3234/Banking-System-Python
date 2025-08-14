# Bank Account Management System (Python + SQLite)

A console-based mini banking system you can build in **one day**. It supports:
- Create Account
- Deposit
- Withdraw
- Transfer (atomic, with double-entry style logs)
- View Transaction History
- Export Transactions to CSV

## Tech Stack
- Python 3.8+
- SQLite (built-in with Python via `sqlite3`)

## Quick Start

```bash
# 1) Create a virtual environment (optional)
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 2) Run the app
python bank_app.py
```

The app creates a local SQLite database file `bank.db` on first run.

## Sample Resume Line
**Bank Account Management System —** Built a console-based banking application with account creation, deposits, withdrawals, transfers, and transaction history using Python and SQLite. Implemented validation, error handling, and atomic DB transactions to simulate real-world banking workflows.

## Files
- `bank_app.py` — main application
- `README.md` — this file
- `.gitignore` — ignore generated files like the DB
