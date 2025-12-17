# core/repositories.py
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime

from google.cloud import firestore
from django.utils import timezone

from .domain import LostItem, Claim, Message, Chat, UserProfile, CATEGORY_CHOICES
from .firestore_client import get_firestore_client


class LostItemRepository(ABC):
    """Интерфейс репозитория для вещей."""

    @abstractmethod
    def create(self, title: str, description: str, location: str, finder_id: str, category: str = "other") -> LostItem:
        ...

    @abstractmethod
    def list_all(self) -> List[LostItem]:
        ...

    @abstractmethod
    def list_filtered(self, category: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[LostItem]:
        ...

    @abstractmethod
    def get_by_id(self, item_id: str) -> Optional[LostItem]:
        ...

    @abstractmethod
    def save(self, item: LostItem) -> None:
        ...

    @abstractmethod
    def delete(self, item_id: str) -> bool:
        ...


class FirestoreLostItemRepository(LostItemRepository):
    """Реализация репозитория вещей на Firestore."""

    def __init__(self):
        self.client = get_firestore_client()
        self.collection = self.client.collection("lost_items")  # коллекция создастся автоматически при первой записи

    def _doc_to_entity(self, doc: firestore.DocumentSnapshot) -> LostItem:
        data = doc.to_dict() or {}

        title = data.get("title")
        if not isinstance(title, str) or not title.strip():
            title = "(untitled)"

        description = data.get("description", "")
        if not isinstance(description, str):
            description = str(description)

        location = data.get("location", "")
        if not isinstance(location, str):
            location = str(location)

        finder_id = data.get("finder_id", "")
        if not isinstance(finder_id, str):
            finder_id = str(finder_id)

        category = data.get("category", "other")
        if not isinstance(category, str) or category not in CATEGORY_CHOICES:
            category = "other"

        created_at = data.get("created_at")
        if not isinstance(created_at, datetime):
            created_at = timezone.now()

        return LostItem(
            id=doc.id,
            title=title,
            description=description,
            location=location,
            finder_id=finder_id,
            created_at=created_at,
            claimed=bool(data.get("claimed", False)),
            category=category,
        )

    def create(self, title: str, description: str, location: str, finder_id: str, category: str = "other") -> LostItem:
        now = timezone.now()
        # Валидация категории
        if category not in CATEGORY_CHOICES:
            category = "other"
        doc_ref = self.collection.document()  # создаём новый ID
        doc_ref.set(
            {
                "title": title,
                "description": description,
                "location": location,
                "finder_id": finder_id,
                "created_at": now,
                "claimed": False,
                "category": category,
            }
        )
        return LostItem(
            id=doc_ref.id,
            title=title,
            description=description,
            location=location,
            finder_id=finder_id,
            created_at=now,
            category=category,
        )

    def list_all(self) -> List[LostItem]:
        docs = (
            self.collection.order_by("created_at", direction=firestore.Query.DESCENDING)
            .stream()
        )
        return [self._doc_to_entity(doc) for doc in docs]

    def list_filtered(self, category: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[LostItem]:
        """Получить список вещей с фильтрацией."""
        from datetime import date

        # Получаем все документы и фильтруем в Python
        # (Firestore ограничен в составных запросах без индексов)
        items = self.list_all()

        # Фильтр по категории
        if category and category in CATEGORY_CHOICES:
            items = [item for item in items if item.category == category]

        # Фильтр по дате "от"
        if date_from:
            try:
                d_from = date.fromisoformat(date_from)
                items = [item for item in items if item.created_at.date() >= d_from]
            except ValueError:
                pass

        # Фильтр по дате "до"
        if date_to:
            try:
                d_to = date.fromisoformat(date_to)
                items = [item for item in items if item.created_at.date() <= d_to]
            except ValueError:
                pass

        return items

    def get_by_id(self, item_id: str) -> Optional[LostItem]:
        doc = self.collection.document(item_id).get()
        if not doc.exists:
            return None
        return self._doc_to_entity(doc)

    def save(self, item: LostItem) -> None:
        self.collection.document(item.id).set(
            {
                "title": item.title,
                "description": item.description,
                "location": item.location,
                "finder_id": item.finder_id,
                "created_at": item.created_at,
                "claimed": item.claimed,
                "category": item.category,
            },
            merge=True,
        )

    def delete(self, item_id: str) -> bool:
        """Удалить вещь по ID."""
        doc_ref = self.collection.document(item_id)
        doc = doc_ref.get()
        if not doc.exists:
            return False
        doc_ref.delete()
        return True


class ClaimRepository(ABC):
    """Интерфейс репозитория заявок владельцев."""

    @abstractmethod
    def create(self, item_id: str, claimer_id: str) -> Claim:
        ...

    @abstractmethod
    def get_by_item_id(self, item_id: str) -> Optional[Claim]:
        ...

    @abstractmethod
    def list_by_claimer_id(self, claimer_id: str) -> List[Claim]:
        ...


class FirestoreClaimRepository(ClaimRepository):
    """Репозиторий заявок в коллекции 'claims'."""

    def __init__(self):
        self.client = get_firestore_client()
        self.collection = self.client.collection("claims")

    def create(self, item_id: str, claimer_id: str) -> Claim:
        now = timezone.now()
        doc_ref = self.collection.document()
        doc_ref.set(
            {
                "item_id": item_id,
                "claimer_id": claimer_id,
                "created_at": now,
            }
        )
        return Claim(
            id=doc_ref.id,
            item_id=item_id,
            claimer_id=claimer_id,
            created_at=now,
        )

    def get_by_item_id(self, item_id: str) -> Optional[Claim]:
        docs = self.collection.where("item_id", "==", item_id).limit(1).stream()
        for doc in docs:
            data = doc.to_dict() or {}
            return Claim(
                id=doc.id,
                item_id=data.get("item_id", ""),
                claimer_id=data.get("claimer_id", ""),
                created_at=data.get("created_at", timezone.now()),
            )
        return None

    def list_by_claimer_id(self, claimer_id: str) -> List[Claim]:
        # Получаем без order_by чтобы избежать требования индекса (Firestore composite index).
        docs = self.collection.where("claimer_id", "==", claimer_id).stream()
        claims: List[Claim] = []
        for doc in docs:
            data = doc.to_dict() or {}
            claims.append(
                Claim(
                    id=doc.id,
                    item_id=data.get("item_id", ""),
                    claimer_id=data.get("claimer_id", ""),
                    created_at=data.get("created_at", timezone.now()),
                )
            )
        return sorted(claims, key=lambda c: c.created_at, reverse=True)


class ChatRepository(ABC):
    """Интерфейс репозитория чатов."""

    @abstractmethod
    def create(self, item_id: str, finder_id: str, claimer_id: str) -> Chat:
        ...

    @abstractmethod
    def get_by_item_id(self, item_id: str) -> Optional[Chat]:
        ...

    @abstractmethod
    def get_user_chats(self, user_id: str) -> List[Chat]:
        ...

    @abstractmethod
    def save(self, chat: Chat) -> None:
        ...


class FirestoreChatRepository(ChatRepository):
    """Репозиторий чатов в Firestore."""

    def __init__(self):
        self.client = get_firestore_client()
        self.collection = self.client.collection("chats")

    def create(self, item_id: str, finder_id: str, claimer_id: str) -> Chat:
        now = timezone.now()
        doc_ref = self.collection.document()
        doc_ref.set(
            {
                "item_id": item_id,
                "finder_id": finder_id,
                "claimer_id": claimer_id,
                "created_at": now,
                "last_message": None,
                "last_message_at": None,
            }
        )
        return Chat(
            id=doc_ref.id,
            item_id=item_id,
            finder_id=finder_id,
            claimer_id=claimer_id,
            created_at=now,
        )

    def get_by_item_id(self, item_id: str) -> Optional[Chat]:
        docs = self.collection.where("item_id", "==", item_id).limit(1).stream()
        for doc in docs:
            data = doc.to_dict() or {}
            return Chat(
                id=doc.id,
                item_id=data.get("item_id", ""),
                finder_id=data.get("finder_id", ""),
                claimer_id=data.get("claimer_id", ""),
                created_at=data.get("created_at", timezone.now()),
                last_message=data.get("last_message"),
                last_message_at=data.get("last_message_at"),
            )
        return None

    def get_user_chats(self, user_id: str) -> List[Chat]:
        # Get chats where user is either finder or claimer
        docs1 = self.collection.where("finder_id", "==", user_id).stream()
        docs2 = self.collection.where("claimer_id", "==", user_id).stream()

        chats = []
        for doc in docs1:
            data = doc.to_dict() or {}
            chats.append(Chat(
                id=doc.id,
                item_id=data.get("item_id", ""),
                finder_id=data.get("finder_id", ""),
                claimer_id=data.get("claimer_id", ""),
                created_at=data.get("created_at", timezone.now()),
                last_message=data.get("last_message"),
                last_message_at=data.get("last_message_at"),
            ))

        for doc in docs2:
            data = doc.to_dict() or {}
            chats.append(Chat(
                id=doc.id,
                item_id=data.get("item_id", ""),
                finder_id=data.get("finder_id", ""),
                claimer_id=data.get("claimer_id", ""),
                created_at=data.get("created_at", timezone.now()),
                last_message=data.get("last_message"),
                last_message_at=data.get("last_message_at"),
            ))

        return sorted(chats, key=lambda c: c.last_message_at or c.created_at, reverse=True)

    def save(self, chat: Chat) -> None:
        self.collection.document(chat.id).set(
            {
                "item_id": chat.item_id,
                "finder_id": chat.finder_id,
                "claimer_id": chat.claimer_id,
                "created_at": chat.created_at,
                "last_message": chat.last_message,
                "last_message_at": chat.last_message_at,
            },
            merge=True,
        )

    def get_by_id(self, chat_id: str) -> Optional[Chat]:
        doc = self.collection.document(chat_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        return Chat(
            id=doc.id,
            item_id=data.get("item_id", ""),
            finder_id=data.get("finder_id", ""),
            claimer_id=data.get("claimer_id", ""),
            created_at=data.get("created_at", timezone.now()),
            last_message=data.get("last_message"),
            last_message_at=data.get("last_message_at"),
        )

    def list_all(self) -> List[Chat]:
        docs = self.collection.stream()
        chats: List[Chat] = []
        for doc in docs:
            data = doc.to_dict() or {}
            chats.append(
                Chat(
                    id=doc.id,
                    item_id=data.get("item_id", ""),
                    finder_id=data.get("finder_id", ""),
                    claimer_id=data.get("claimer_id", ""),
                    created_at=data.get("created_at", timezone.now()),
                    last_message=data.get("last_message"),
                    last_message_at=data.get("last_message_at"),
                )
            )
        return sorted(chats, key=lambda c: c.last_message_at or c.created_at, reverse=True)


class MessageRepository(ABC):
    """Интерфейс репозитория сообщений."""

    @abstractmethod
    def create(self, item_id: str, sender_id: str, text: str) -> Message:
        ...

    @abstractmethod
    def get_by_item_id(self, item_id: str) -> List[Message]:
        ...

    @abstractmethod
    def get_all(self) -> List[Message]:
        ...

    @abstractmethod
    def get_by_user(self, user_id: str) -> List[Message]:
        ...


class FirestoreMessageRepository(MessageRepository):
    """Репозиторий сообщений в Firestore."""

    def __init__(self):
        self.client = get_firestore_client()
        self.collection = self.client.collection("messages")

    def create(self, item_id: str, sender_id: str, text: str) -> Message:
        now = timezone.now()
        doc_ref = self.collection.document()
        doc_ref.set(
            {
                "item_id": item_id,
                "sender_id": sender_id,
                "text": text,
                "created_at": now,
                "read": False,
            }
        )
        return Message(
            id=doc_ref.id,
            item_id=item_id,
            sender_id=sender_id,
            text=text,
            created_at=now,
            read=False,
        )

    def get_by_item_id(self, item_id: str) -> List[Message]:
        # Получаем без order_by чтобы избежать требования индекса
        docs = self.collection.where("item_id", "==", item_id).stream()
        messages = []
        for doc in docs:
            data = doc.to_dict() or {}
            messages.append(Message(
                id=doc.id,
                item_id=data.get("item_id", ""),
                sender_id=data.get("sender_id", ""),
                text=data.get("text", ""),
                created_at=data.get("created_at", timezone.now()),
                read=data.get("read", False),
            ))
        # Сортируем в Python
        return sorted(messages, key=lambda m: m.created_at)

    def get_all(self) -> List[Message]:
        """Получить все сообщения (для админки)."""
        docs = self.collection.order_by("created_at", direction=firestore.Query.DESCENDING).stream()
        messages = []
        for doc in docs:
            data = doc.to_dict() or {}
            messages.append(Message(
                id=doc.id,
                item_id=data.get("item_id", ""),
                sender_id=data.get("sender_id", ""),
                text=data.get("text", ""),
                created_at=data.get("created_at", timezone.now()),
                read=data.get("read", False),
            ))
        return messages

    def get_by_user(self, user_id: str) -> List[Message]:
        """Получить все сообщения пользователя (для админки)."""
        docs = self.collection.where("sender_id", "==", user_id).stream()
        messages = []
        for doc in docs:
            data = doc.to_dict() or {}
            messages.append(Message(
                id=doc.id,
                item_id=data.get("item_id", ""),
                sender_id=data.get("sender_id", ""),
                text=data.get("text", ""),
                created_at=data.get("created_at", timezone.now()),
                read=data.get("read", False),
            ))
        return sorted(messages, key=lambda m: m.created_at, reverse=True)


class UserProfileRepository(ABC):
    """Интерфейс репозитория профиля пользователя."""

    @abstractmethod
    def get_by_uid(self, uid: str) -> Optional[UserProfile]:
        ...

    @abstractmethod
    def upsert(self, profile: UserProfile) -> UserProfile:
        ...

    @abstractmethod
    def get_all(self) -> List[UserProfile]:
        ...


class FirestoreUserProfileRepository(UserProfileRepository):
    """Профиль пользователя в коллекции 'users' (doc id = uid)."""

    def __init__(self):
        self.client = get_firestore_client()
        self.collection = self.client.collection("users")

    def get_by_uid(self, uid: str) -> Optional[UserProfile]:
        doc = self.collection.document(uid).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        return UserProfile(
            uid=uid,
            email=data.get("email"),
            display_name=data.get("display_name", ""),
            city=data.get("city", ""),
            about=data.get("about", ""),
            language=data.get("language", "en"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    def upsert(self, profile: UserProfile) -> UserProfile:
        self.collection.document(profile.uid).set(
            {
                "email": profile.email,
                "display_name": profile.display_name,
                "city": profile.city,
                "about": profile.about,
                "language": profile.language,
                "created_at": profile.created_at,
                "updated_at": profile.updated_at,
            },
            merge=True,
        )
        return profile

    def get_all(self) -> List[UserProfile]:
        """Получить всех пользователей (для админки)."""
        docs = self.collection.stream()
        users = []
        for doc in docs:
            data = doc.to_dict() or {}
            users.append(UserProfile(
                uid=doc.id,
                email=data.get("email"),
                display_name=data.get("display_name", ""),
                city=data.get("city", ""),
                about=data.get("about", ""),
                language=data.get("language", "en"),
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at"),
            ))
        return sorted(users, key=lambda u: u.created_at or timezone.now(), reverse=True)
