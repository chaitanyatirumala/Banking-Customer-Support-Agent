import os
import uuid
from datetime import datetime, timedelta, timezone
import jwt

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-fintech-dispute-secret-key-2026")
JWT_ALGORITHM = "HS256"
REVIEW_WINDOW_HOURS = 24

def create_escalation_token(
        customer_id : str,
        escalation_reason : str,
        audit_summary : str,
        conversation_history : list[str],
) -> dict:
    """
    Wraps a Tier-3 dispute case into a tamper-proof JWT valid for 24 hours
    for asynchronous Risk & Compliance Officer review.
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=REVIEW_WINDOW_HOURS)
    ticket_id = f"ESC-{uuid.uuid4().hex[:8].upper()}"
    
    
    payload = {
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "escalation_reason": escalation_reason,
        "audit_summary": audit_summary,
        "transcript": conversation_history,
        "iat": now,          # Standard JWT claim: Issued At
        "exp": expires_at,   # Standard JWT claim: Expires At (auto-enforced 24hr window)
    }

    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return {
        "ticket_id": ticket_id,
        "expires_at": expires_at.isoformat(),
        'token' : token,
        "review_url" :f"http://localhost:8000/compliance/review?token={token}",
    }

def verify_escalation_token(token: str) -> dict:
    """
    Decodes and verifies an escalation JWT when the human compliance officer opens it.
    Automatically rejects tampered tokens or tokens older than 24 hours.
    """
    try:
        decoded_payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
        return {"valid": True, "data": decoded_payload}
    except jwt.ExpiredSignatureError:
        return {"valid": False, "error": "Escalation token has expired (24-hour SLA window passed)."}
    except jwt.InvalidTokenError:
        return {"valid": False, "error": "Invalid or tampered escalation token."}