#!/usr/bin/env python3
"""
Bank Account Management System (CLI)
- Accounts and transactions persisted in SQLite
- Amounts stored as integer paise (cents) to avoid floating-point errors
- Atomic transfers (BEGIN...COMMIT), with two transaction logs (out/in)
"""

import sqlite3
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import secrets
import os
import csv
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "bank.db")

@contextmanager
def db_conn():
    conn = sqlite3.connect(DB_PATH, isolation_level=None)  # autocommit mode; we'll use explicit BEGIN
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        yield conn
    finally:
        conn.close()

def init_db():
    with db_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            account_no TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            balance_paise INTEGER NOT NULL DEFAULT 0,
            opened_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_no TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('DEPOSIT','WITHDRAW','TRANSFER_IN','TRANSFER_OUT')),
            amount_paise INTEGER NOT NULL,
            balance_after_paise INTEGER NOT NULL,
            counterparty_account TEXT,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(account_no) REFERENCES accounts(account_no)
        );
        """)

# ---------- Money helpers ----------

def parse_amount_to_paise(s: str) -> int:
    """Parse a human input like '123.45' into integer paise (e.g., 12345)."""
    s = s.strip().replace(",", "")
    if s.startswith("₹"):
        s = s[1:].strip()
    try:
        d = (Decimal(s)
             .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid amount. Please enter a valid number like 100 or 100.50")
    if d <= 0:
        raise ValueError("Amount must be positive.")
    paise = int((d * 100).to_integral_value(rounding=ROUND_HALF_UP))
    return paise

def paise_to_rupees(paise: int) -> str:
    rupees = Decimal(paise) / Decimal(100)
    return f"₹{rupees:.2f}"

# ---------- Core operations ----------

class InsufficientFunds(Exception):
    pass

def generate_account_no() -> str:
    # 12-digit pseudo-random number (not real banking format)
    return "".join(str(secrets.randbelow(10)) for _ in range(12))

def create_account(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("Name cannot be empty.")
    with db_conn() as conn:
        while True:
            acct = generate_account_no()
            cur = conn.execute("SELECT 1 FROM accounts WHERE account_no = ?", (acct,))
            if cur.fetchone() is None:
                break
        conn.execute("INSERT INTO accounts(account_no, name) VALUES (?, ?)", (acct, name))
    return acct

def get_account(conn, account_no: str):
    cur = conn.execute("SELECT account_no, name, balance_paise, opened_at FROM accounts WHERE account_no = ?", (account_no,))
    return cur.fetchone()

def deposit(account_no: str, amount_paise: int, note: str | None = None):
    with db_conn() as conn:
        conn.execute("BEGIN IMMEDIATE;")
        try:
            acc = get_account(conn, account_no)
            if not acc:
                raise ValueError("Account not found.")
            new_bal = acc[2] + amount_paise
            conn.execute("UPDATE accounts SET balance_paise = ? WHERE account_no = ?", (new_bal, account_no))
            conn.execute("""
                INSERT INTO transactions(account_no, type, amount_paise, balance_after_paise, note)
                VALUES(?, 'DEPOSIT', ?, ?, ?)
            """, (account_no, amount_paise, new_bal, note))
            conn.execute("COMMIT;")
            return new_bal
        except Exception:
            conn.execute("ROLLBACK;")
            raise

def withdraw(account_no: str, amount_paise: int, note: str | None = None):
    with db_conn() as conn:
        conn.execute("BEGIN IMMEDIATE;")
        try:
            acc = get_account(conn, account_no)
            if not acc:
                raise ValueError("Account not found.")
            if acc[2] < amount_paise:
                raise InsufficientFunds("Insufficient balance.")
            new_bal = acc[2] - amount_paise
            conn.execute("UPDATE accounts SET balance_paise = ? WHERE account_no = ?", (new_bal, account_no))
            conn.execute("""
                INSERT INTO transactions(account_no, type, amount_paise, balance_after_paise, note)
                VALUES(?, 'WITHDRAW', ?, ?, ?)
            """, (account_no, amount_paise, new_bal, note))
            conn.execute("COMMIT;")
            return new_bal
        except Exception:
            conn.execute("ROLLBACK;")
            raise

def transfer(from_acct: str, to_acct: str, amount_paise: int, note: str | None = None):
    if from_acct == to_acct:
        raise ValueError("Cannot transfer to the same account.")
    with db_conn() as conn:
        conn.execute("BEGIN IMMEDIATE;")
        try:
            a = get_account(conn, from_acct)
            b = get_account(conn, to_acct)
            if not a or not b:
                raise ValueError("One or both accounts not found.")
            if a[2] < amount_paise:
                raise InsufficientFunds("Insufficient balance for transfer.")

            new_a = a[2] - amount_paise
            new_b = b[2] + amount_paise

            conn.execute("UPDATE accounts SET balance_paise = ? WHERE account_no = ?", (new_a, from_acct))
            conn.execute("UPDATE accounts SET balance_paise = ? WHERE account_no = ?", (new_b, to_acct))

            # Log both sides of the transfer
            conn.execute("""
                INSERT INTO transactions(account_no, type, amount_paise, balance_after_paise, counterparty_account, note)
                VALUES(?, 'TRANSFER_OUT', ?, ?, ?, ?)
            """, (from_acct, amount_paise, new_a, to_acct, note))
            conn.execute("""
                INSERT INTO transactions(account_no, type, amount_paise, balance_after_paise, counterparty_account, note)
                VALUES(?, 'TRANSFER_IN',  ?, ?, ?, ?)
            """, (to_acct, amount_paise, new_b, from_acct, note))

            conn.execute("COMMIT;")
            return new_a, new_b
        except Exception:
            conn.execute("ROLLBACK;")
            raise

def fetch_transactions(account_no: str, limit: int = 20):
    with db_conn() as conn:
        cur = conn.execute("""
            SELECT id, type, amount_paise, balance_after_paise, counterparty_account, note, created_at
            FROM transactions
            WHERE account_no = ?
            ORDER BY id DESC
            LIMIT ?
        """, (account_no, limit))
        return cur.fetchall()

from datetime import datetime

from datetime import datetime

def export_transactions_csv(account_no: str, out_path: str):
    rows = fetch_transactions(account_no, limit=1000000)
    headers = ["id", "type", "amount", "balance_after", "counterparty_account", "note", "created_at"]

    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            created_at = r[6]
            try:
                # Try converting to datetime for consistent formatting
                created_at_dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                created_at = created_at_dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                # If it's already a string or invalid, just keep it as-is
                pass

            w.writerow([
                r[0],
                r[1],
                paise_to_rupees(r[2]),
                paise_to_rupees(r[3]),
                str(r[4]) if r[4] else "",
                r[5] or "",
                created_at
            ])
    return out_path



# ---------- CLI ----------

def print_header():
    print("=" * 68)
    print("      BANK ACCOUNT MANAGEMENT SYSTEM".center(68))
    print("=" * 68)

def menu():
    print("\nChoose an option:")
    print(" 1) Create Account")
    print(" 2) Deposit")
    print(" 3) Withdraw")
    print(" 4) Transfer")
    print(" 5) View Transactions")
    print(" 6) Export Transactions to CSV")
    print(" 0) Exit")

def prompt(msg):
    return input(msg).strip()

def main():
    init_db()
    print_header()
    while True:
        try:
            menu()
            choice = prompt("Enter choice: ")
            if choice == "1":
                name = prompt("Enter account holder name: ")
                acct = create_account(name)
                print(f"✅ Account created. Account No: {acct}")
            elif choice == "2":
                acct = prompt("Enter account no: ")
                amt = parse_amount_to_paise(prompt("Enter amount (e.g., 100 or 100.50): "))
                note = prompt("Optional note: ")
                new_bal = deposit(acct, amt, note or None)
                print(f"✅ Deposited {paise_to_rupees(amt)}. New Balance: {paise_to_rupees(new_bal)}")
            elif choice == "3":
                acct = prompt("Enter account no: ")
                amt = parse_amount_to_paise(prompt("Enter amount (e.g., 100 or 100.50): "))
                note = prompt("Optional note: ")
                try:
                    new_bal = withdraw(acct, amt, note or None)
                    print(f"✅ Withdrew {paise_to_rupees(amt)}. New Balance: {paise_to_rupees(new_bal)}")
                except InsufficientFunds as e:
                    print(f"❌ {e}")
            elif choice == "4":
                from_acct = prompt("From account no: ")
                to_acct = prompt("To account no: ")
                amt = parse_amount_to_paise(prompt("Enter amount (e.g., 100 or 100.50): "))
                note = prompt("Optional note: ")
                try:
                    new_a, new_b = transfer(from_acct, to_acct, amt, note or None)
                    print(f"✅ Transferred {paise_to_rupees(amt)} from {from_acct} to {to_acct}.")
                    print(f"   New Balance (From): {paise_to_rupees(new_a)}")
                    print(f"   New Balance (To)  : {paise_to_rupees(new_b)}")
                except InsufficientFunds as e:
                    print(f"❌ {e}")
            elif choice == "5":
                acct = prompt("Enter account no: ")
                limit_raw = prompt("How many recent transactions? (default 20): ").strip()
                limit = int(limit_raw) if limit_raw.isdigit() else 20
                rows = fetch_transactions(acct, limit=limit)
                if not rows:
                    print("No transactions found.")
                else:
                    print("\nRecent Transactions:")
                    print("-" * 68)
                    for r in rows:
                        t_id, t_type, amt_p, bal_p, cp, note, ts = r
                        amt = paise_to_rupees(amt_p)
                        bal = paise_to_rupees(bal_p)
                        cp_str = f" | With: {cp}" if cp else ""
                        note_str = f" | Note: {note}" if note else ""
                        print(f"[{t_id}] {ts} | {t_type:<12} | {amt:<10} | Bal: {bal}{cp_str}{note_str}")
                    print("-" * 68)
            elif choice == "6":
                acct = prompt("Enter account no: ")
                filename = f"transactions_{acct}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                out_path = os.path.join(os.path.dirname(__file__), filename)
                try:
                    export_transactions_csv(acct, out_path)
                    print(f"✅ Exported to {out_path}")
                except Exception as e:
                    print(f"❌ Failed to export: {e}")
            elif choice == "0":
                print("Goodbye!")
                break
            else:
                print("Please enter a valid choice (0-6).")
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
