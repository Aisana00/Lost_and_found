# core/admin_views.py
"""
Админ-панель для управления Lost & Found.
Доступ по /api/panel/
"""
import os
from functools import wraps
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from google.api_core import exceptions as google_exceptions
from django.utils import timezone

from .repositories import (
    FirestoreLostItemRepository,
    FirestoreMessageRepository,
    FirestoreUserProfileRepository,
    FirestoreChatRepository,
)
from .domain import ITEM_CATEGORIES, CATEGORY_CHOICES, UserProfile

# Простая аутентификация админа через переменные окружения
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


def admin_required(view_func):
    """Декоратор для проверки авторизации админа."""
    @wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        if not request.session.get("is_admin"):
            return redirect("admin-login")
        return view_func(request, *args, **kwargs)
    return wrapper


@require_http_methods(["GET", "POST"])
def admin_login(request: HttpRequest):
    """Страница входа в админку."""
    error = None
    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            request.session["is_admin"] = True
            return redirect("admin-dashboard")
        else:
            error = "Неверный логин или пароль"

    return render(request, "panel/login.html", {"error": error})


@require_http_methods(["GET"])
def admin_logout(request: HttpRequest):
    """Выход из админки."""
    request.session.pop("is_admin", None)
    return redirect("admin-login")


@admin_required
@require_http_methods(["GET"])
def admin_dashboard(request: HttpRequest):
    """Главная страница админки."""
    try:
        item_repo = FirestoreLostItemRepository()
        user_repo = FirestoreUserProfileRepository()
        message_repo = FirestoreMessageRepository()

        items = item_repo.list_all()
        users = user_repo.get_all()
        all_messages = message_repo.get_all()

        stats = {
            "total_items": len(items),
            "claimed_items": len([i for i in items if i.claimed]),
            "unclaimed_items": len([i for i in items if not i.claimed]),
            "total_users": len(users),
            "total_messages": len(all_messages),
        }
    except google_exceptions.GoogleAPICallError as exc:
        stats = {"error": str(exc)}

    return render(request, "panel/dashboard.html", {"stats": stats})


@admin_required
@require_http_methods(["GET"])
def admin_items_list(request: HttpRequest):
    """Список всех вещей с фильтрацией."""
    category_filter = request.GET.get("category", "")
    claimed_filter = request.GET.get("claimed", "")

    try:
        repo = FirestoreLostItemRepository()
        items = repo.list_all()

        # Фильтрация
        if category_filter:
            items = [i for i in items if i.category == category_filter]
        if claimed_filter == "yes":
            items = [i for i in items if i.claimed]
        elif claimed_filter == "no":
            items = [i for i in items if not i.claimed]

    except google_exceptions.GoogleAPICallError as exc:
        items = []
        messages.error(request, f"Ошибка загрузки: {exc}")

    return render(request, "panel/items_list.html", {
        "items": items,
        "categories": ITEM_CATEGORIES,
        "category_filter": category_filter,
        "claimed_filter": claimed_filter,
    })


@admin_required
@require_http_methods(["GET", "POST"])
def admin_item_create(request: HttpRequest):
    """Создание новой вещи."""
    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        description = (request.POST.get("description") or "").strip()
        location = (request.POST.get("location") or "").strip()
        category = (request.POST.get("category") or "other").strip()
        finder_id = (request.POST.get("finder_id") or "").strip()

        if not title:
            messages.error(request, "Title is required")
        else:
            try:
                repo = FirestoreLostItemRepository()
                repo.create(title, description, location, finder_id, category=category)
                messages.success(request, "Item created")
                return redirect("admin-items")
            except google_exceptions.GoogleAPICallError as exc:
                messages.error(request, f"Ошибка создания: {exc}")

    return render(request, "panel/item_create.html", {"categories": ITEM_CATEGORIES})


@admin_required
@require_http_methods(["GET", "POST"])
def admin_item_messages(request: HttpRequest, item_id: str):
    """Сообщения по конкретной вещи + возможность добавить сообщение (для модерации/тестов)."""
    item_repo = FirestoreLostItemRepository()
    message_repo = FirestoreMessageRepository()
    user_repo = FirestoreUserProfileRepository()
    chat_repo = FirestoreChatRepository()

    try:
        item = item_repo.get_by_id(item_id)
        if not item:
            messages.error(request, "Вещь не найдена")
            return redirect("admin-items")

        if request.method == "POST":
            sender_id = (request.POST.get("sender_id") or "").strip()
            text = (request.POST.get("text") or "").strip()
            if not sender_id or not text:
                messages.error(request, "Sender ID and text are required")
            else:
                msg = message_repo.create(item_id, sender_id, text)
                chat = chat_repo.get_by_item_id(item_id)
                if chat:
                    chat.last_message = text
                    chat.last_message_at = msg.created_at
                    chat_repo.save(chat)
                messages.success(request, "Message created")
                return redirect("admin-item-messages", item_id=item_id)

        msgs = message_repo.get_by_item_id(item_id)
        message_rows = []
        for m in msgs:
            user = user_repo.get_by_uid(m.sender_id)
            message_rows.append({"message": m, "user": user})

    except google_exceptions.GoogleAPICallError as exc:
        item = None
        message_rows = []
        messages.error(request, f"Ошибка загрузки: {exc}")

    return render(request, "panel/item_messages.html", {"item": item, "message_rows": message_rows})


