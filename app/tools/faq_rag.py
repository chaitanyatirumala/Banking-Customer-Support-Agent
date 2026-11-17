from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import FAISS

import os

# Path where FAISS saves the vector database on your disk
FAISS_PATH = "faiss_index"

# Initialize local Llama 3.1 embeddings once
embeddings = OllamaEmbeddings(model="nomic-embed-text:latest")

# Default company rulebook for Tier-1 FAQ support
DEFAULT_RULEBOOK = [
    "RBI UPI Auto-Reversal Rule: If a UPI transaction fails but money is debited (Failed/Debited), the bank must auto-reverse the amount within T+1 business days. Failing this, the bank must pay the customer ₹100 per day as compensation.",
    "Instant Auto-Refund Policy: Verified failed UPI transactions or duplicate merchant charges under ₹2,000 are eligible for instant automated reversal to the source bank account.",
    "High-Value & Fraud Escalation Rule: Any transaction dispute above ₹2,000, international card transactions, or suspected unauthorized fraud cannot be auto-refunded and must be escalated to a Risk & Compliance Officer for review within 24 hours.",
    "Card Chargeback Policy: Domestic debit and credit card duplicate debits or unfulfilled merchant payments can be disputed within 60 days of the transaction date under NPCI/Card Network chargeback guidelines."
]

def store_rulebook(rules: list[str]) -> None:
    """
    Embeds and stores the RBI/NPCI payment rules into the local FAISS index.
    """
    # 1. If the database already exists, append the new rules to it
    if os.path.exists(FAISS_PATH):
        print("[FAISS] Adding new rules to existing vector store...")
        vector_db = FAISS.load_local(
            FAISS_PATH, 
            embeddings, 
            allow_dangerous_deserialization=True
        )
        vector_db.add_texts(rules)
    
    # 2. If no database exists yet, create a brand new one from the rulebook
    else:
        print("[FAISS] Creating new vector store from rulebook...")
        vector_db = FAISS.from_texts(rules, embeddings)

    # 3. Save the updated index back to disk
    vector_db.save_local(FAISS_PATH)
    print(f"[FAISS] Rulebook successfully stored in '{FAISS_PATH}/'")


def retrieve_faq(query: str, k: int = 2) -> str:
    """
    Searches the stored FAISS database for the top-k rules matching the customer's query.
    """
    # Safety check: If no rulebook has been stored yet, store the default one automatically
    if not os.path.exists(FAISS_PATH):
        store_rulebook(DEFAULT_RULEBOOK)

    # Load the stored database and search for the closest matching rules
    vector_db = FAISS.load_local(
        FAISS_PATH, 
        embeddings, 
        allow_dangerous_deserialization=True
    )
    docs = vector_db.similarity_search(query, k=k)
    
    return "\n".join([doc.page_content for doc in docs])