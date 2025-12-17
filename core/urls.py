# core/urls.py
from django.urls import path

from . import views

urlpatterns = [
    path("items/", views.list_items_view, name="items-list"),
    path("items/create/", views.create_item_view, name="items-create"),
    path("items/my/", views.list_user_items_view, name="items-my"),
    path("items/<str:item_id>/", views.item_detail_view, name="items-detail"),
    path("items/<str:item_id>/claim/", views.create_claim_view, name="items-claim"),
    path("payments/reward/", views.create_reward_payment_view, name="payments-reward"),
    path("profile/", views.profile_view, name="profile"),
    # Chat endpoints
    path("chats/", views.list_user_chats_view, name="chats-list"),
    path("chats/<str:item_id>/messages/", views.get_chat_messages_view, name="chat-messages"),
    path("chats/<str:item_id>/messages/send/", views.send_message_view, name="chat-send"),
]
