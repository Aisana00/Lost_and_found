# core/firestore_client.py
import os

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from google.cloud import firestore
from google.oauth2 import service_account


def get_firestore_client() -> firestore.Client:
    credentials_path = settings.FIREBASE_CREDENTIALS_FILE
    project_id = settings.FIREBASE_PROJECT_ID

    if not credentials_path:
        raise ImproperlyConfigured("FIREBASE_CREDENTIALS_FILE is not set in settings/.env")

    if not project_id:
        raise ImproperlyConfigured("FIREBASE_PROJECT_ID is not set in settings/.env")

    if not os.path.exists(credentials_path):
        raise ImproperlyConfigured(f"Service account file not found: {credentials_path}")

    credentials = service_account.Credentials.from_service_account_file(credentials_path)
    return firestore.Client(project=project_id, credentials=credentials)
