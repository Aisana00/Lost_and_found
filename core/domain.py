# core/domain.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class LostItem:
    id: str
    title: str
    description: str
    location: str
    finder_contact: str
    created_at: datetime
    claimed: bool = False
    owner_message: Optional[str] = None
    owner_contact: Optional[str] = None


@dataclass
class Claim:
    item_id: str
    owner_contact: str
    message: str
    created_at: datetime
