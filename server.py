# server.py
"""
MCP-style server exposing tools for:
- searching Gmail attachments
- uploading attachments to OneDrive
- compressing files
- sending zip via email

Implements a simple MCP-like tool registry with JSON schemas for inputs.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uvicorn
import os
import tempfile
import shutil

from email_processor import (
    build_gmail_service,
    search_messages_with_attachments,
    download_attachments_from_messages,
    send_message_with_attachment,
)
from onedrive_handler import (
    get_onedrive_access_token,
    upload_file_to_onedrive_path,
)
from file_compressor import compress_files
from config import settings

app = FastAPI(title="MCP Email <-> OneDrive Tools", version="1.0")

# Define tool metadata according to MCP-style protocol (approximate)
TOOL_DEFINITIONS = {
    "search_and_download_attachments": {
        "title": "Search Gmail and download attachments",
        "description": "Searches Gmail inbox for messages matching query and downloads attachments.",
        "input_schema": {
            "type": "object",
            "required": ["query", "max_results"],
            "properties": {
                "query": {"type": "string", "description": "Gmail search query (e.g., 'has:attachment from:someone@example.com')"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 500},
            },
        },
    },
    "upload_to_onedrive": {
        "title": "Upload files to OneDrive",
        "description": "Uploads local files to a OneDrive folder.",
        "input_schema": {
            "type": "object",
            "required": ["local_paths", "remote_folder_path"],
            "properties": {
                "local_paths": {"type": "array", "items": {"type": "string"}, "description": "List of local file paths to upload"},
                "remote_folder_path": {"type": "string", "description": "Remote path in OneDrive (e.g., 'MyFolder/Sub')"},
            },
        },
    },
    "compress_files": {
        "title": "Compress files into zip",
        "description": "Compresses a list of local files into a zip archive.",
        "input_schema": {
            "type": "object",
            "required": ["local_paths", "output_zip"],
            "properties": {
                "local_paths": {"type": "array", "items": {"type": "string"}},
                "output_zip": {"type": "string", "description": "Local path for output zip file"},
            },
        },
    },
    "send_zip_via_email": {
        "title": "Send zip via Gmail",
        "description": "Sends a zip file as an attachment via Gmail API.",
        "input_schema": {
            "type": "object",
            "required": ["to", "subject", "body", "zip_path"],
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "zip_path": {"type": "string"},
            },
        },
    },
    "orchestrate_full_pipeline": {
        "title": "Full pipeline: search -> upload -> zip -> send",
        "description": "Runs the entire pipeline: search Gmail, download attachments, upload to OneDrive, compress, and send zip.",
        "input_schema": {
            "type": "object",
            "required": ["query", "max_results", "onedrive_folder", "recipient_email", "zip_name"],
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
                "onedrive_folder": {"type": "string"},
                "recipient_email": {"type": "string"},
                "zip_name": {"type": "string"},
            },
        },
    },
}


@app.get("/mcp/tools")
def list_tools():
    """Return the tool definitions (MCP-style metadata)."""
    return {"tools": TOOL_DEFINITIONS}


class RunRequest(BaseModel):
    tool: str
    input: Dict[str, Any]


@app.post("/mcp/run")
def run_tool(req: RunRequest):
    tool = req.tool
    data = req.input
    if tool not in TOOL_DEFINITIONS:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {tool}")

    # Validate required fields quickly
    schema = TOOL_DEFINITIONS[tool]["input_schema"]
    required = schema.get("required", [])
    for r in required:
        if r not in data:
            raise HTTPException(status_code=400, detail=f"Missing required input: {r}")

    # Temporary working dir for operations
    work_dir = tempfile.mkdtemp(prefix="mcp_work_")
    try:
        if tool == "search_and_download_attachments":
            query = data["query"]
            max_results = int(data["max_results"])
            service = build_gmail_service()
            messages = search_messages_with_attachments(service, query=query, max_results=max_results)
            if not messages:
                return {"downloaded_files": []}
            files = download_attachments_from_messages(service, messages, download_folder=work_dir)
            return {"downloaded_files": files}

        elif tool == "upload_to_onedrive":
            local_paths = data["local_paths"]
            remote_folder = data["remote_folder_path"]
            token = get_onedrive_access_token()
            uploaded = []
            for lp in local_paths:
                if not os.path.isabs(lp):
                    lp = os.path.abspath(lp)
                if not os.path.exists(lp):
                    raise HTTPException(status_code=400, detail=f"Local file not found: {lp}")
                remote_path = os.path.join(remote_folder, os.path.basename(lp)).replace("\\", "/")
                res = upload_file_to_onedrive_path(token, lp, remote_path)
                uploaded.append(res)
            return {"uploaded": uploaded}

        elif tool == "compress_files":
            local_paths = data["local_paths"]
            output_zip = data["output_zip"]
            # If output_zip not absolute, place in work_dir
            if not os.path.isabs(output_zip):
                output_zip = os.path.join(work_dir, output_zip)
            compress_files(local_paths, output_zip)
            return {"zip_path": output_zip}

        elif tool == "send_zip_via_email":
            to = data["to"]
            subject = data["subject"]
            body = data["body"]
            zip_path = data["zip_path"]
            service = build_gmail_service()
            res = send_message_with_attachment(service, to, subject, body, zip_path)
            return {"result": res}

        elif tool == "orchestrate_full_pipeline":
            query = data["query"]
            max_results = int(data["max_results"])
            onedrive_folder = data["onedrive_folder"]
            recipient = data["recipient_email"]
            zip_name = data["zip_name"]

            # 1) Search & download
            service = build_gmail_service()
            messages = search_messages_with_attachments(service, query=query, max_results=max_results)
            if not messages:
                return {"status": "no_messages_found", "downloaded_files": []}
            files = download_attachments_from_messages(service, messages, download_folder=work_dir)

            # 2) Upload attachments to OneDrive
            token = get_onedrive_access_token()
            uploaded = []
            for fpath in files:
                remote_path = os.path.join(onedrive_folder, os.path.basename(fpath)).replace("\\", "/")
                uploaded.append(upload_file_to_onedrive_path(token, fpath, remote_path))

            # 3) Compress files
            zip_path = os.path.join(work_dir, zip_name if zip_name.endswith(".zip") else f"{zip_name}.zip")
            compress_files(files, zip_path)

            # 4) Send zip via Gmail
            send_res = send_message_with_attachment(service, recipient, f"Files: {zip_name}", "See attached zip.", zip_path)

            return {
                "downloaded_files": files,
                "uploaded": uploaded,
                "zip_path": zip_path,
                "send_result": send_res,
            }

        else:
            raise HTTPException(status_code=400, detail="Unhandled tool")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tool execution error: {str(e)}")
    finally:
        # Clean up working dir - comment out if you want to inspect files
        try:
            shutil.rmtree(work_dir)
        except Exception:
            pass


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))