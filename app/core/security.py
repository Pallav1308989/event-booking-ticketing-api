"""
Low-level security primitives: password hashing and JWT tokens.

Passwords are NEVER stored in plain text. We store a bcrypt hash. bcrypt is
deliberately slow + salted, so even if the DB leaks, passwords are hard to crack.

Auth flow:
  register -> hash_password() -> store hash
  login    -> verify_password() -> create_access_token() -> client gets a JWT
  request  -> client sends "Authorization: Bearer <jwt>" -> decode_access_token()
"""

from datetime import datetime, timedelta, timezone

import jwt  # PyJWT
from passlib.context import CryptContext

from app.core.config import settings

# bcrypt scheme. passlib handles salting + the algorithm details.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str | int, role: str) -> str:
    """
    Build a signed JWT. The payload ("claims") carries the user id (`sub`) and
    `role`, plus an expiry (`exp`). It's signed with JWT_SECRET so it can't be
    tampered with — anyone can read it, but only the server can forge it.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": str(subject),  # JWT spec wants `sub` to be a string
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Verify signature + expiry and return the claims.
    Raises jwt.PyJWTError (caught by the caller) if the token is invalid/expired.
    """
    return jwt.decode(
        token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
    )
