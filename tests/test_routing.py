import sqlite3
from langchain_core.messages import HumanMessage
from app.graph.workflow import workflow
from app.tools.crm_db import DB_PATH, init_crm_db


def reset_test_transactions() -> None:
    """Resets UPI-9001 so the instant auto-refund test is repeatable."""
    init_crm_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE transactions SET status = 'FAILED_DEBITED', settlement_status = 'UNSETTLED_AT_BANK' WHERE txn_id = 'UPI-9001'"
    )
    conn.commit()
    conn.close()


TEST_CASES = [
    {
        "name": "1. Tier-1 (RBI Policy RAG)",
        "query": "What is the RBI compensation rule if my failed UPI debit is not reversed on time?",
        "expected_tier": "tier_1_rag",
        "expect_ticket": False,
    },
    {
        "name": "2. Tier-2 (Instant Auto-Refund < ₹2,000)",
        "query": "My UPI-9001 payment to Swiggy failed and money was debited. Please refund it.",
        "expected_tier": "tier_2_crm",
        "expect_ticket": False,
    },
    {
        "name": "3. Tier-2 -> Tier-3 (High-Value >= ₹2,000 Guardrail)",
        "query": "My payment UPI-9003 to Amazon India failed. Please process a refund.",
        "expected_tier": "tier_3_human",
        "expect_ticket": True,
    },
    {
        "name": "4. Tier-3 (Fraud / International Dispute)",
        "query": "Someone stole my card and made an unauthorized payment on CARD-5001 in London!",
        "expected_tier": "tier_3_human",
        "expect_ticket": True,
    },
]


def run_tests() -> None:
    reset_test_transactions()
    passed = 0

    for case in TEST_CASES:
        print(f"\n{'=' * 60}\nRunning: {case['name']}\n{'=' * 60}")
        result = workflow.invoke(
            {
                "messages": [HumanMessage(content=case["query"])],
                "customer_id": "CUST-12345",
            }
        )

        actual_tier = result.get("curr_tier")
        ticket = result.get("escalation_ticket")
        has_ticket = bool(ticket and ticket.get("ticket_id") and ticket.get("token"))

        tier_ok = actual_tier == case["expected_tier"]
        ticket_ok = has_ticket == case["expect_ticket"]
        ok = tier_ok and ticket_ok

        if ok:
            passed += 1

        print(f"Expected Tier: {case['expected_tier']} | Actual: {actual_tier}")
        if has_ticket:
            print(f"Ticket Minted: {ticket['ticket_id']} -> {ticket['review_endpoint']}")
        print(f"Bot Reply:     {result['messages'][-1].content}")
        print(f"Status:        {'PASS' if ok else 'FAIL'}")

    print(f"\n{'=' * 60}\nSummary: {passed}/{len(TEST_CASES)} test cases passed.\n{'=' * 60}")


if __name__ == "__main__":
    run_tests()