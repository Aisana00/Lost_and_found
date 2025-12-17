# core/views.py
import json
import logging
from typing import Optional, Tuple, Dict, Any
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from google.api_core import exceptions as google_exceptions
from firebase_admin import auth as firebase_auth

from .repositories import (
    FirestoreLostItemRepository,
    FirestoreClaimRepository,
    FirestoreChatRepository,
    FirestoreMessageRepository,
    FirestoreUserProfileRepository,
)
from .services import LostItemService, ClaimService, ChatService, PaymentService, ItemAlreadyClaimedError, UserProfileService
from .services import SelfActionNotAllowedError
from .domain import ITEM_CATEGORIES, CATEGORY_CHOICES
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
    logger = logging.getLogger(__name__)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, JsonResponse({"error": "unauthorized", "detail": "Missing Bearer token"}, status=401)

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None, JsonResponse({"error": "unauthorized", "detail": "Empty token"}, status=401)

    try:
        claims = verify_firebase_token(token)
    except (firebase_auth.InvalidIdTokenError, firebase_auth.ExpiredIdTokenError, firebase_auth.RevokedIdTokenError) as exc:
        logger.exception("Firebase auth failed (invalid/expired/revoked)")
        return None, JsonResponse({"error": "unauthorized", "detail": "Invalid or expired token"}, status=401)
    except Exception as exc:
        logger.exception("Firebase auth failed (unexpected)")
        return None, JsonResponse({"error": "unauthorized", "detail": str(exc)}, status=401)

    return claims, None


def get_lost_item_service() -> LostItemService:
    return LostItemService(FirestoreLostItemRepository())


def get_claim_service() -> ClaimService:
    item_repo = FirestoreLostItemRepository()
    claim_repo = FirestoreClaimRepository()
    chat_repo = FirestoreChatRepository()
    return ClaimService(item_repo, claim_repo, chat_repo)


def get_chat_service() -> ChatService:
    chat_repo = FirestoreChatRepository()
    message_repo = FirestoreMessageRepository()
    item_repo = FirestoreLostItemRepository()
    return ChatService(chat_repo, message_repo, item_repo)


def get_payment_service() -> PaymentService:
    return PaymentService()


def get_user_profile_service() -> UserProfileService:
    return UserProfileService(FirestoreUserProfileRepository())


def _validate_profile_field(value: Optional[str], *, max_len: int) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("must be a string")
    value = value.strip()
    if len(value) > max_len:
        raise ValueError(f"max length is {max_len}")
    return value


