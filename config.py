# config.py
import os
from dotenv import load_dotenv
from pydantic import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    GOOGLE_CREDENTIALS_FILE: str = os.environ.get("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    GOOGLE_TOKEN_FILE: str = os.environ.get("GOOGLE_TOKEN_FILE", "token.json")

    MSFT_CLIENT_ID: str = os.environ.get("MSFT_CLIENT_ID", "")
    MSFT_CLIENT_SECRET: str = os.environ.get("MSFT_CLIENT_SECRET", "")
    MSFT_TENANT_ID: str = os.environ.get("MSFT_TENANT_ID", "common")
    MSAL_TOKEN_FILE: str = os.environ.get("MSAL_TOKEN_FILE", "msal_token.json")

    # Default MS Graph scopes used
    MSFT_SCOPES = ["https://graph.microsoft.com/.default"] if MSFT_CLIENT_SECRET else ["Files.ReadWrite.All", "offline_access", "User.Read"]

    PORT: int = int(os.environ.get("PORT", 8000))


settings = Settings()