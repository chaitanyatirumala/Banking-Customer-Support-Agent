import sqlite3
from langchain_core.tools import tool
from typing import Literal

DisputeReason = Literal[
    "FAILED_DEBIT",
    "DUPLICATE_CHARGE",
    "UNAUTHORIZED_FRAUD",
    "MERCHANT_ISSUE"
]

DB_PATH = "fintech_disputes.db"
AUTO_REFUND_LIMIT = 2000.0  # Deterministic guardrail: refunds >= ₹2,000 require Tier-3 review


def init_crm_db() -> None:
    """Creates the UPI & Card transactions table and seeds mock Indian fintech records."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            txn_id TEXT PRIMARY KEY,
            customer_id TEXT,
            payment_method TEXT,
            merchant TEXT,
            amount REAL,
            status TEXT,
            settlement_status TEXT,
            is_international INTEGER
        )
    """)

    # Seed realistic UPI & Card dispute test cases
    cursor.executemany(
        "INSERT OR IGNORE INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            # Case 1: Failed UPI under ₹2,000 -> Eligible for instant auto-refund
            ("UPI-9001", "CUST-12345", "UPI", "Swiggy", 450.00, "FAILED_DEBITED", "UNSETTLED_AT_BANK", 0),
            # Case 2: Duplicate UPI debit under ₹2,000 -> Eligible for instant auto-refund
            ("UPI-9002", "CUST-12345", "UPI", "Zomato", 1250.00, "DUPLICATE_DEBIT", "UNSETTLED_AT_BANK", 0),
            # Case 3: Failed UPI above ₹2,000 -> Must escalate to Tier-3 (JWT)
            ("UPI-9003", "CUST-12345", "UPI", "Amazon India", 4500.00, "FAILED_DEBITED", "UNSETTLED_AT_BANK", 0),
            # Case 4: International card + suspected fraud -> Must escalate to Tier-3 (JWT)
            ("CARD-5001", "CUST-12345", "Credit Card", "Apple Store UK", 15000.00, "SUSPECTED_FRAUD", "PENDING_INTERNATIONAL", 1),
            # Case 5: Valid completed payment -> Already settled with merchant (no auto-refund)
            ("UPI-9004", "CUST-12345", "UPI", "Uber India", 320.00, "SUCCESS", "SETTLED_TO_MERCHANT", 0),
        ]
    )

    conn.commit()
    conn.close()


@tool
def list_customer_transactions(customer_id: str) -> str:
    """List recent UPI and Card transactions for a given customer_id when the user does not mention a txn_id."""
    init_crm_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT txn_id, payment_method, merchant, amount, status FROM transactions WHERE customer_id = ?",
        (customer_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return f"No transactions found for customer {customer_id}."

    lines = [
        f"- {r[0]} | {r[1]} | {r[2]} | ₹{r[3]:.2f} | Status: {r[4]}"
        for r in rows
    ]
    return "Recent Transactions:\n" + "\n".join(lines)


@tool
def check_transaction_status(txn_id: str) -> str:
    """Verify a UPI or Card transaction's status, amount, and merchant settlement status using its txn_id (e.g., UPI-9001)."""
    init_crm_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """SELECT payment_method, merchant, amount, status, settlement_status, is_international
           FROM transactions WHERE txn_id = ?""",
        (txn_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return f"Transaction {txn_id} was not found in bank records."

    region = "International" if row[5] == 1 else "Domestic"
    return (
        f"Transaction {txn_id}: Method={row[0]} ({region}), Merchant={row[1]}, "
        f"Amount=₹{row[2]:.2f}, Status={row[3]}, Settlement={row[4]}"
    )


@tool
@tool
def process_instant_refund(txn_id: str, reason_code: DisputeReason) -> str:
    """
    Attempt an instant automated refund for a failed or duplicate UPI/Card transaction.
    Choose the exact reason_code that best matches the customer's complaint.
    """
    init_crm_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT amount, status, settlement_status, is_international FROM transactions WHERE txn_id = ?",
        (txn_id,)
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        return f"Refund denied: Transaction {txn_id} does not exist."

    amount, status, settlement_status, is_international = row

    # Guardrail 1: Idempotency check
    if status == "AUTO_REFUNDED":
        conn.close()
        return f"Transaction {txn_id} (₹{amount:.2f}) has already been refunded."

    # Guardrail 2: Bank-flagged OR Customer-reported Fraud / International -> Tier-3
    if is_international == 1 or status == "SUSPECTED_FRAUD" or reason_code == "UNAUTHORIZED_FRAUD":
        conn.close()
        return (
            f"ESCALATE_TIER_3: Transaction {txn_id} (₹{amount:.2f}) flagged under "
            f"{reason_code} / {'International' if is_international else status}. "
            "Requires Risk & Compliance Officer review."
        )

    # Guardrail 3: High-Value Limit (>= ₹2,000) -> Tier-3
    if amount >= AUTO_REFUND_LIMIT:
        conn.close()
        return (
            f"ESCALATE_TIER_3: Transaction {txn_id} amount (₹{amount:.2f}) exceeds the "
            f"instant auto-refund limit (under ₹{AUTO_REFUND_LIMIT:.0f}). "
            "Requires Risk & Compliance Officer review."
        )

    # Guardrail 4: Only Failed/Debited or Duplicate transactions qualify for auto-credit
    if status not in ("FAILED_DEBITED", "DUPLICATE_DEBIT"):
        conn.close()
        return (
            f"Auto-refund not eligible for {txn_id}: Current status is '{status}' "
            f"and settlement is '{settlement_status}'. Customer must raise a merchant chargeback."
        )

    # Passed all checks -> Execute instant refund
    cursor.execute(
        "UPDATE transactions SET status = ?, settlement_status = ? WHERE txn_id = ?",
        ("AUTO_REFUNDED", "CREDITED_TO_SOURCE", txn_id)
    )
    conn.commit()
    conn.close()

    return (
        f"SUCCESS: Instant auto-refund of ₹{amount:.2f} credited for {txn_id}. "
        f"Dispute code logged: '{reason_code}'."
    )

# Export all tools for the Tier-2 Agent
CRM_TOOLS = [list_customer_transactions, check_transaction_status, process_instant_refund]