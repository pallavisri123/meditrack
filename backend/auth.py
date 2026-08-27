"""
Authentication helpers for MediTrack.

- Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib `hashlib`, no extra
  dependency / no native build step required) using a random salt per user.
- Sessions are stateless JSON Web Tokens (JWT) signed with HS256 via PyJWT.
- Reset tokens for the forgot-password flow are random, single-use, stored
  only as a hash in the database, and expire after RESET_TOKEN_TTL_MINUTES.
"""
import os
import hmac
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session

from database import get_db
import models as M

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
# In production, set JWT_SECRET_KEY as an environment variable. A random
# fallback is generated per-process so the app still runs out of the box in
# a demo/dev environment (tokens simply won't survive a server restart).
SECRET_KEY = os.getenv("JWT_SECRET_KEY") or secrets.token_hex(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_MINUTES = int(os.getenv("ACCESS_TOKEN_TTL_MINUTES", "60"))
REMEMBER_ME_TTL_DAYS = int(os.getenv("REMEMBER_ME_TTL_DAYS", "30"))
RESET_TOKEN_TTL_MINUTES = int(os.getenv("RESET_TOKEN_TTL_MINUTES", "30"))

PBKDF2_ITERATIONS = 260_000


# --------------------------------------------------------------------------
# Password hashing
# --------------------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, hex_digest = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(digest.hex(), hex_digest)
    except Exception:
        return False


def password_strength_errors(password: str) -> list:
    errors = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")
    if not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter")
    if not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter")
    if not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one number")
    if not any(not c.isalnum() for c in password):
        errors.append("Password must contain at least one special character")
    return errors


# --------------------------------------------------------------------------
# JWT
# --------------------------------------------------------------------------
def create_access_token(user_id: int, patient_id: int, email: str, remember_me: bool = False) -> str:
    ttl = timedelta(days=REMEMBER_ME_TTL_DAYS) if remember_me else timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES)
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "patient_id": patient_id,
        "email": email,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid authentication token.")


class CurrentUser:
    def __init__(self, user_id: int, patient_id: int, email: str):
        self.user_id = user_id
        self.patient_id = patient_id
        self.email = email


def get_current_user(authorization: Optional[str] = Header(None)) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Not authenticated. Please log in.")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    return CurrentUser(int(payload["sub"]), int(payload["patient_id"]), payload.get("email", ""))


def require_own_patient(pid: int, current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Ensures the token's owner matches the patient record being accessed."""
    if current.patient_id != pid:
        raise HTTPException(403, "You are not authorized to access this patient's records.")
    return current


# --------------------------------------------------------------------------
# Reset tokens
# --------------------------------------------------------------------------
def make_reset_token() -> tuple:
    """Returns (raw_token_for_the_user, hash_to_store_in_db)."""
    raw = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()