@admin_required
@require_http_methods(["GET", "POST"])
def admin_item_edit(request: HttpRequest, item_id: str):
    """Редактирование вещи."""
    repo = FirestoreLostItemRepository()

    try:
        item = repo.get_by_id(item_id)
        if not item:
            messages.error(request, "Вещь не найдена")
            return redirect("admin-items")

        if request.method == "POST":
            item.title = request.POST.get("title", item.title)
            item.description = request.POST.get("description", item.description)
            item.location = request.POST.get("location", item.location)
            item.category = request.POST.get("category", item.category)
            item.claimed = request.POST.get("claimed") == "on"

            repo.save(item)
            messages.success(request, "Вещь успешно обновлена")
            return redirect("admin-items")

    except google_exceptions.GoogleAPICallError as exc:
        messages.error(request, f"Ошибка: {exc}")
        return redirect("admin-items")

    return render(request, "panel/item_edit.html", {
        "item": item,
        "categories": ITEM_CATEGORIES,
    })


@admin_required
@require_http_methods(["POST"])
@csrf_exempt
def admin_item_delete(request: HttpRequest, item_id: str):
    """Удаление вещи."""
    try:
        repo = FirestoreLostItemRepository()
        if repo.delete(item_id):
            messages.success(request, "Вещь удалена")
        else:
            messages.error(request, "Вещь не найдена")
    except google_exceptions.GoogleAPICallError as exc:
        messages.error(request, f"Ошибка удаления: {exc}")

    return redirect("admin-items")


@admin_required
@require_http_methods(["GET"])
def admin_users_list(request: HttpRequest):
    """Список всех пользователей."""
    try:
        repo = FirestoreUserProfileRepository()
        users = repo.get_all()
    except google_exceptions.GoogleAPICallError as exc:
        users = []
        messages.error(request, f"Ошибка загрузки: {exc}")

    return render(request, "panel/users_list.html", {"users": users})


@admin_required
@require_http_methods(["GET", "POST"])
def admin_user_create(request: HttpRequest):
    """Создание/добавление профиля пользователя вручную (Firestore users/{uid})."""
    if request.method == "POST":
        uid = (request.POST.get("uid") or "").strip()
        email = (request.POST.get("email") or "").strip() or None
        display_name = (request.POST.get("display_name") or "").strip()
        city = (request.POST.get("city") or "").strip()
        about = (request.POST.get("about") or "").strip()
        language = (request.POST.get("language") or "en").strip().lower()

        if not uid:
            messages.error(request, "UID is required")
        elif language not in {"en", "ru", "kk"}:
            messages.error(request, "Language must be en/ru/kk")
        else:
            try:
                repo = FirestoreUserProfileRepository()
                now = timezone.now()
                profile = UserProfile(
                    uid=uid,
                    email=email,
                    display_name=display_name,
                    city=city,
                    about=about,
                    language=language,
                    created_at=now,
                    updated_at=now,
                )
                repo.upsert(profile)
                messages.success(request, "User profile saved")
                return redirect("admin-users")
            except google_exceptions.GoogleAPICallError as exc:
                messages.error(request, f"Ошибка создания: {exc}")

    return render(request, "panel/user_create.html")


@admin_required
@require_http_methods(["GET"])
def admin_chats_list(request: HttpRequest):
    """Список всех чатов."""
    item_id_filter = (request.GET.get("item_id") or "").strip()
    user_id_filter = (request.GET.get("user_id") or "").strip()

    try:
        chat_repo = FirestoreChatRepository()
        item_repo = FirestoreLostItemRepository()
        user_repo = FirestoreUserProfileRepository()

        chats = chat_repo.list_all()
        if item_id_filter:
            chats = [c for c in chats if c.item_id == item_id_filter]
        if user_id_filter:
            chats = [c for c in chats if c.finder_id == user_id_filter or c.claimer_id == user_id_filter]

        rows = []
        for chat in chats:
            item = item_repo.get_by_id(chat.item_id)
            finder = user_repo.get_by_uid(chat.finder_id) if chat.finder_id else None
            claimer = user_repo.get_by_uid(chat.claimer_id) if chat.claimer_id else None
            rows.append({"chat": chat, "item": item, "finder": finder, "claimer": claimer})

    except google_exceptions.GoogleAPICallError as exc:
        rows = []
        messages.error(request, f"Ошибка загрузки: {exc}")

    return render(request, "panel/chats_list.html", {
        "rows": rows,
        "item_id_filter": item_id_filter,
        "user_id_filter": user_id_filter,
    })


