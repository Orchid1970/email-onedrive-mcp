# onedrive_handler.py
"""
OneDrive / Microsoft Graph helpers.

This example uses MSAL for acquiring tokens and the Graph upload endpoint for file content.

Two typical patterns:
- Delegated user auth (device code or auth code) - stores token in msal_token.json
- Client credentials (app-only) for app with application permissions (requires tenant, client secret)

This file implements a simple MSAL device flow for delegated permissions, and an upload helper.
"""
import os
import json
import requests
from msal import PublicClientApplication, ConfidentialClientApplication
from typing import Dict
from config import settings

MSAL_TOKEN_PATH = settings.MSAL_TOKEN_FILE


def _load_msal_app():
    # If CLIENT_SECRET present -> use ConfidentialClientApplication (client credentials)
    if settings.MSFT_CLIENT_SECRET:
        app = ConfidentialClientApplication(
            settings.MSFT_CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{settings.MSFT_TENANT_ID}",
            client_credential=settings.MSFT_CLIENT_SECRET,
        )
    else:
        # Public client for device code flow
        app = PublicClientApplication(
            settings.MSFT_CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{settings.MSFT_TENANT_ID}",
        )
    return app


def get_onedrive_access_token(scopes=None) -> Dict:
    """
    Acquire or load a token for Microsoft Graph.
    Returns a dict with access_token and expires_in etc.
    """
    if scopes is None:
        scopes = settings.MSFT_SCOPES

    app = _load_msal_app()

    accounts = app.get_accounts()
    result = None
    if accounts:
        # try silent
        result = app.acquire_token_silent(scopes, account=accounts[0])

    if not result:
        if settings.MSFT_CLIENT_SECRET:
            # client credentials flow (app-only)
            result = app.acquire_token_for_client(scopes=scopes)
        else:
            # device code flow for user-delegated
            flow = app.initiate_device_flow(scopes=scopes)
            if "user_code" not in flow:
                raise RuntimeError("Failed to create device flow. Check MSAL configuration.")
            print(f"To authenticate, visit {flow['verification_uri']} and enter code: {flow['user_code']}")
            result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(f"Could not obtain access token: {result}")

    # Optionally persist token to disk (msal manages caching if you pass a cache)
    return result


def upload_file_to_onedrive_path(token_response: Dict, local_path: str, remote_path: str) -> Dict:
    """
    Uploads a file to OneDrive at remote_path (path relative to drive root).
    Uses the simple upload (if < 4MB) or the simple upload for smaller files. For large files, resumable upload needed.
    remote_path example: "MyFolder/file.pdf" (no leading slash)
    """
    access_token = token_response.get("access_token")
    if not access_token:
        raise RuntimeError("Missing access token")

    # Ensure remote path is URL encoded properly
    # Use Graph API: /me/drive/root:/remote_path:/content
    url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{remote_path}:/content"
    headers = {"Authorization": f"Bearer {access_token}"}
    with open(local_path, "rb") as f:
        data = f.read()
    resp = requests.put(url, headers=headers, data=data)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"OneDrive upload failed: {resp.status_code} - {resp.text}")
    return resp.json()