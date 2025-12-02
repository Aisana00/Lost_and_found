import os
from google.cloud import firestore
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv()  # чтобы прочитать .env

def get_firestore_client():
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not cred_path:
        raise RuntimeError("Переменная GOOGLE_APPLICATION_CREDENTIALS не задана")

    credentials = service_account.Credentials.from_service_account_file(cred_path)
    return firestore.Client(credentials=credentials)