@admin_required
@require_http_methods(["GET", "POST"])
def admin_chat_create(request: HttpRequest):
    """Создать чат вручную (если его нет)."""
    if request.method == "POST":
        item_id = (request.POST.get("item_id") or "").strip()
        finder_id = (request.POST.get("finder_id") or "").strip()
        claimer_id = (request.POST.get("claimer_id") or "").strip()

        if not item_id or not finder_id or not claimer_id:
            messages.error(request, "Item ID, finder UID and claimer UID are required")
        else:
            try:
                chat_repo = FirestoreChatRepository()
                existing = chat_repo.get_by_item_id(item_id)
                if existing:
                    messages.info(request, "Chat already exists for this item")
                    return redirect("admin-chat-detail", chat_id=existing.id)

                chat = chat_repo.create(item_id=item_id, finder_id=finder_id, claimer_id=claimer_id)
                messages.success(request, "Chat created")
                return redirect("admin-chat-detail", chat_id=chat.id)
            except google_exceptions.GoogleAPICallError as exc:
                messages.error(request, f"Ошибка создания: {exc}")

    return render(request, "panel/chat_create.html")


@admin_required
@require_http_methods(["GET", "POST"])
def admin_chat_detail(request: HttpRequest, chat_id: str):
    """Детали чата + сообщения по item_id."""
    chat_repo = FirestoreChatRepository()
    item_repo = FirestoreLostItemRepository()
    message_repo = FirestoreMessageRepository()
    user_repo = FirestoreUserProfileRepository()

    try:
        chat = chat_repo.get_by_id(chat_id)
        if not chat:
            messages.error(request, "Chat not found")
            return redirect("admin-chats")

        item = item_repo.get_by_id(chat.item_id)
        finder = user_repo.get_by_uid(chat.finder_id) if chat.finder_id else None
        claimer = user_repo.get_by_uid(chat.claimer_id) if chat.claimer_id else None

        if request.method == "POST":
            sender_id = (request.POST.get("sender_id") or "").strip()
            text = (request.POST.get("text") or "").strip()
            if not sender_id or not text:
                messages.error(request, "Sender UID and text are required")
            else:
                msg = message_repo.create(chat.item_id, sender_id, text)
                chat.last_message = text
                chat.last_message_at = msg.created_at
                chat_repo.save(chat)
                messages.success(request, "Message sent")
                return redirect("admin-chat-detail", chat_id=chat.id)

        msgs = message_repo.get_by_item_id(chat.item_id)
        message_rows = []
        for m in msgs:
            user = user_repo.get_by_uid(m.sender_id)
            message_rows.append({"message": m, "user": user})

    except google_exceptions.GoogleAPICallError as exc:
        chat = None
        item = None
        finder = None
        claimer = None
        message_rows = []
        messages.error(request, f"Ошибка загрузки: {exc}")

    return render(request, "panel/chat_detail.html", {
        "chat": chat,
        "item": item,
        "finder": finder,
        "claimer": claimer,
        "message_rows": message_rows,
    })


@admin_required
@require_http_methods(["GET"])
def admin_user_messages(request: HttpRequest, user_id: str):
    """Все сообщения конкретного пользователя."""
    try:
        message_repo = FirestoreMessageRepository()
        user_repo = FirestoreUserProfileRepository()
        item_repo = FirestoreLostItemRepository()

        user = user_repo.get_by_uid(user_id)
        user_messages = message_repo.get_by_user(user_id)

        # Добавляем информацию о вещах к сообщениям
        messages_with_items = []
        for msg in user_messages:
            item = item_repo.get_by_id(msg.item_id)
            messages_with_items.append({
                "message": msg,
                "item": item,
            })

    except google_exceptions.GoogleAPICallError as exc:
        user = None
        messages_with_items = []
        messages.error(request, f"Ошибка загрузки: {exc}")

    return render(request, "panel/user_messages.html", {
        "user": user,
        "user_id": user_id,
        "messages_with_items": messages_with_items,
    })


@admin_required
@require_http_methods(["GET"])
def admin_messages_list(request: HttpRequest):
    """Все сообщения системы."""
    try:
        message_repo = FirestoreMessageRepository()
        user_repo = FirestoreUserProfileRepository()
        item_repo = FirestoreLostItemRepository()

        all_messages = message_repo.get_all()

        # Группируем сообщения по пользователям
        users_messages = {}
        for msg in all_messages:
            if msg.sender_id not in users_messages:
                user = user_repo.get_by_uid(msg.sender_id)
                users_messages[msg.sender_id] = {
                    "user": user,
                    "messages": [],
                    "count": 0,
                }
            item = item_repo.get_by_id(msg.item_id)
            users_messages[msg.sender_id]["messages"].append({
                "message": msg,
                "item": item,
            })
            users_messages[msg.sender_id]["count"] += 1

    except google_exceptions.GoogleAPICallError as exc:
        users_messages = {}
        messages.error(request, f"Ошибка загрузки: {exc}")

    return render(request, "panel/messages_list.html", {
        "users_messages": users_messages,
    })
