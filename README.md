# MCP Email -> OneDrive Pipeline (Python)

## Overview

This project provides a Model Context Protocol (MCP)-style server implemented with FastAPI.
It exposes tools to:
1. Search Gmail for messages with attachments and download attachments
2. Upload attachments to OneDrive
3. Compress files into a zip archive
4. Send the zip as an email attachment
5. Orchestrate the entire pipeline in one call

## Security note

Do NOT commit credentials or token files. Use environment variables (.env) and follow the steps below to create credentials for Google and Microsoft.

## Setup

### 1) Clone repository and create a Python virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Environment variables

Copy `.env.example` -> `.env` and edit values.

`.env` should contain:
- `GOOGLE_CREDENTIALS_FILE`: path to Google OAuth client credentials JSON (download from Google Cloud Console)
- `GOOGLE_TOKEN_FILE`: path where the token will be stored (default: token.json)
- `MSFT_CLIENT_ID`, `MSFT_CLIENT_SECRET` (optional), `MSFT_TENANT_ID`
- `MSAL_TOKEN_FILE`: token cache file (optional)
- OTHER settings as needed

### 3) Google API (Gmail)

- Go to https://console.developers.google.com/ and create a project.
- Enable Gmail API.
- Create OAuth 2.0 Client ID credentials (Desktop app).
- Download the credentials JSON and set `GOOGLE_CREDENTIALS_FILE` to its path.
- The first time you run the server and call a tool that uses Gmail, you will be prompted to authenticate in your browser. A `token.json` file will be written.

Required OAuth scopes used by this code:
- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/gmail.send`

### 4) Microsoft Graph / OneDrive

**Option A: Delegated (recommended for personal/dev)**
- Register an app in Azure Portal (App registrations).
- Set redirect URI if using auth code flow, or use device code flow.
- Make note of CLIENT_ID and TENANT_ID.
- Configure API permissions for Microsoft Graph: Files.ReadWrite (delegated)
- For device flow, the code will print instructions and you will authenticate in the browser.

**Option B: Client credentials (app-only, organization tenants only)**
- Create a client secret for your app.
- Grant application permissions (Files.ReadWrite.All) and have admin consent.
- Provide `MSFT_CLIENT_SECRET` in `.env` and the code will use client credentials flow.

### 5) Running the server

```bash
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

**Endpoints:**
- `GET /mcp/tools` -> List available tools (MCP-style metadata)
- `POST /mcp/run` -> Run a tool

**Request JSON:**
```json
{
  "tool": "orchestrate_full_pipeline",
  "input": {
    "query": "has:attachment",
    "max_results": 50,
    "onedrive_folder": "MyFolder/Sub",
    "recipient_email": "recipient@example.com",
    "zip_name": "exports_2025_10_01"
  }
}
```

## Examples

### 1) Search & download attachments

```bash
POST /mcp/run
{
  "tool": "search_and_download_attachments",
  "input": {
    "query": "has:attachment newer_than:7d",
    "max_results": 50
  }
}
```

### 2) Full pipeline (search -> upload -> zip -> send)

```bash
POST /mcp/run
{
  "tool": "orchestrate_full_pipeline",
  "input": {
    "query": "has:attachment from:someone@example.com",
    "max_results": 100,
    "onedrive_folder": "Backups/EmailAttachments",
    "recipient_email": "other@example.com",
    "zip_name": "attachments_backup_oct2025"
  }
}
```

## Notes & Limitations

- OneDrive upload here uses a simple PUT to `/me/drive/root:/path:/content` which is OK for small files. For large files (>4MB) you should implement resumable uploads (upload session).
- Gmail download logic inspects message payload parts for attachments; more complex MIME trees may require recursive descent.
- Token persistence: this example keeps token files locally (token.json and MSAL caches). Use secure stores for production.
- The MCP tool definitions are an approximation. If you have a specific MCP spec version you want exact conformance to, share it and I will adjust the JSON schema fields.

## Support

If you want, I can:
- Add resumable upload support for large files
- Add logging, metrics, and retries
- Package the server as a Docker image