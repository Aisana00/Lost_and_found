# core/views.py
import json
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods

from . import lost_item_service, claim_service, payment_service


def _parse_json_body(request: HttpRequest) -> dict:
    try:
        return json.loads(request.body.decode("utf-8"))
    except Exception:
        return {}


@require_http_methods(["POST"])
def create_item_view(request: HttpRequest):
    data = _parse_json_body(request)
    title = data.get("title")
    description = data.get("description", "")
    location = data.get("location", "")
    finder_contact = data.get("finder_contact", "")

    if not title or not finder_contact:
        return JsonResponse({"error": "title and finder_contact are required"}, status=400)

    item = lost_item_service.create_item(title, description, location, finder_contact)
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
    items = lost_item_service.list_items()
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
    item = lost_item_service.get_item(item_id)
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


@require_http_methods(["POST"])
def create_claim_view(request: HttpRequest, item_id: str):
    data = _parse_json_body(request)
    owner_contact = data.get("owner_contact")
    message = data.get("message", "")

    if not owner_contact:
        return JsonResponse({"error": "owner_contact is required"}, status=400)

    try:
        claim = claim_service.create_claim(item_id, owner_contact, message)
    except ValueError:
        return JsonResponse({"error": "Item not found"}, status=404)

    return JsonResponse(
        {
            "item_id": claim.item_id,
            "owner_contact": claim.owner_contact,
            "message": claim.message,
            "created_at": claim.created_at.isoformat(),
        },
        status=201,
    )


@require_http_methods(["POST"])
def create_reward_payment_view(request: HttpRequest):
    """
    Пример: POST { "amount_cents": 500 }
    """
    data = _parse_json_body(request)
    amount_cents = data.get("amount_cents")

    if not isinstance(amount_cents, int) or amount_cents <= 0:
        return JsonResponse({"error": "amount_cents must be positive integer"}, status=400)

    checkout_url = payment_service.create_reward_checkout(amount_cents)
    return JsonResponse({"checkout_url": checkout_url}, status=201)
