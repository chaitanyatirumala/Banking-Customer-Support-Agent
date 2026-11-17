import sqlite3
from langchain_core.tools import tool

DB_PATH = "crm_database.db"

def init_crm_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    ## Table CREATION
    # TABLE- 1 : Customer Details
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS Customers(
            Customer_ID TEXT PRIMARY KEY,
            name TEXT,
            email TEXT,
            account_status TEXT,
            open_complaints INTEGER)
"""
    )

    # TABLE- 2 : Order Details 
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS Orders(
            Order_ID TEXT PRIMARY KEY,
            Customer_ID TEXT,
            item_name TEXT,
            status TEXT,
            amount REAL) 
"""
 ) 
    # Synthetic CRM Data for testing
    cursor.executemany(
        "INSERT OR IGNORE INTO customers VALUES (?, ?, ?, ?, ?)",
        [
            ("CUST-12345", "Aarav Sharma", "aarav@example.com", "Active", 0),
            ("CUST-67890", "Priya Patel", "priya@example.com", "Locked", 2),
        ]
    )

    cursor.executemany(
        "INSERT OR IGNORE INTO orders VALUES (?, ?, ?, ?, ?)",
        [
            ("ORD-101", "CUST-12345", "Wireless Headphones", "Delayed in Transit", 89.99),
            ("ORD-102", "CUST-12345", "Mechanical Keyboard", "Delivered", 120.00),
            ("ORD-201", "CUST-67890", "Gaming Mouse", "Delivered", 45.50),
        ]
    )

    conn.commit()
    conn.close()


# Tool to fetch Customer account details
@tool
def get_customer_account(customer_id:str) -> str:
    """"Look up a customer's account status ,email, and open_complaints by customer_id"""
    init_crm_db() 
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, email, account_status, open_complaints FROM Customers WHERE Customer_ID = ?",(customer_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return f"no customer found with ID:{customer_id}."
    return f"Customer_name:{row[0]} | Email:{row[1]} | Account_status:{row[2]} | Open_complaints:{row[3]}"

@tool
def get_order_status(order_id: str) -> str:
    """Check the current delivery status and price of an order using its order_id (e.g., ORD-101)."""
    init_crm_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT item_name, status, amount FROM orders WHERE order_id = ?",
        (order_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return f"Order {order_id} was not found in the CRM."
    return f"Order {order_id}: Item='{row[0]}', Status='{row[1]}', Amount=${row[2]}"


@tool
def initiate_refund(order_id: str, reason: str) -> str:
    """Initiate a refund for a specific order_id and record the reason."""
    init_crm_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT status FROM orders WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return f"Cannot refund: Order {order_id} does not exist."

    cursor.execute(
        "UPDATE orders SET status = ? WHERE order_id = ?",
        (f"Refund Initiated ({reason})", order_id)
    )
    conn.commit()
    conn.close()
    return f"Success: Refund initiated for order {order_id}. Reason logged: '{reason}'."


# Export all tools in a single list for the Tier-2 Agent
CRM_TOOLS = [get_customer_account, get_order_status, initiate_refund]