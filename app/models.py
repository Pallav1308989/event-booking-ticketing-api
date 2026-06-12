"""
Database tables (ORM models).

Three core tables:
  - User    : accounts with a role (attendee / organizer / admin) for RBAC.
  - Event   : something an organizer creates and sells tickets to.
  - Booking : an order placed by an attendee for N tickets of one event.

Concurrency note: `Event.seats_booked` is the running count of reserved seats.
A seat is reserved the moment a (pending) booking is created and released if the
booking is cancelled / payment fails. The booking endpoint locks the Event row
(SELECT ... FOR UPDATE) before touching this counter so two requests can never
oversell the last seat. See app/routers/bookings.py.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserRole(str, enum.Enum):
    attendee = "attendee"
    organizer = "organizer"
    admin = "admin"


class BookingStatus(str, enum.Enum):
    pending = "pending"      # seats reserved, payment not completed yet
    paid = "paid"            # payment succeeded
    cancelled = "cancelled"  # released (user cancelled or payment failed)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.attendee, nullable=False
    )
    # Premium unlocks a higher event limit + the ability to feature listings.
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    events: Mapped[list["Event"]] = relationship(back_populates="organizer")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="attendee")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    organizer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    venue: Mapped[str] = mapped_column(String(255), default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    seats_booked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    organizer: Mapped["User"] = relationship(back_populates="events")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="event")

    @property
    def seats_available(self) -> int:
        return self.capacity - self.seats_booked


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    attendee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus), default=BookingStatus.pending, nullable=False
    )

    # Idempotency: the client sends a unique key; a UNIQUE constraint guarantees
    # that retrying the same request never creates a second booking.
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )

    # Stripe PaymentIntent id (or a fake id when Stripe is disabled).
    payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    attendee: Mapped["User"] = relationship(back_populates="bookings")
    event: Mapped["Event"] = relationship(back_populates="bookings")
