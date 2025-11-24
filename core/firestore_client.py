# core/firestore_client.py
import os
from google.cloud import firestore
from google.oauth2 import service_account
from django.conf import settings


def get_firestore_client() -> firestore.Client:
    credentials = service_account.Credentials.from_service_account_file(
        settings.FIREBASE_CREDENTIALS_FILE
    )
    return firestore.Client(
        project=settings.FIREBASE_PROJECT_ID,
        credentials=credentials,
    )
