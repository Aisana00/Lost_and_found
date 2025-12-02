# core/firestore_client.py

import os
from pathlib import Path

from google.cloud import firestore
from google.oauth2 import service_account
from dotenv import load_dotenv


# Базовая директория проекта (где лежит manage.py)
BASE_DIR = Path(__file__).resolve().parent.parent

# Подгружаем .env (если уже грузишь в settings.py – не страшно, будет второй раз)
load_dotenv(BASE_DIR / ".env")


def get_firestore_client() -> firestore.Client:
    """
    Возвращает клиента Firestore, используя сервисный аккаунт из JSON-файла.
    Путь берётся из переменной окружения GOOGLE_APPLICATION_CREDENTIALS.
    """

    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if not cred_path:
        raise RuntimeError(
            "Переменная окружения GOOGLE_APPLICATION_CREDENTIALS не задана. "
            "Добавь её в .env"
        )

    # Поддержка относительных путей и ~
    cred_path = os.path.expanduser(cred_path)
    if not os.path.isabs(cred_path):
        cred_path = os.path.join(BASE_DIR, cred_path)

    if not os.path.exists(cred_path):
        raise FileNotFoundError(
            f"Файл сервисного аккаунта не найден по пути: {cred_path}"
        )

    credentials = service_account.Credentials.from_service_account_file(cred_path)

    # project_id можно взять из credentials, если он там есть
    client = firestore.Client(
        project=credentials.project_id,
        credentials=credentials,
    )

    return client
