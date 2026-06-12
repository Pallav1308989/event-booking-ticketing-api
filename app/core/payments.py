"""
Payment service — a thin wrapper around Stripe.

Why a wrapper? So the rest of the code calls `create_payment_intent(...)` /
`confirm_payment(...)` without caring whether Stripe is real or faked.

  STRIPE_ENABLED = False  -> FakePaymentProvider: returns realistic-looking fake
                            PaymentIntents so you can run/demo the whole app with
                            zero setup.
  STRIPE_ENABLED = True   -> StripePaymentProvider: real Stripe TEST-mode calls
                            using your sk_test_... key.

A "PaymentIntent" is Stripe's object representing an attempt to collect money.
Lifecycle here: created (status "requires_payment_method") -> confirmed
("succeeded"). In a real frontend the browser confirms it with the card; for
easy Postman testing we confirm server-side with Stripe's test card token
`pm_card_visa`.
"""

from dataclasses import dataclass

from app.core.config import settings


@dataclass
class PaymentResult:
    intent_id: str
    client_secret: str | None
    status: str  # "requires_payment_method" | "succeeded" | "failed"


# ---------------- Fake provider (default) ----------------
class FakePaymentProvider:
    def create_payment_intent(self, amount_cents: int, idempotency_key: str) -> PaymentResult:
        # Derive a stable fake id from the idempotency key so retries look identical.
        fake_id = f"pi_fake_{idempotency_key[:24]}"
        return PaymentResult(
            intent_id=fake_id,
            client_secret=f"{fake_id}_secret_test",
            status="requires_payment_method",
        )

    def confirm_payment(self, intent_id: str) -> str:
        # The fake processor always "succeeds".
        return "succeeded"


# ---------------- Real Stripe provider ----------------
class StripePaymentProvider:
    def __init__(self):
        import stripe

        stripe.api_key = settings.STRIPE_SECRET_KEY
        self._stripe = stripe

    def create_payment_intent(self, amount_cents: int, idempotency_key: str) -> PaymentResult:
        # Stripe's own idempotency support: same key -> same PaymentIntent.
        intent = self._stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=settings.STRIPE_CURRENCY,
            payment_method_types=["card"],
            idempotency_key=idempotency_key,
        )
        return PaymentResult(
            intent_id=intent.id,
            client_secret=intent.client_secret,
            status=intent.status,
        )

    def confirm_payment(self, intent_id: str) -> str:
        # Confirm server-side with a Stripe TEST card (no real money moves).
        intent = self._stripe.PaymentIntent.confirm(
            intent_id, payment_method="pm_card_visa"
        )
        return intent.status


def get_payment_provider():
    if settings.STRIPE_ENABLED:
        return StripePaymentProvider()
    return FakePaymentProvider()


payment_provider = get_payment_provider()
