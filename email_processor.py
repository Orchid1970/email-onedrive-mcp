# email_processor.py
"""
Gmail API helper functions:
- build_gmail_service: build authorized Gmail API service using OAuth2 token.json
- search_messages_with_attachments: find message IDs with attachments
- download_attachments_from_messages: download attachments to folder
- send_message_with_attachment: send an email with an attachment
"""
import os
import base64
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import List, Dict
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

from config import settings

# Required scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    # add more scopes if you need modify permissions
]


def build_gmail_service():
    """
    Build an authorized Gmail API service.
    Expects:
      - GOOGLE_CREDENTIALS_FILE (path to credentials.json downloaded from Google Cloud Console)
      - token file path will be settings.GOOGLE_TOKEN_FILE
      - If token file missing or expired, will run local OAuth flow.
    """
    creds = None
    token_path = settings.GOOGLE_TOKEN_FILE
    cred_path = settings.GOOGLE_CREDENTIALS_FILE

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # If no valid credentials, run local flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not creds:
            if not os.path.exists(cred_path):
                raise FileNotFoundError("Google credentials file not found. See README to create credentials.json.")
            flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
            creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(token_path, "w") as token:
                token.write(creds.to_json())

    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return service


def search_messages_with_attachments(service, query: str, max_results: int = 50) -> List[Dict]:
    """
    Search messages matching a query and return message resource dicts that have attachments.
    """
    try:
        results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        messages = results.get("messages", [])
        found = []
        for m in messages:
            msg = service.users().messages().get(userId="me", id=m["id"], format="full").execute()
            if "payload" in msg and "parts" in msg["payload"]:
                # crude check for attachment part
                parts = msg["payload"].get("parts", [])
                has_attachment = any(p.get("filename") for p in parts)
                if has_attachment:
                    found.append(msg)
        return found
    except HttpError as e:
        raise RuntimeError(f"Gmail API error during search: {e}")


def download_attachments_from_messages(service, messages: List[Dict], download_folder: str) -> List[str]:
    """
    Given messages (full message resources), downloads attachments to download_folder.
    Returns list of saved file paths.
    """
    saved_files = []
    os.makedirs(download_folder, exist_ok=True)
    for msg in messages:
        msg_id = msg["id"]
        parts = msg["payload"].get("parts", [])
        for part in parts:
            filename = part.get("filename")
            body = part.get("body", {})
            if filename:
                if "attachmentId" in body:
                    attach_id = body["attachmentId"]
                    attachment = service.users().messages().attachments().get(userId="me", messageId=msg_id, id=attach_id).execute()
                    data = attachment.get("data")
                    file_data = base64.urlsafe_b64decode(data.encode("UTF-8"))
                    save_path = os.path.join(download_folder, filename)
                    # Ensure unique filename
                    base, ext = os.path.splitext(save_path)
                    i = 1
                    while os.path.exists(save_path):
                        save_path = f"{base}_{i}{ext}"
                        i += 1
                    with open(save_path, "wb") as f:
                        f.write(file_data)
                    saved_files.append(save_path)
    return saved_files


def send_message_with_attachment(service, to: str, subject: str, body_text: str, file_path: str):
    """
    Send an email with an attachment via Gmail API.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Attachment not found: {file_path}")

    message = MIMEMultipart()
    message["to"] = to
    message["subject"] = subject
    message.attach(MIMEText(body_text, "plain"))

    with open(file_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(file_path)}"')
    message.attach(part)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    try:
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"id": sent.get("id")}
    except Exception as e:
        raise RuntimeError(f"Failed to send message: {e}")