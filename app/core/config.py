"""
Central configuration.

All secrets / environment-specific values live in the `.env` file at the project
root. This module loads them into a typed `Settings` object using
`pydantic-settings`, so the rest of the app never reads os.environ directly and
gets validation + autocompletion for free.

To change credentials later, edit `.env` (NOT this file).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Database ---
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "1234"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "event_booking"

    # --- JWT / auth ---
    # Change this to a long random string in production. Generate one with:
    #   python -c "import secrets; print(secrets.token_hex(32))"
    JWT_SECRET: str = "CHANGE_ME_TO_A_LONG_RANDOM_STRING"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # --- Stripe (test mode) ---
    # When STRIPE_ENABLED is False the app uses a built-in FAKE payment processor
    # so the whole project runs without a Stripe account. Set it to True and paste
    # your Stripe TEST secret key (starts with sk_test_...) to use real Stripe.
    STRIPE_ENABLED: bool = False
    STRIPE_SECRET_KEY: str = "sk_test_PASTE_YOUR_KEY_HERE"
    STRIPE_CURRENCY: str = "usd"

    # --- Business rules (premium / limits) ---
    FREE_ORGANIZER_EVENT_LIMIT: int = 3
    PREMIUM_ORGANIZER_EVENT_LIMIT: int = 100
    PREMIUM_PRICE_CENTS: int = 2000  # $20.00 to upgrade an organizer to premium

    @property
    def database_url(self) -> str:
        """SQLAlchemy connection string built from the parts above."""
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Tell pydantic-settings to read from the .env file at the project root.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so the .env file is parsed only once per process."""
    return Settings()


settings = get_settings()
