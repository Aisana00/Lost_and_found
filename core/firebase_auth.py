# core/firebase_auth.py
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
import firebase_admin
from firebase_admin import auth, credentials


def _get_app():
    """
    Инициализирует Firebase Admin с service account из настроек.
    Повторные вызовы возвращают уже созданный app.
    """
    cred_path = settings.FIREBASE_CREDENTIALS_FILE
    project_id = settings.FIREBASE_PROJECT_ID

    if not cred_path:
        raise ImproperlyConfigured("FIREBASE_CREDENTIALS_FILE is not set")
    if not project_id:
        raise ImproperlyConfigured("FIREBASE_PROJECT_ID is not set")

    try:
        return firebase_admin.get_app()
    except ValueError:
        cred = credentials.Certificate(cred_path)
        return firebase_admin.initialize_app(cred, {"projectId": project_id})


def verify_firebase_token(id_token: str) -> dict:
    """
    Проверяет Firebase ID token и возвращает его claims (uid, email, ...).
    Бросает исключения firebase_admin.auth при невалидном токене.
    """
    app = _get_app()
    # clock_skew_seconds даёт допуск на небольшое расхождение часов (например, на эмуляторах/устройствах)
    return auth.verify_id_token(id_token, app=app, clock_skew_seconds=60)

