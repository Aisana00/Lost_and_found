# core/services.py
from typing import List, Optional
from django.utils import timezone

from .domain import LostItem, Claim, Chat, Message, UserProfile
from .repositories import (
    LostItemRepository,
    ClaimRepository,
    ChatRepository,
    MessageRepository,
    UserProfileRepository,
)
from .stripe_client import create_checkout_session


class ItemAlreadyClaimedError(Exception):
    """Вещь уже помечена как забранная/затребованная владельцем."""


class SelfActionNotAllowedError(Exception):
    """Пользователь пытается совершить действие над своим же объектом."""


class LostItemService:
    """Бизнес-логика вокруг найденных вещей."""

    def __init__(self, repo: LostItemRepository):
        self.repo = repo

    def create_item(self, title: str, description: str, location: str, finder_id: str, category: str = "other") -> LostItem:
        return self.repo.create(title, description, location, finder_id, category)

    def list_items(self) -> List[LostItem]:
        return self.repo.list_all()

    def list_items_filtered(self, category: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[LostItem]:
        return self.repo.list_filtered(category, date_from, date_to)

    def get_item(self, item_id: str) -> Optional[LostItem]:
        return self.repo.get_by_id(item_id)

    def update_item(self, item: LostItem) -> None:
        self.repo.save(item)

    def delete_item(self, item_id: str) -> bool:
        return self.repo.delete(item_id)


class ClaimService:
    """Логика заявок владельцев на вещи."""

    def __init__(
        self,
        item_repo: LostItemRepository,
        claim_repo: ClaimRepository,
        chat_repo: ChatRepository
    ):
        self.item_repo = item_repo
        self.claim_repo = claim_repo
        self.chat_repo = chat_repo

    def create_claim(self, item_id: str, claimer_id: str) -> tuple[Claim, Chat]:
        """Create a claim and automatically create a chat between finder and claimer."""
        item = self.item_repo.get_by_id(item_id)
        if item is None:
            raise ValueError("Item not found")

        if item.finder_id and claimer_id == item.finder_id:
            raise SelfActionNotAllowedError("Cannot claim your own item")

        if item.claimed:
            raise ItemAlreadyClaimedError("Item already claimed")

        # Mark item as claimed
        item.claimed = True
        self.item_repo.save(item)

        # Create claim
        claim = self.claim_repo.create(item_id, claimer_id)

        # Create chat between finder and claimer
        chat = self.chat_repo.create(item_id, item.finder_id, claimer_id)

        return claim, chat


class ChatService:
    """Логика работы с чатами."""

    def __init__(
        self,
        chat_repo: ChatRepository,
        message_repo: MessageRepository,
        item_repo: LostItemRepository
    ):
        self.chat_repo = chat_repo
        self.message_repo = message_repo
        self.item_repo = item_repo

    def get_user_chats(self, user_id: str) -> List[dict]:
        """Get all chats for a user with item details."""
        chats = self.chat_repo.get_user_chats(user_id)
        result = []

        for chat in chats:
            item = self.item_repo.get_by_id(chat.item_id)
            if item:
                result.append({
                    "chat_id": chat.id,
                    "item_id": chat.item_id,
                    "item_title": item.title,
                    "last_message": chat.last_message,
                    "last_message_at": chat.last_message_at,
                    "created_at": chat.created_at,
                })

        return result

    def send_message(self, item_id: str, sender_id: str, text: str) -> Message:
        """Send a message and update chat last_message."""
        # Get or verify chat exists
        chat = self.chat_repo.get_by_item_id(item_id)
        if not chat:
            raise ValueError("Chat not found for this item")

        if chat.finder_id and chat.finder_id == chat.claimer_id:
            raise SelfActionNotAllowedError("Cannot send messages to yourself")

        # Verify sender is part of the chat
        if sender_id not in [chat.finder_id, chat.claimer_id]:
            raise ValueError("User is not part of this chat")

        # Create message
        message = self.message_repo.create(item_id, sender_id, text)

        # Update chat with last message
        chat.last_message = text
        chat.last_message_at = message.created_at
        self.chat_repo.save(chat)

        return message

    def get_messages(self, item_id: str, user_id: str) -> List[Message]:
        """Get all messages for a chat, verifying user access."""
        chat = self.chat_repo.get_by_item_id(item_id)
        if not chat:
            raise ValueError("Chat not found")

        if chat.finder_id and chat.finder_id == chat.claimer_id:
            raise SelfActionNotAllowedError("Cannot open chat with yourself")

        # Verify user is part of the chat
        if user_id not in [chat.finder_id, chat.claimer_id]:
            raise ValueError("User is not part of this chat")

        return self.message_repo.get_by_item_id(item_id)


class PaymentService:
    """Логика работы с платежами (Stripe)."""

    def create_reward_checkout(self, amount_cents: int) -> str:
        return create_checkout_session(amount_cents)


class UserProfileService:
    """Логика работы с профилем пользователя."""

    def __init__(self, repo: UserProfileRepository):
        self.repo = repo

    def get_or_create(self, uid: str, email: Optional[str]) -> UserProfile:
        existing = self.repo.get_by_uid(uid)
        if existing:
            if email and existing.email != email:
                existing.email = email
                existing.updated_at = timezone.now()
                self.repo.upsert(existing)
            return existing

        now = timezone.now()
        profile = UserProfile(
            uid=uid,
            email=email,
            display_name="",
            city="",
            about="",
            language="en",
            created_at=now,
            updated_at=now,
        )
        return self.repo.upsert(profile)

    def update_profile(
        self,
        uid: str,
        email: Optional[str],
        display_name: Optional[str] = None,
        city: Optional[str] = None,
        about: Optional[str] = None,
        language: Optional[str] = None,
    ) -> UserProfile:
        profile = self.get_or_create(uid, email)

        if display_name is not None:
            profile.display_name = display_name.strip()
        if city is not None:
            profile.city = city.strip()
        if about is not None:
            profile.about = about.strip()
        if language is not None:
            profile.language = language.strip().lower()

        profile.updated_at = timezone.now()
        return self.repo.upsert(profile)
