# core/views.py
import json
from typing import Optional, Tuple, Dict, Any
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from google.api_core import exceptions as google_exceptions
from firebase_admin import auth as firebase_auth

from .repositories import FirestoreLostItemRepository, FirestoreClaimRepository
from .services import LostItemService, ClaimService, PaymentService, ItemAlreadyClaimedError
from .stripe_client import PaymentProviderError
from .firebase_auth import verify_firebase_token

MIN_REWARD = 100
MAX_REWARD = 10000


def _parse_json_body(request: HttpRequest) -> dict:
    try:
        return json.loads(request.body.decode("utf-8"))
    except Exception:
        return {}


def _require_firebase_user(request: HttpRequest) -> Tuple[Optional[Dict[str, Any]], Optional[JsonResponse]]:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, JsonResponse({"error": "unauthorized", "detail": "Missing Bearer token"}, status=401)

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None, JsonResponse({"error": "unauthorized", "detail": "Empty token"}, status=401)

    try:
        claims = verify_firebase_token(token)
    except (firebase_auth.InvalidIdTokenError, firebase_auth.ExpiredIdTokenError, firebase_auth.RevokedIdTokenError):
        return None, JsonResponse({"error": "unauthorized", "detail": "Invalid or expired token"}, status=401)
    except Exception as exc:
        return None, JsonResponse({"error": "unauthorized", "detail": str(exc)}, status=401)

    return claims, None


def get_lost_item_service() -> LostItemService:
    return LostItemService(FirestoreLostItemRepository())


def get_claim_service() -> ClaimService:
    item_repo = FirestoreLostItemRepository()
    claim_repo = FirestoreClaimRepository()
    return ClaimService(item_repo, claim_repo)


def get_payment_service() -> PaymentService:
    return PaymentService()


@csrf_exempt
@require_http_methods(["POST"])
def create_item_view(request: HttpRequest):
    """
    POST /api/items/

    {
      "title": "Backpack",
      "description": "Black backpack with laptop",
      "location": "Almaty, Mega",
      "finder_contact": "+7 777 000 00 00"
    }
    """
    _, error = _require_firebase_user(request)
    if error:
        return error

    data = _parse_json_body(request)
    title = data.get("title")
    description = data.get("description", "")
    location = data.get("location", "")
    finder_contact = data.get("finder_contact", "")

    if not title or not finder_contact:
        return JsonResponse({"error": "title and finder_contact are required"}, status=400)

    service = get_lost_item_service()
    try:
        item = service.create_item(title, description, location, finder_contact)
    except google_exceptions.GoogleAPICallError as exc:
        return JsonResponse({"error": "storage_unavailable", "detail": str(exc)}, status=502)

    return JsonResponse(
        {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "location": item.location,
            "finder_contact": item.finder_contact,
            "created_at": item.created_at.isoformat(),
            "claimed": item.claimed,
        },
        status=201,
    )


@require_http_methods(["GET"])
def list_items_view(request: HttpRequest):
    """
    GET /api/items/
    """
    service = get_lost_item_service()
    try:
        items = service.list_items()
    except google_exceptions.GoogleAPICallError as exc:
        return JsonResponse({"error": "storage_unavailable", "detail": str(exc)}, status=502)

    data = [
        {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "location": item.location,
            "finder_contact": item.finder_contact,
            "created_at": item.created_at.isoformat(),
            "claimed": item.claimed,
        }
        for item in items
    ]
    return JsonResponse(data, safe=False)


@require_http_methods(["GET"])
def item_detail_view(request: HttpRequest, item_id: str):
    """
    GET /api/items/<id>/
    """
    service = get_lost_item_service()
    try:
        item = service.get_item(item_id)
    except google_exceptions.GoogleAPICallError as exc:
        return JsonResponse({"error": "storage_unavailable", "detail": str(exc)}, status=502)

    if not item:
        return JsonResponse({"error": "Not found"}, status=404)

    return JsonResponse(
        {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "location": item.location,
            "finder_contact": item.finder_contact,
            "created_at": item.created_at.isoformat(),
            "claimed": item.claimed,
            "owner_contact": item.owner_contact,
            "owner_message": item.owner_message,
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def create_claim_view(request: HttpRequest, item_id: str):
    """
    POST /api/items/<id>/claim/

    {
      "owner_contact": "@telegram",
      "message": "Это мой рюкзак..."
    }
    """
    _, error = _require_firebase_user(request)
    if error:
        return error

    data = _parse_json_body(request)
    owner_contact = data.get("owner_contact")
    message = data.get("message", "")

    if not owner_contact:
        return JsonResponse({"error": "owner_contact is required"}, status=400)

    service = get_claim_service()
    try:
        claim = service.create_claim(item_id, owner_contact, message)
    except ValueError:
        return JsonResponse({"error": "Item not found"}, status=404)
    except ItemAlreadyClaimedError:
        return JsonResponse({"error": "Item already claimed"}, status=409)
    except google_exceptions.GoogleAPICallError as exc:
        return JsonResponse({"error": "storage_unavailable", "detail": str(exc)}, status=502)

    return JsonResponse(
        {
            "item_id": claim.item_id,
            "owner_contact": claim.owner_contact,
            "message": claim.message,
            "created_at": claim.created_at.isoformat(),
        },
        status=201,
    )


@csrf_exempt
@require_http_methods(["POST"])
def create_reward_payment_view(request: HttpRequest):
    """
    POST /api/payments/reward/

    { "amount_cents": 500 }
    """
    _, error = _require_firebase_user(request)
    if error:
        return error

    data = _parse_json_body(request)
    amount_cents = data.get("amount_cents")

    if not isinstance(amount_cents, int):
        return JsonResponse({"error": "amount_cents must be integer"}, status=400)
    if amount_cents < MIN_REWARD or amount_cents > MAX_REWARD:
        return JsonResponse(
            {"error": f"amount_cents must be between {MIN_REWARD} and {MAX_REWARD}"},
            status=400,
        )

    service = get_payment_service()
    try:
        checkout_url = service.create_reward_checkout(amount_cents)
    except PaymentProviderError as exc:
        return JsonResponse({"error": "payment_provider_error", "detail": str(exc)}, status=502)

    return JsonResponse({"checkout_url": checkout_url}, status=201)
