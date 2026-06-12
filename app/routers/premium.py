"""
Premium upgrade for organizers.

Paying for premium raises the event limit and unlocks "featured" listings.
We reuse the same payment provider as ticket booking. To keep Postman testing
simple, this single endpoint creates AND confirms the payment in one step.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.core.config import settings
from app.core.database import get_db
from app.core.payments import payment_provider
from app.models import User, UserRole
from app.schemas import UserOut

router = APIRouter(prefix="/premium", tags=["premium"])


@router.post("/upgrade", response_model=UserOut)
def upgrade_to_premium(
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.organizer)),
):
    if user.is_premium:
        raise HTTPException(status_code=400, detail="Already premium.")

    key = f"premium_{user.id}_{uuid.uuid4().hex}"
    payment = payment_provider.create_payment_intent(
        amount_cents=settings.PREMIUM_PRICE_CENTS, idempotency_key=key
    )
    result_status = payment_provider.confirm_payment(payment.intent_id)
    if result_status != "succeeded":
        raise HTTPException(status_code=402, detail=f"Payment failed ({result_status}).")

    user.is_premium = True
    db.commit()
    db.refresh(user)
    return user
