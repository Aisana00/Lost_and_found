# core/__init__.py
from .repositories import FirestoreLostItemRepository, FirestoreClaimRepository
from .services import LostItemService, ClaimService, PaymentService

# единственный инстанс для всего приложения
lost_item_repo = FirestoreLostItemRepository()
claim_repo = FirestoreClaimRepository()

lost_item_service = LostItemService(lost_item_repo)
claim_service = ClaimService(lost_item_repo, claim_repo)
payment_service = PaymentService()
