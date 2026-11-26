import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv

# Load secrets from .env file into environment variables
load_dotenv()

DB_PATH = "fintech_disputes.db"
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "fintech-dispute-agent"
JWT_AUDIENCE = "compliance-review-portal"
REQUIRED_SCOPE = "compliance:review"
REVIEW_WINDOW_HOURS = 24
MIN_SECRET_LENGTH = 32  # Minimum 256-bit key strength for HS256


def _get_jwt_secret() -> str:
    """Fail-fast secret loader: refuses to run with missing or weak keys."""
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret or len(secret) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"SECURITY ERROR: JWT_SECRET_KEY must be set in .env and be at least "
            f"{MIN_SECRET_LENGTH} characters long. Generate one with: "
            "python -c 'import secrets; print(secrets.token_hex(32))'"
        )
    return secret


def _get_secure_base_url() -> str:
    """Enforces HTTPS for all non-local environments."""
    base_url = os.getenv("APP_BASE_URL", "https://compliance.yourbank.internal").rstrip("/")
    app_env = os.getenv("APP_ENV", "production").lower()

    is_local_dev = app_env == "development" and base_url.startswith(
        ("http://localhost", "http://127.0.0.1")
    )
    if not base_url.startswith("https://") and not is_local_dev:
        raise RuntimeError(
            f"SECURITY ERROR: APP_BASE_URL ('{base_url}') must use HTTPS outside local development."
        )
    return base_url


def init_escalation_db() -> None:
    """Creates the server-side table that stores sensitive dispute PII safely away from the JWT."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS escalation_tickets (
            ticket_id TEXT PRIMARY KEY,
            jti TEXT UNIQUE NOT NULL,
            customer_id TEXT NOT NULL,
            escalation_reason TEXT NOT NULL,
            audit_summary TEXT NOT NULL,
            transcript_json TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def create_escalation_token(
    customer_id: str,
    escalation_reason: str,
    audit_summary: str,
    conversation_transcript: list[str],
) -> dict:
    """
    Stores sensitive dispute details in SQLite and mints a zero-PII JWT reference token
    valid for 24 hours.
    """
    secret_key = _get_jwt_secret()
    base_url = _get_secure_base_url()
    init_escalation_db()

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=REVIEW_WINDOW_HOURS)
    ticket_id = f"ESC-{uuid.uuid4().hex[:8].upper()}"
    jti = uuid.uuid4().hex  # Unique Token ID for replay protection & revocation

    # 1. Persist sensitive PII strictly on the server (never inside the JWT)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO escalation_tickets
           (ticket_id, jti, customer_id, escalation_reason, audit_summary,
            transcript_json, status, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ticket_id,
            jti,
            customer_id,
            escalation_reason,
            audit_summary,
            json.dumps(conversation_transcript),
            "PENDING_REVIEW",
            now.isoformat(),
            expires_at.isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    # 2. Mint a minimal, zero-PII JWT reference token
    payload = {
        "sub": ticket_id,           # Opaque ticket reference only
        "jti": jti,                 # Prevents replay after resolution
        "iss": JWT_ISSUER,          # Who issued the token
        "aud": JWT_AUDIENCE,        # Which service is allowed to accept it
        "scope": REQUIRED_SCOPE,    # Least-privilege permission scope
        "iat": now,
        "exp": expires_at,
    }

    token = jwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM)

    # 3. Return clean HTTPS endpoint (token must be sent via Authorization: Bearer header, NOT in URL)
    return {
        "ticket_id": ticket_id,
        "token": token,
        "expires_at": expires_at.isoformat(),
        "review_endpoint": f"{base_url}/api/v1/compliance/tickets/{ticket_id}",
        "auth_header_hint": "Pass token in HTTP header -> Authorization: Bearer <token>",
    }


def verify_escalation_token(token: str) -> dict:
    """
    Verifies the JWT signature, claims, and 24-hour expiry, then fetches the
    sensitive dispute record from SQLite only if the ticket is still pending.
    """
    secret_key = _get_jwt_secret()
    init_escalation_db()

    try:
        claims = jwt.decode(
            token,
            secret_key,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"require": ["sub", "jti", "iss", "aud", "exp", "iat", "scope"]},
        )
    except jwt.ExpiredSignatureError:
        return {"valid": False, "error": "Escalation token expired (24-hour SLA window passed)."}
    except jwt.InvalidTokenError as exc:
        return {"valid": False, "error": f"Invalid or tampered token: {exc}"}

    if claims.get("scope") != REQUIRED_SCOPE:
        return {"valid": False, "error": "Token lacks required compliance review scope."}

    ticket_id = claims["sub"]
    jti = claims["jti"]

    # Fetch the actual dispute record from server-side DB and verify status + jti
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT customer_id, escalation_reason, audit_summary, transcript_json, status, expires_at
           FROM escalation_tickets WHERE ticket_id = ? AND jti = ?""",
        (ticket_id, jti),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"valid": False, "error": "Ticket not found or token ID has been revoked."}

    if row[4] != "PENDING_REVIEW":
        return {"valid": False, "error": f"Replay blocked: ticket already closed ({row[4]})."}

    return {
        "valid": True,
        "data": {
            "ticket_id": ticket_id,
            "customer_id": row[0],
            "escalation_reason": row[1],
            "audit_summary": row[2],
            "transcript": json.loads(row[3]),
            "status": row[4],
            "expires_at": row[5],
        },
    }


def mark_ticket_resolved(ticket_id: str, decision: str) -> bool:
    """Marks a ticket RESOLVED so its JWT can never be replayed again."""
    init_escalation_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE escalation_tickets SET status = ? WHERE ticket_id = ? AND status = 'PENDING_REVIEW'",
        (decision, ticket_id),
    )
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated