# core/urls.py
from django.urls import path

from . import views
from . import admin_views

urlpatterns = [
    path("items/", views.list_items_view, name="items-list"),
    path("items/create/", views.create_item_view, name="items-create"),
    path("items/my/", views.list_user_items_view, name="items-my"),
    path("items/claimed/", views.list_claimed_items_view, name="items-claimed"),
    path("items/<str:item_id>/", views.item_detail_view, name="items-detail"),
    path("items/<str:item_id>/claim/", views.create_claim_view, name="items-claim"),
    path("payments/reward/", views.create_reward_payment_view, name="payments-reward"),
    path("profile/", views.profile_view, name="profile"),
    # Chat endpoints
    path("chats/", views.list_user_chats_view, name="chats-list"),
    path("chats/<str:item_id>/messages/", views.get_chat_messages_view, name="chat-messages"),
    path("chats/<str:item_id>/messages/send/", views.send_message_view, name="chat-send"),
    # Categories
    path("categories/", views.get_categories_view, name="categories-list"),
    # Admin panel
    path("panel/", admin_views.admin_dashboard, name="admin-dashboard"),
    path("panel/items/", admin_views.admin_items_list, name="admin-items"),
    path("panel/items/create/", admin_views.admin_item_create, name="admin-item-create"),
    path("panel/items/<str:item_id>/edit/", admin_views.admin_item_edit, name="admin-item-edit"),
    path("panel/items/<str:item_id>/messages/", admin_views.admin_item_messages, name="admin-item-messages"),
    path("panel/items/<str:item_id>/delete/", admin_views.admin_item_delete, name="admin-item-delete"),
    path("panel/users/", admin_views.admin_users_list, name="admin-users"),
    path("panel/users/create/", admin_views.admin_user_create, name="admin-user-create"),
    path("panel/users/<str:user_id>/messages/", admin_views.admin_user_messages, name="admin-user-messages"),
    path("panel/messages/", admin_views.admin_messages_list, name="admin-messages"),
    path("panel/chats/", admin_views.admin_chats_list, name="admin-chats"),
    path("panel/chats/create/", admin_views.admin_chat_create, name="admin-chat-create"),
    path("panel/chats/<str:chat_id>/", admin_views.admin_chat_detail, name="admin-chat-detail"),
    path("panel/login/", admin_views.admin_login, name="admin-login"),
    path("panel/logout/", admin_views.admin_logout, name="admin-logout"),
]
