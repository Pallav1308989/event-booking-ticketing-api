"""
Analytics endpoints.

  GET /events/{id}/analytics  -> per-event: tickets sold, revenue, daily timeline
                                 (owning organizer or admin only)
  GET /analytics/platform     -> platform-wide totals + top events (admin only)

Only PAID bookings count toward tickets-sold and revenue. We aggregate in SQL
(SUM / GROUP BY) rather than in Python so it stays fast as data grows.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_role
from app.core.database import get_db
from app.models import Booking, BookingStatus, Event, User, UserRole
from app.schemas import EventAnalytics, PlatformAnalytics, TicketsPerDay

router = APIRouter(tags=["analytics"])


def _build_event_analytics(db: Session, event: Event) -> EventAnalytics:
    # Totals across all PAID bookings for this event.
    tickets_sold, revenue = (
        db.query(
            func.coalesce(func.sum(Booking.quantity), 0),
            func.coalesce(func.sum(Booking.amount_cents), 0),
        )
        .filter(Booking.event_id == event.id, Booking.status == BookingStatus.paid)
        .one()
    )

    # Daily timeline: GROUP BY the calendar date of each paid booking.
    day = func.date(Booking.created_at)
    rows = (
        db.query(
            day.label("day"),
            func.sum(Booking.quantity),
            func.sum(Booking.amount_cents),
        )
        .filter(Booking.event_id == event.id, Booking.status == BookingStatus.paid)
        .group_by(day)
        .order_by(day)
        .all()
    )
    timeline = [
        TicketsPerDay(date=str(d), tickets_sold=int(qty), revenue_cents=int(rev))
        for d, qty, rev in rows
    ]

    sell_through = (tickets_sold / event.capacity * 100) if event.capacity else 0.0
    return EventAnalytics(
        event_id=event.id,
        title=event.title,
        capacity=event.capacity,
        tickets_sold=int(tickets_sold),
        seats_available=event.capacity - int(tickets_sold),
        revenue_cents=int(revenue),
        sell_through_pct=round(sell_through, 2),
        timeline=timeline,
    )


@router.get("/events/{event_id}/analytics", response_model=EventAnalytics)
def event_analytics(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found.")
    if user.role != UserRole.admin and event.organizer_id != user.id:
        raise HTTPException(status_code=403, detail="Not your event.")
    return _build_event_analytics(db, event)


@router.get("/analytics/platform", response_model=PlatformAnalytics)
def platform_analytics(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.admin)),
):
    total_events = db.query(func.count(Event.id)).scalar() or 0
    total_tickets, total_revenue = (
        db.query(
            func.coalesce(func.sum(Booking.quantity), 0),
            func.coalesce(func.sum(Booking.amount_cents), 0),
        )
        .filter(Booking.status == BookingStatus.paid)
        .one()
    )

    # Top 5 events by revenue.
    top_event_ids = [
        row[0]
        for row in (
            db.query(Booking.event_id)
            .filter(Booking.status == BookingStatus.paid)
            .group_by(Booking.event_id)
            .order_by(func.sum(Booking.amount_cents).desc())
            .limit(5)
            .all()
        )
    ]
    top_events = [
        _build_event_analytics(db, db.get(Event, eid)) for eid in top_event_ids
    ]

    return PlatformAnalytics(
        total_events=int(total_events),
        total_tickets_sold=int(total_tickets),
        total_revenue_cents=int(total_revenue),
        top_events=top_events,
    )
