# core/repositories.py
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from .domain import LostItem, Claim
from .firestore_client import get_firestore_client
from google.cloud import firestore



class LostItemRepository(ABC):
    """Интерфейс репозитория для вещей."""

    @abstractmethod
    def create(self, title: str, description: str, location: str, finder_contact: str) -> LostItem:
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
    """Конкретная реализация для Firestore."""

    def __init__(self):
        self.client = get_firestore_client()
        self.collection = self.client.collection("lost_items")

    def _doc_to_entity(self, doc) -> LostItem:
        data = doc.to_dict()
        return LostItem(
            id=doc.id,
            title=data["title"],
            description=data.get("description", ""),
            location=data.get("location", ""),
            finder_contact=data.get("finder_contact", ""),
            created_at=data.get("created_at", datetime.utcnow()),
            claimed=data.get("claimed", False),
            owner_message=data.get("owner_message"),
            owner_contact=data.get("owner_contact"),
        )

    def create(self, title: str, description: str, location: str, finder_contact: str) -> LostItem:
        now = datetime.utcnow()
        doc_ref = self.collection.document()
        doc_ref.set(
            {
                "title": title,
                "description": description,
                "location": location,
                "finder_contact": finder_contact,
                "created_at": now,
                "claimed": False,
                "owner_message": None,
                "owner_contact": None,
            }
        )
        return LostItem(
            id=doc_ref.id,
            title=title,
            description=description,
            location=location,
            finder_contact=finder_contact,
            created_at=now,
        )

    def list_all(self) -> List[LostItem]:
        docs = self.collection.order_by("created_at", direction=firestore.Query.DESCENDING).stream()
        return [self._doc_to_entity(doc) for doc in docs]

    def get_by_id(self, item_id: str) -> Optional[LostItem]:
        doc = self.collection.document(item_id).get()
        if not doc.exists:
            return None
        return self._doc_to_entity(doc)

    def save(self, item: LostItem) -> None:
        self.collection.document(item.id).update(
            {
                "title": item.title,
                "description": item.description,
                "location": item.location,
                "finder_contact": item.finder_contact,
                "created_at": item.created_at,
                "claimed": item.claimed,
                "owner_message": item.owner_message,
                "owner_contact": item.owner_contact,
            }
        )


class ClaimRepository(ABC):
    """Интерфейс репозитория заявок на вещь (чтобы отделить ответственность)."""

    @abstractmethod
    def create(self, item_id: str, owner_contact: str, message: str) -> Claim:
        ...


class FirestoreClaimRepository(ClaimRepository):
    def __init__(self):
        self.client = get_firestore_client()
        self.collection = self.client.collection("claims")

    def create(self, item_id: str, owner_contact: str, message: str) -> Claim:
        now = datetime.utcnow()
        doc_ref = self.collection.document()
        doc_ref.set(
            {
                "item_id": item_id,
                "owner_contact": owner_contact,
                "message": message,
                "created_at": now,
            }
        )
        return Claim(
            item_id=item_id,
            owner_contact=owner_contact,
            message=message,
            created_at=now,
        )
