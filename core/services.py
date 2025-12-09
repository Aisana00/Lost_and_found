# core/services.py
from typing import List, Optional

from .domain import LostItem, Claim
from .repositories import LostItemRepository, ClaimRepository
from .stripe_client import create_checkout_session


class LostItemService:
    """Бизнес-логика вокруг найденных вещей."""

    def __init__(self, repo: LostItemRepository):
        self.repo = repo

    def create_item(self, title: str, description: str, location: str, finder_contact: str) -> LostItem:
        return self.repo.create(title, description, location, finder_contact)

    def list_items(self) -> List[LostItem]:
        return self.repo.list_all()

    def get_item(self, item_id: str) -> Optional[LostItem]:
        return self.repo.get_by_id(item_id)


class ClaimService:
    """Логика заявок владельцев на вещи."""

    def __init__(self, item_repo: LostItemRepository, claim_repo: ClaimRepository):
        self.item_repo = item_repo
        self.claim_repo = claim_repo

    def create_claim(self, item_id: str, owner_contact: str, message: str) -> Claim:
        item = self.item_repo.get_by_id(item_id)
        if item is None:
            raise ValueError("Item not found")

        item.claimed = True
        item.owner_contact = owner_contact
        item.owner_message = message
        self.item_repo.save(item)

        return self.claim_repo.create(item_id, owner_contact, message)


class PaymentService:
    """Логика работы с платежами (Stripe)."""

    def create_reward_checkout(self, amount_cents: int) -> str:
        return create_checkout_session(amount_cents)
