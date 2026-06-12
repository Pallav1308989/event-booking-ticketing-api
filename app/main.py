"""
Application entry point.

Run with:  uvicorn app.main:app --reload
Then open: http://localhost:8000/docs  (interactive Swagger UI)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.database import Base, engine
from app.routers import analytics, bookings, events, premium
from app.auth import router as auth_router

# Import models so SQLAlchemy registers them before create_all runs.
from app import models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup, create any missing tables. (For a real app you'd use Alembic
    # migrations instead; create_all is perfect for a project like this.)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Event Booking / Ticketing API",
    description=(
        "Eventbrite-lite: events, ticket booking with safe concurrency, "
        "JWT auth + RBAC, Stripe test payments, premium organizers, analytics."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Wire up all the route groups.
app.include_router(auth_router.router)
app.include_router(events.router)
app.include_router(bookings.router)
app.include_router(premium.router)
app.include_router(analytics.router)


@app.get("/", tags=["health"])
def root():
    return {
        "service": "Event Booking / Ticketing API",
        "docs": "/docs",
        "stripe_enabled": settings.STRIPE_ENABLED,
    }