def _validate_language(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("language must be a string")
    value = value.strip().lower()
    if value not in {"en", "ru", "kk"}:
        raise ValueError("language must be one of: en, ru, kk")
    return value


@csrf_exempt
@require_http_methods(["GET", "PATCH", "PUT"])
def profile_view(request: HttpRequest):
    """
    GET /api/profile/
    PATCH/PUT /api/profile/

    Body example:
    {
      "display_name": "Alex",
      "city": "Almaty",
      "about": "…"
    }
    """
    user, error = _require_firebase_user(request)
    if error:
        return error

    uid = user["uid"]
    email = user.get("email")

    service = get_user_profile_service()

    if request.method == "GET":
        try:
            profile = service.get_or_create(uid, email)
        except google_exceptions.GoogleAPICallError as exc:
            return JsonResponse({"error": "storage_unavailable", "detail": str(exc)}, status=502)
        return JsonResponse(
            {
                "uid": profile.uid,
                "email": profile.email,
                "display_name": profile.display_name,
                "city": profile.city,
                "about": profile.about,
                "language": profile.language,
                "created_at": profile.created_at.isoformat() if profile.created_at else None,
                "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
            }
        )

    data = _parse_json_body(request)

    try:
        display_name = _validate_profile_field(data.get("display_name"), max_len=50)
        city = _validate_profile_field(data.get("city"), max_len=50)
        about = _validate_profile_field(data.get("about"), max_len=500)
        language = _validate_language(data.get("language"))
    except ValueError as exc:
        return JsonResponse({"error": "invalid_profile", "detail": str(exc)}, status=400)

    try:
        profile = service.update_profile(uid, email, display_name=display_name, city=city, about=about, language=language)
    except google_exceptions.GoogleAPICallError as exc:
        return JsonResponse({"error": "storage_unavailable", "detail": str(exc)}, status=502)

    return JsonResponse(
        {
            "uid": profile.uid,
            "email": profile.email,
            "display_name": profile.display_name,
            "city": profile.city,
            "about": profile.about,
            "language": profile.language,
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def create_item_view(request: HttpRequest):
    """
    POST /api/items/create/

    {
      "title": "Backpack",
      "description": "Black backpack with laptop",
      "location": "Almaty, Mega",
      "category": "bags"
    }
    """
    user, error = _require_firebase_user(request)
    if error:
        return error

    data = _parse_json_body(request)
    title = data.get("title")
    description = data.get("description", "")
    location = data.get("location", "")
    category = data.get("category", "other")

    if not title:
        return JsonResponse({"error": "title is required"}, status=400)

    # Валидация категории
    if category not in CATEGORY_CHOICES:
        category = "other"

    service = get_lost_item_service()
    try:
        item = service.create_item(title, description, location, user["uid"], category)
    except google_exceptions.GoogleAPICallError as exc:
        return JsonResponse({"error": "storage_unavailable", "detail": str(exc)}, status=502)

    return JsonResponse(
        {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "location": item.location,
            "finder_id": item.finder_id,
            "created_at": item.created_at.isoformat(),
            "claimed": item.claimed,
            "category": item.category,
        },
        status=201,
    )


@require_http_methods(["GET"])
def list_items_view(request: HttpRequest):
    """
    GET /api/items/
    GET /api/items/?category=electronics&date_from=2024-01-01&date_to=2024-12-31
    """
    # Получаем параметры фильтрации из query string
    category = request.GET.get("category")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    service = get_lost_item_service()
    try:
        # Используем фильтрацию если есть параметры
        if category or date_from or date_to:
            items = service.list_items_filtered(category, date_from, date_to)
        else:
            items = service.list_items()
    except google_exceptions.GoogleAPICallError as exc:
        return JsonResponse({"error": "storage_unavailable", "detail": str(exc)}, status=502)

    data = [
        {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "location": item.location,
            "finder_id": item.finder_id,
            "created_at": item.created_at.isoformat(),
            "claimed": item.claimed,
            "category": item.category,
        }
        for item in items
    ]
    return JsonResponse(data, safe=False)


@require_http_methods(["GET"])
def get_categories_view(request: HttpRequest):
    """
    GET /api/categories/
    Возвращает список доступных категорий.
    """
    return JsonResponse(
        [{"id": cat[0], "name": cat[1]} for cat in ITEM_CATEGORIES],
        safe=False
    )


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
            "finder_id": item.finder_id,
            "created_at": item.created_at.isoformat(),
            "claimed": item.claimed,
            "category": item.category,
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def create_claim_view(request: HttpRequest, item_id: str):
    """
    POST /api/items/<id>/claim/

    Creates a claim and automatically creates a chat between finder and claimer.
    No body needed - claimer is identified by Firebase token.
    """
    user, error = _require_firebase_user(request)
    if error:
        return error

    service = get_claim_service()
    try:
        claim, chat = service.create_claim(item_id, user["uid"])
    except ValueError:
        return JsonResponse({"error": "Item not found"}, status=404)
    except SelfActionNotAllowedError:
        return JsonResponse({"error": "forbidden", "detail": "Cannot claim your own item"}, status=403)
    except ItemAlreadyClaimedError:
        return JsonResponse({"error": "Item already claimed"}, status=409)
    except google_exceptions.GoogleAPICallError as exc:
        return JsonResponse({"error": "storage_unavailable", "detail": str(exc)}, status=502)

    return JsonResponse(
        {
            "claim_id": claim.id,
            "item_id": claim.item_id,
            "chat_id": chat.id,
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


@require_http_methods(["GET"])
def stripe_success_view(request: HttpRequest):
    # Redirect back into the mobile app via deep link. Works well with Custom Tabs / SFSafariViewController.
    html = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Payment successful</title>
  </head>
  <body>
    <h2>Payment successful</h2>
    <p>Returning to the app…</p>
    <p><a href="lostandfound://payment/success">Open the app</a></p>
    <script>
      window.location.href = "lostandfound://payment/success";
    </script>
  </body>
</html>
"""
    return HttpResponse(html, content_type="text/html; charset=utf-8")


@require_http_methods(["GET"])
def stripe_cancel_view(request: HttpRequest):
    html = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Payment canceled</title>
  </head>
  <body>
    <h2>Payment canceled</h2>
    <p>Returning to the app…</p>
    <p><a href="lostandfound://payment/cancel">Open the app</a></p>
    <script>
      window.location.href = "lostandfound://payment/cancel";
    </script>
  </body>
</html>
"""
    return HttpResponse(html, content_type="text/html; charset=utf-8")


@require_http_methods(["GET"])
def list_user_items_view(request: HttpRequest):
    """
    GET /api/items/my/

    Returns all items created by the authenticated user.
    """
    logger = logging.getLogger(__name__)
    user, error = _require_firebase_user(request)
    if error:
        return error

    logger.info(f"Fetching items for user: {user['uid']}")
    service = get_lost_item_service()
    try:
        all_items = service.list_items()
        logger.info(f"Total items in database: {len(all_items)}")
        # Filter items by current user's Firebase UID
        user_items = [item for item in all_items if item.finder_id == user["uid"]]
        logger.info(f"User items found: {len(user_items)}")
    except google_exceptions.GoogleAPICallError as exc:
        return JsonResponse({"error": "storage_unavailable", "detail": str(exc)}, status=502)

    data = [
        {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "location": item.location,
            "finder_id": item.finder_id,
            "created_at": item.created_at.isoformat(),
            "claimed": item.claimed,
            "category": item.category,
        }
        for item in user_items
    ]
    return JsonResponse(data, safe=False)


@require_http_methods(["GET"])
def list_claimed_items_view(request: HttpRequest):
    """
    GET /api/items/claimed/

    Returns items claimed by the authenticated user (claimer).
    """
    user, error = _require_firebase_user(request)
    if error:
        return error

    uid = user["uid"]
    claim_repo = FirestoreClaimRepository()
    item_repo = FirestoreLostItemRepository()

    try:
        claims = claim_repo.list_by_claimer_id(uid)
        items = []
        for claim in claims:
            item = item_repo.get_by_id(claim.item_id)
            if not item:
                continue
            items.append(
                {
                    "id": item.id,
                    "title": item.title,
                    "description": item.description,
                    "location": item.location,
                    "finder_id": item.finder_id,
                    "created_at": item.created_at.isoformat(),
                    "claimed": item.claimed,
                    "claim_id": claim.id,
                    "claim_created_at": claim.created_at.isoformat(),
                }
            )
    except google_exceptions.GoogleAPICallError as exc:
        return JsonResponse({"error": "storage_unavailable", "detail": str(exc)}, status=502)

    return JsonResponse(items, safe=False)


@require_http_methods(["GET"])
def list_user_chats_view(request: HttpRequest):
    """
    GET /api/chats/

    Returns all chats for the authenticated user.
    """
    user, error = _require_firebase_user(request)
    if error:
        return error

    service = get_chat_service()
    try:
        chats = service.get_user_chats(user["uid"])
    except google_exceptions.GoogleAPICallError as exc:
        return JsonResponse({"error": "storage_unavailable", "detail": str(exc)}, status=502)

    # Convert datetime objects to ISO format
    for chat in chats:
        if chat.get("created_at"):
            chat["created_at"] = chat["created_at"].isoformat()
        if chat.get("last_message_at"):
            chat["last_message_at"] = chat["last_message_at"].isoformat()

    return JsonResponse(chats, safe=False)


@require_http_methods(["GET"])
def get_chat_messages_view(request: HttpRequest, item_id: str):
    """
    GET /api/chats/<item_id>/messages/

    Returns all messages for a specific chat (identified by item_id).
    """
    user, error = _require_firebase_user(request)
    if error:
        return error

    service = get_chat_service()
    try:
        messages = service.get_messages(item_id, user["uid"])
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=403)
    except SelfActionNotAllowedError as e:
        return JsonResponse({"error": "forbidden", "detail": str(e)}, status=403)
    except google_exceptions.GoogleAPICallError as exc:
        return JsonResponse({"error": "storage_unavailable", "detail": str(exc)}, status=502)

    data = [
        {
            "id": msg.id,
            "item_id": msg.item_id,
            "sender_id": msg.sender_id,
            "text": msg.text,
            "created_at": msg.created_at.isoformat(),
            "read": msg.read,
        }
        for msg in messages
    ]

    return JsonResponse(data, safe=False)


@csrf_exempt
@require_http_methods(["POST"])
def send_message_view(request: HttpRequest, item_id: str):
    """
    POST /api/chats/<item_id>/messages/

    {
      "text": "Hello, is this still available?"
    }
    """
    user, error = _require_firebase_user(request)
    if error:
        return error

    data = _parse_json_body(request)
    text = data.get("text", "").strip()

    if not text:
        return JsonResponse({"error": "text is required"}, status=400)

    service = get_chat_service()
    try:
        message = service.send_message(item_id, user["uid"], text)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=403)
    except SelfActionNotAllowedError as e:
        return JsonResponse({"error": "forbidden", "detail": str(e)}, status=403)
    except google_exceptions.GoogleAPICallError as exc:
        return JsonResponse({"error": "storage_unavailable", "detail": str(exc)}, status=502)

    return JsonResponse(
        {
            "id": message.id,
            "item_id": message.item_id,
            "sender_id": message.sender_id,
            "text": message.text,
            "created_at": message.created_at.isoformat(),
            "read": message.read,
        },
        status=201,
    )
