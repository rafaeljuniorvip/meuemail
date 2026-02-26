import os
import re
import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
TOKEN_FILE = PROJECT_ROOT / "token.json"


class GmailService:
    def __init__(self):
        self.service = None
        self.user_email = None

    def is_authenticated(self) -> bool:
        return self.service is not None

    def authenticate(self) -> dict:
        creds = None

        if TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

        if creds and creds.valid:
            self.service = build("gmail", "v1", credentials=creds)
            profile = self.service.users().getProfile(userId="me").execute()
            self.user_email = profile.get("emailAddress")
            return {"status": "ok", "email": self.user_email}

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self._save_token(creds)
            self.service = build("gmail", "v1", credentials=creds)
            profile = self.service.users().getProfile(userId="me").execute()
            self.user_email = profile.get("emailAddress")
            return {"status": "ok", "email": self.user_email}

        if not CREDENTIALS_FILE.exists():
            return {
                "status": "error",
                "message": "credentials.json não encontrado na raiz do projeto",
            }

        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_FILE), SCOPES
        )
        creds = flow.run_local_server(port=8081, open_browser=True)
        self._save_token(creds)

        self.service = build("gmail", "v1", credentials=creds)
        profile = self.service.users().getProfile(userId="me").execute()
        self.user_email = profile.get("emailAddress")
        return {"status": "ok", "email": self.user_email}

    def _save_token(self, creds: Credentials):
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    def fetch_email_ids(self, page_token=None, max_results=500) -> dict:
        results = (
            self.service.users()
            .messages()
            .list(userId="me", maxResults=max_results, pageToken=page_token)
            .execute()
        )
        return {
            "messages": results.get("messages", []),
            "nextPageToken": results.get("nextPageToken"),
            "resultSizeEstimate": results.get("resultSizeEstimate", 0),
        }

    def fetch_email_detail(self, msg_id: str) -> dict:
        msg = (
            self.service.users()
            .messages()
            .get(userId="me", id=msg_id, format="full")
            .execute()
        )
        return self._parse_message(msg, resolve_cid=True)

    def fetch_emails_batch(self, msg_ids: list[str]) -> list[dict]:
        emails = []
        batch_size = 50

        for i in range(0, len(msg_ids), batch_size):
            chunk = msg_ids[i : i + batch_size]
            batch = self.service.new_batch_http_request()

            def make_callback(email_list):
                def callback(request_id, response, exception):
                    if exception is None:
                        parsed = self._parse_message(response)
                        email_list.append(parsed)
                return callback

            for mid in chunk:
                batch.add(
                    self.service.users()
                    .messages()
                    .get(userId="me", id=mid, format="full"),
                    callback=make_callback(emails),
                )
            batch.execute()

        return emails

    def delete_emails(self, gmail_ids: list[str]) -> dict:
        deleted = 0
        errors = []
        batch_size = 50

        for i in range(0, len(gmail_ids), batch_size):
            chunk = gmail_ids[i : i + batch_size]
            batch = self.service.new_batch_http_request()

            def make_callback(counter_ref):
                def callback(request_id, response, exception):
                    if exception:
                        counter_ref["errors"].append(str(exception))
                    else:
                        counter_ref["deleted"] += 1
                return callback

            counter = {"deleted": 0, "errors": []}
            for gid in chunk:
                batch.add(
                    self.service.users()
                    .messages()
                    .trash(userId="me", id=gid),
                    callback=make_callback(counter),
                )
            batch.execute()
            deleted += counter["deleted"]
            errors.extend(counter["errors"])

        return {"deleted": deleted, "errors": errors}

    def _parse_message(self, msg: dict, resolve_cid: bool = False) -> dict:
        headers = {
            h["name"].lower(): h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }

        sender = headers.get("from", "")
        sender_email = self._extract_email(sender)

        date_str = headers.get("date", "")
        date = None
        if date_str:
            try:
                date = parsedate_to_datetime(date_str)
            except Exception:
                date = None

        labels = msg.get("labelIds", [])
        is_read = "UNREAD" not in labels

        attachments_meta = self._extract_attachments(msg.get("payload", {}))
        has_attachments = len(attachments_meta) > 0

        gmail_link = f"https://mail.google.com/mail/u/0/#inbox/{msg['id']}"

        body = self._extract_body(msg["id"], msg.get("payload", {}), resolve_cid=resolve_cid)

        return {
            "gmail_id": msg["id"],
            "thread_id": msg.get("threadId", ""),
            "subject": headers.get("subject", "(sem assunto)"),
            "sender": sender,
            "sender_email": sender_email,
            "recipients": headers.get("to", ""),
            "date": date,
            "snippet": msg.get("snippet", ""),
            "labels": labels,
            "size_estimate": msg.get("sizeEstimate", 0),
            "has_attachments": has_attachments,
            "gmail_link": gmail_link,
            "is_read": is_read,
            "body": body,
            "attachments": attachments_meta,
        }

    def _extract_email(self, sender: str) -> str:
        match = re.search(r"<(.+?)>", sender)
        if match:
            return match.group(1).lower()
        if "@" in sender:
            return sender.strip().lower()
        return sender

    def _extract_body(self, msg_id: str, payload: dict, resolve_cid: bool = False) -> str:
        """Extract email body (prefer HTML over plain), optionally replacing cid: with inline data URIs."""
        cid_map = {}
        if resolve_cid:
            self._collect_cid_images(msg_id, payload, cid_map)

        body = self._extract_body_content(payload)

        # Replace cid: references with data URIs
        for cid, data_uri in cid_map.items():
            body = body.replace(f"cid:{cid}", data_uri)

        return body

    def _extract_body_content(self, payload: dict) -> str:
        if payload.get("mimeType") == "text/html" and payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

        parts = payload.get("parts", [])
        text_body = None
        html_body = None

        for part in parts:
            mime = part.get("mimeType", "")
            if mime == "text/html" and part.get("body", {}).get("data"):
                html_body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
            elif mime == "text/plain" and part.get("body", {}).get("data"):
                text_body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
            elif mime.startswith("multipart/"):
                nested = self._extract_body_content(part)
                if nested:
                    if "<" in nested:
                        html_body = html_body or nested
                    else:
                        text_body = text_body or nested

        return html_body or text_body or ""

    def _collect_cid_images(self, msg_id: str, part: dict, cid_map: dict):
        """Walk payload parts and collect inline images (Content-ID → data URI).
        Handles both inline data and attachment-based CID images."""
        headers = {
            h["name"].lower(): h["value"]
            for h in part.get("headers", [])
        }
        content_id = headers.get("content-id", "").strip("<>")
        mime_type = part.get("mimeType", "")
        body = part.get("body", {})
        body_data = body.get("data")
        attachment_id = body.get("attachmentId")

        if content_id and mime_type.startswith("image/"):
            if body_data:
                cid_map[content_id] = f"data:{mime_type};base64,{body_data}"
            elif attachment_id:
                try:
                    raw = self.download_attachment(msg_id, attachment_id)
                    b64 = base64.b64encode(raw).decode("ascii")
                    cid_map[content_id] = f"data:{mime_type};base64,{b64}"
                except Exception:
                    pass

        for sub in part.get("parts", []):
            self._collect_cid_images(msg_id, sub, cid_map)

    def _extract_attachments(self, payload: dict) -> list[dict]:
        attachments = []
        self._walk_attachments(payload, attachments)
        return attachments

    def _walk_attachments(self, part: dict, attachments: list):
        filename = part.get("filename", "")
        body = part.get("body", {})
        if filename and body.get("attachmentId"):
            attachments.append({
                "filename": filename,
                "mimeType": part.get("mimeType", "application/octet-stream"),
                "size": body.get("size", 0),
                "attachmentId": body["attachmentId"],
            })
        for sub in part.get("parts", []):
            self._walk_attachments(sub, attachments)

    def download_attachment(self, msg_id: str, attachment_id: str) -> bytes:
        result = (
            self.service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=msg_id, id=attachment_id)
            .execute()
        )
        data = result.get("data", "")
        return base64.urlsafe_b64decode(data)


gmail_service = GmailService()
