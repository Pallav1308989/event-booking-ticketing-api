"""
Booking endpoints — the heart of the project (concurrency + money).

THE OVERSELL PROBLEM
--------------------
Imagine 1 seat left and two people click "Book" at the same instant. Naively:
    seats_available = capacity - seats_booked   # both read "1 available"
    if seats_available >= 1: book()             # both pass the check -> OVERSOLD
Both requests read the old value before either writes, so both succeed.

THE FIX: row-level locking with SELECT ... FOR UPDATE
-----------------------------------------------------
We lock the Event row inside a DB transaction:
    SELECT * FROM events WHERE id = :id FOR UPDATE;
The FIRST transaction to grab the lock holds it until it COMMITs. The second
transaction BLOCKS on that line until the first finishes, then reads the
*updated* seats_booked. So the checks happen one-at-a-time — no oversell.

IDEMPOTENCY
-----------
Networks retry. If a client sends the same booking twice (same Idempotency-Key
header), we must not charge/book twice. We store the key with a UNIQUE
constraint and return the original booking on any replay.
"""

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.core.payments import payment_provider
from app.models import Booking, BookingStatus, Event, User, UserRole
from app.schemas import BookingCreate, BookingOut, BookingWithPayment

router = APIRouter(tags=["bookings"])


def _release_seats(db: Session, event_id: int, quantity: int) -> None:
    """Give seats back to an event, locking the row so the counter stays correct."""
    event = (
        db.query(Event)
        .filter(Event.id == event_id)
        .with_for_update()
        .one()
    )
    event.seats_booked = max(0, event.seats_booked - quantity)


@router.post(
    "/events/{event_id}/bookings",
    response_model=BookingWithPayment,
    status_code=status.HTTP_201_CREATED,
)
def create_booking(
    event_id: int,
    payload: BookingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    # 1) Idempotency replay: if we've seen this key, return the existing booking.
    if idempotency_key:
        existing = (
            db.query(Booking)
            .filter(Booking.idempotency_key == idempotency_key)
            .first()
        )
        if existing:
            return BookingWithPayment(
                booking=existing,
                client_secret=None,
                message="Replay of an existing booking (idempotent).",
            )

    # A stable key for both our UNIQUE column and Stripe's idempotency.
    effective_key = idempotency_key or f"auto_{uuid.uuid4().hex}"

    # 2) Lock the event row. The transaction starts implicitly; the lock is
    #    held until commit/rollback. Concurrent bookings queue up here.
    event = (
        db.query(Event)
        .filter(Event.id == event_id)
        .with_for_update()
        .one_or_none()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    if event.is_cancelled:
        raise HTTPException(status_code=400, detail="Event is cancelled.")

    # 3) Capacity check happens while we hold the lock -> safe.
    if event.seats_available < payload.quantity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Not enough seats. Available: {event.seats_available}.",
        )

    # 4) Reserve the seats by bumping the counter.
    event.seats_booked += payload.quantity
    amount_cents = payload.quantity * event.price_cents

    # 5) Create the payment intent (real Stripe or fake, transparent to us).
    payment = payment_provider.create_payment_intent(
        amount_cents=amount_cents, idempotency_key=effective_key
    )

    # 6) Persist the booking (status = pending until paid).
    booking = Booking(
        attendee_id=user.id,
        event_id=event.id,
        quantity=payload.quantity,
        amount_cents=amount_cents,
        status=BookingStatus.pending,
        idempotency_key=effective_key,
        payment_intent_id=payment.intent_id,
    )
    db.add(booking)

    try:
        db.commit()  # releases the FOR UPDATE lock
    except IntegrityError:
        # Rare race: two requests with the same idempotency key committed
        # near-simultaneously. The UNIQUE constraint rejected the loser;
        # roll back and return the winner.
        db.rollback()
        existing = (
            db.query(Booking)
            .filter(Booking.idempotency_key == effective_key)
            .first()
        )
        if existing:
            return BookingWithPayment(
                booking=existing,
                client_secret=None,
                message="Replay of an existing booking (idempotent).",
            )
        raise

    db.refresh(booking)
    return BookingWithPayment(
        booking=booking,
        client_secret=payment.client_secret,
        message="Booking created (pending). Confirm payment via POST /bookings/{id}/pay.",
    )


@router.post("/bookings/{booking_id}/pay", response_model=BookingOut)
def pay_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.attendee_id != user.id and user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Not your booking.")

    if booking.status == BookingStatus.paid:
        return booking  # already paid -> idempotent
    if booking.status == BookingStatus.cancelled:
        raise HTTPException(status_code=400, detail="Booking was cancelled.")

    # Confirm the payment with the provider.
    result_status = payment_provider.confirm_payment(booking.payment_intent_id)

    if result_status == "succeeded":
        booking.status = BookingStatus.paid
        db.commit()
        db.refresh(booking)
        return booking

    # Payment failed -> release the held seats and cancel the booking.
    _release_seats(db, booking.event_id, booking.quantity)
    booking.status = BookingStatus.cancelled
    db.commit()
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail=f"Payment failed (status: {result_status}). Seats released.",
    )


@router.post("/bookings/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.attendee_id != user.id and user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Not your booking.")
    if booking.status == BookingStatus.cancelled:
        return booking

    # Release seats back to inventory (a real app would also refund a paid booking).
    _release_seats(db, booking.event_id, booking.quantity)
    booking.status = BookingStatus.cancelled
    db.commit()
    db.refresh(booking)
    return booking


@router.get("/bookings/me", response_model=list[BookingOut])
def my_bookings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return (
        db.query(Booking)
        .filter(Booking.attendee_id == user.id)
        .order_by(Booking.created_at.desc())
        .all()
    )


@router.get("/bookings/{booking_id}", response_model=BookingOut)
def get_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.attendee_id != user.id and user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Not your booking.")
    return booking
