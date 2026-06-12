"""
Helper script — run once to set up the database for testing.

  python seed.py

It:
  1. creates all tables (if missing),
  2. creates an admin user you can log in with,
  3. prints the admin credentials.

Admins can't be created through the public /auth/register endpoint, so this
script is how you bootstrap one.
"""

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import User, UserRole

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin1234"


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if existing:
            print(f"Admin already exists: {ADMIN_EMAIL}")
            return
        admin = User(
            email=ADMIN_EMAIL,
            hashed_password=hash_password(ADMIN_PASSWORD),
            full_name="Platform Admin",
            role=UserRole.admin,
            is_premium=True,
        )
        db.add(admin)
        db.commit()
        print("Created admin user:")
        print(f"  email:    {ADMIN_EMAIL}")
        print(f"  password: {ADMIN_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
