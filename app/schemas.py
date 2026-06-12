"""
Pydantic schemas = the shape of data going IN (request bodies) and OUT (responses).

FastAPI uses these to:
  - validate/parse incoming JSON automatically (422 error if it's wrong),
  - serialize ORM objects to JSON (response_model),
  - generate the interactive docs at /docs.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import BookingStatus, UserRole


# ---------- Auth / Users ----------
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str = Field(min_length=1)
    # Allow signing up as attendee or organizer. (admins are made via /seed or DB.)
    role: UserRole = UserRole.attendee


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # let it read from ORM objects
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_premium: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ---------- Events ----------
class EventCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    venue: str = ""
    starts_at: datetime
    capacity: int = Field(gt=0)
    price_cents: int = Field(ge=0, description="Ticket price in cents, e.g. 1500 = $15.00")


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    venue: str | None = None
    starts_at: datetime | None = None
    capacity: int | None = Field(default=None, gt=0)
    price_cents: int | None = Field(default=None, ge=0)


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organizer_id: int
    title: str
    description: str
    venue: str
    starts_at: datetime
    capacity: int
    seats_booked: int
    seats_available: int
    price_cents: int
    is_featured: bool
    is_cancelled: bool
    created_at: datetime


# ---------- Bookings ----------
class BookingCreate(BaseModel):
    quantity: int = Field(gt=0, le=10, description="How many tickets (max 10 per booking)")


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    attendee_id: int
    event_id: int
    quantity: int
    amount_cents: int
    status: BookingStatus
    payment_intent_id: str | None
    created_at: datetime


class BookingWithPayment(BaseModel):
    """Returned right after creating a booking — includes Stripe info for the client."""
    booking: BookingOut
    client_secret: str | None = None
    message: str


# ---------- Analytics ----------
class TicketsPerDay(BaseModel):
    date: str
    tickets_sold: int
    revenue_cents: int


class EventAnalytics(BaseModel):
    event_id: int
    title: str
    capacity: int
    tickets_sold: int
    seats_available: int
    revenue_cents: int
    sell_through_pct: float
    timeline: list[TicketsPerDay]


class PlatformAnalytics(BaseModel):
    total_events: int
    total_tickets_sold: int
    total_revenue_cents: int
    top_events: list[EventAnalytics]
