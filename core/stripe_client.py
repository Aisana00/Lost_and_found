# core/stripe_client.py
import stripe
from django.conf import settings

stripe.api_key = settings.STRIPE_SECRET_KEY


class PaymentProviderError(Exception):
    """Ошибки платёжного провайдера (Stripe)."""


def create_checkout_session(amount_cents: int, currency: str = "usd") -> str:
    """
    Создаёт Stripe Checkout Session и возвращает URL.
    amount_cents: сумма в центах (например 500 = $5.00)
    """
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": currency,
                        "product_data": {
                            "name": "Lost & Found reward",
                        },
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }
            ],
            success_url=settings.STRIPE_SUCCESS_URL,
            cancel_url=settings.STRIPE_CANCEL_URL,
        )
    except stripe.error.StripeError as exc:  # type: ignore[attr-defined]
        # Пробрасываем контролируемую ошибку выше, чтобы вернуть 502 вместо 500.
        raise PaymentProviderError(exc.user_message or str(exc)) from exc

    return session.url
