"""
Event endpoints.

RBAC summary:
  - Anyone logged in can browse events (GET).
  - Only organizers/admins can create.
  - Only the owning organizer (or an admin) can update / cancel / feature.

Premium tie-in:
  - Free organizers can have at most FREE_ORGANIZER_EVENT_LIMIT active events.
  - Premium organizers get PREMIUM_ORGANIZER_EVENT_LIMIT.
  - Only premium organizers (or admins) can mark an event "featured".
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_role
from app.core.config import settings
from app.core.database import get_db
from app.models import Event, User, UserRole
from app.schemas import EventCreate, EventOut, EventUpdate

router = APIRouter(prefix="/events", tags=["events"])


def _get_owned_event_or_404(event_id: int, user: User, db: Session) -> Event:
    """Fetch an event and ensure the caller is allowed to modify it."""
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found.")
    # Admins can touch any event; organizers only their own.
    if user.role != UserRole.admin and event.organizer_id != user.id:
        raise HTTPException(status_code=403, detail="Not your event.")
    return event


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(
    payload: EventCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.organizer, UserRole.admin)),
):
    # Enforce the per-organizer event limit (admins are exempt).
    if user.role == UserRole.organizer:
        active_count = (
            db.query(Event)
            .filter(Event.organizer_id == user.id, Event.is_cancelled == False)  # noqa: E712
            .count()
        )
        limit = (
            settings.PREMIUM_ORGANIZER_EVENT_LIMIT
            if user.is_premium
            else settings.FREE_ORGANIZER_EVENT_LIMIT
        )
        if active_count >= limit:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Event limit reached ({limit}). "
                    f"Upgrade to premium via POST /premium/upgrade for more."
                ),
            )

    event = Event(organizer_id=user.id, **payload.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("", response_model=list[EventOut])
def list_events(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
    featured_only: bool = False,
):
    """Browse active events. Featured events are sorted first."""
    stmt = select(Event).where(Event.is_cancelled == False)  # noqa: E712
    if featured_only:
        stmt = stmt.where(Event.is_featured == True)  # noqa: E712
    stmt = stmt.order_by(Event.is_featured.desc(), Event.starts_at.asc())
    return db.scalars(stmt).all()


@router.get("/{event_id}", response_model=EventOut)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found.")
    return event


@router.patch("/{event_id}", response_model=EventOut)
def update_event(
    event_id: int,
    payload: EventUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.organizer, UserRole.admin)),
):
    event = _get_owned_event_or_404(event_id, user, db)

    updates = payload.model_dump(exclude_unset=True)
    # Don't allow shrinking capacity below seats already sold.
    if "capacity" in updates and updates["capacity"] < event.seats_booked:
        raise HTTPException(
            status_code=400,
            detail=f"Capacity can't be below seats already booked ({event.seats_booked}).",
        )
    for field, value in updates.items():
        setattr(event, field, value)

    db.commit()
    db.refresh(event)
    return event


@router.post("/{event_id}/cancel", response_model=EventOut)
def cancel_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.organizer, UserRole.admin)),
):
    event = _get_owned_event_or_404(event_id, user, db)
    event.is_cancelled = True
    db.commit()
    db.refresh(event)
    return event


@router.post("/{event_id}/feature", response_model=EventOut)
def feature_event(
    event_id: int,
    featured: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.organizer, UserRole.admin)),
):
    """Premium perk: highlight an event in listings."""
    event = _get_owned_event_or_404(event_id, user, db)
    # Organizers must be premium to feature; admins always can.
    if user.role == UserRole.organizer and not user.is_premium:
        raise HTTPException(
            status_code=403,
            detail="Featuring events is a premium perk. Upgrade via POST /premium/upgrade.",
        )
    event.is_featured = featured
    db.commit()
    db.refresh(event)
    return event
