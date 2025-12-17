# core/repositories.py
from abc import ABC, abstractmethod
from typing import List, Optional

from google.cloud import firestore
from django.utils import timezone

from .domain import LostItem, Claim, Message, Chat, UserProfile
from .firestore_client import get_firestore_client


class LostItemRepository(ABC):
    """Интерфейс репозитория для вещей."""

    @abstractmethod
    def create(self, title: str, description: str, location: str, finder_id: str) -> LostItem:
        ...

    @abstractmethod
    def list_all(self) -> List[LostItem]:
        ...

    @abstractmethod
    def get_by_id(self, item_id: str) -> Optional[LostItem]:
        ...

    @abstractmethod
    def save(self, item: LostItem) -> None:
        ...


class FirestoreLostItemRepository(LostItemRepository):
    """Реализация репозитория вещей на Firestore."""

    def __init__(self):
        self.client = get_firestore_client()
        self.collection = self.client.collection("lost_items")  # коллекция создастся автоматически при первой записи

    def _doc_to_entity(self, doc: firestore.DocumentSnapshot) -> LostItem:
        data = doc.to_dict() or {}
        return LostItem(
            id=doc.id,
            title=data["title"],
            description=data.get("description", ""),
            location=data.get("location", ""),
            finder_id=data.get("finder_id", ""),
            created_at=data.get("created_at", timezone.now()),
            claimed=data.get("claimed", False),
        )

    def create(self, title: str, description: str, location: str, finder_id: str) -> LostItem:
        now = timezone.now()
        doc_ref = self.collection.document()  # создаём новый ID
        doc_ref.set(
            {
                "title": title,
                "description": description,
                "location": location,
                "finder_id": finder_id,
                "created_at": now,
                "claimed": False,
            }
        )
        return LostItem(
            id=doc_ref.id,
            title=title,
            description=description,
            location=location,
            finder_id=finder_id,
            created_at=now,
        )

    def list_all(self) -> List[LostItem]:
        docs = (
            self.collection.order_by("created_at", direction=firestore.Query.DESCENDING)
            .stream()
        )
        return [self._doc_to_entity(doc) for doc in docs]

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
            },
            merge=True,
        )


class ClaimRepository(ABC):
    """Интерфейс репозитория заявок владельцев."""

    @abstractmethod
    def create(self, item_id: str, claimer_id: str) -> Claim:
        ...

    @abstractmethod
    def get_by_item_id(self, item_id: str) -> Optional[Claim]:
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


class MessageRepository(ABC):
    """Интерфейс репозитория сообщений."""

    @abstractmethod
    def create(self, item_id: str, sender_id: str, text: str) -> Message:
        ...

    @abstractmethod
    def get_by_item_id(self, item_id: str) -> List[Message]:
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
        docs = (
            self.collection
            .where("item_id", "==", item_id)
            .order_by("created_at", direction=firestore.Query.ASCENDING)
            .stream()
        )
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


class UserProfileRepository(ABC):
    """Интерфейс репозитория профиля пользователя."""

    @abstractmethod
    def get_by_uid(self, uid: str) -> Optional[UserProfile]:
        ...

    @abstractmethod
    def upsert(self, profile: UserProfile) -> UserProfile:
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
