"""
Reusable FastAPI dependencies for authentication + authorization (RBAC).

  get_current_user  -> turns the "Authorization: Bearer <jwt>" header into a User.
  require_role(...)  -> a dependency FACTORY that only lets certain roles through.

Usage in a route:
    @router.post("/events")
    def create_event(user: User = Depends(require_role(UserRole.organizer,
                                                        UserRole.admin))):
        ...
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import User, UserRole

# This produces the "Authorize" button in the /docs UI and reads the
# Authorization header for us.
bearer_scheme = HTTPBearer(auto_error=True)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Decode the JWT, then load the matching user from the DB."""
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload.get("sub"))
    except (jwt.PyJWTError, TypeError, ValueError):
        raise credentials_error

    user = db.get(User, user_id)
    if user is None:
        raise credentials_error
    return user


def require_role(*allowed_roles: UserRole):
    """
    Returns a dependency that allows the request only if the current user's role
    is in `allowed_roles`. Otherwise 403 Forbidden.
    """

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Requires role: {', '.join(r.value for r in allowed_roles)}. "
                    f"You are '{user.role.value}'."
                ),
            )
        return user

    return checker
