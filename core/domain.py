# core/domain.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Tuple


# Категории вещей
ITEM_CATEGORIES: List[Tuple[str, str]] = [
    ("electronics", "Электроника"),
    ("clothing", "Одежда"),
    ("accessories", "Аксессуары"),
    ("documents", "Документы"),
    ("keys", "Ключи"),
    ("bags", "Сумки/Рюкзаки"),
    ("other", "Другое"),
]

CATEGORY_CHOICES = [cat[0] for cat in ITEM_CATEGORIES]


@dataclass
class LostItem:
    id: str
    title: str
    description: str
    location: str
    finder_id: str  # Firebase UID of finder
    created_at: datetime
    claimed: bool = False
    category: str = "other"


@dataclass
class Claim:
    id: str
    item_id: str
    claimer_id: str  # Firebase UID of person claiming
    created_at: datetime


@dataclass
class Message:
    id: str
    item_id: str
    sender_id: str  # Firebase UID
    text: str
    created_at: datetime
    read: bool = False


@dataclass
class Chat:
    id: str
    item_id: str
    finder_id: str
    claimer_id: str
    created_at: datetime
    last_message: Optional[str] = None
    last_message_at: Optional[datetime] = None


@dataclass
class UserProfile:
    uid: str
    email: Optional[str]
    display_name: str = ""
    city: str = ""
    about: str = ""
    language: str = "en"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
