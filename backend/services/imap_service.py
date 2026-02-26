import os
import re
import email
import imaplib
import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from email.header import decode_header

from cryptography.fernet import Fernet

IMAP_ENCRYPTION_KEY = os.getenv("IMAP_ENCRYPTION_KEY", "")


def _get_fernet():
    if not IMAP_ENCRYPTION_KEY:
        raise ValueError("IMAP_ENCRYPTION_KEY not set in environment")
    return Fernet(IMAP_ENCRYPTION_KEY.encode())


def encrypt_password(plain: str) -> str:
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    return _get_fernet().decrypt(encrypted.encode()).decode()


class ImapService:

    def __init__(self, host: str, port: int, username: str, password: str, use_ssl: bool = True):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.conn = None

    def connect(self):
        if self.use_ssl:
            self.conn = imaplib.IMAP4_SSL(self.host, self.port)
        else:
            self.conn = imaplib.IMAP4(self.host, self.port)
        self.conn.login(self.username, self.password)
        return self

    def disconnect(self):
        if self.conn:
            try:
                self.conn.logout()
            except Exception:
                pass
            self.conn = None

    def test_connection(self) -> bool:
        try:
            self.connect()
            self.disconnect()
            return True
        except Exception:
            return False

    def fetch_folders(self) -> list[str]:
        if not self.conn:
            self.connect()
        status, folders = self.conn.list()
        result = []
        for f in folders:
            decoded = f.decode() if isinstance(f, bytes) else f
            match = re.search(r'"([^"]*)"$|(\S+)$', decoded)
            if match:
                result.append(match.group(1) or match.group(2))
        return result

    def fetch_email_ids(self, folder: str = "INBOX", since_date: str = None) -> list[str]:
        if not self.conn:
            self.connect()
        self.conn.select(folder, readonly=True)

        criteria = "ALL"
        if since_date:
            criteria = f'(SINCE "{since_date}")'

        status, data = self.conn.search(None, criteria)
        if status != "OK":
            return []
        return data[0].split()

    def fetch_email_detail(self, uid: bytes, folder: str = "INBOX") -> dict:
        if not self.conn:
            self.connect()

        self.conn.select(folder, readonly=True)
        status, data = self.conn.fetch(uid, "(RFC822)")
        if status != "OK" or not data or not data[0]:
            return None

        raw = data[0][1]
        msg = email.message_from_bytes(raw)
        return self._parse_message(msg, uid)

    def fetch_emails_batch(self, uids: list[bytes], folder: str = "INBOX") -> list[dict]:
        if not self.conn:
            self.connect()
        self.conn.select(folder, readonly=True)

        results = []
        batch_size = 50
        for i in range(0, len(uids), batch_size):
            chunk = uids[i:i + batch_size]
            uid_str = b",".join(chunk)
            status, data = self.conn.fetch(uid_str, "(RFC822)")
            if status != "OK":
                continue
            for item in data:
                if isinstance(item, tuple) and len(item) == 2:
                    raw = item[1]
                    msg = email.message_from_bytes(raw)
                    parsed = self._parse_message(msg, item[0])
                    if parsed:
                        results.append(parsed)
        return results

    def _parse_message(self, msg, uid) -> dict:
        subject = self._decode_header(msg.get("Subject", "(sem assunto)"))
        sender = self._decode_header(msg.get("From", ""))
        recipients = self._decode_header(msg.get("To", ""))
        sender_email = self._extract_email(sender)

        date = None
        date_str = msg.get("Date", "")
        if date_str:
            try:
                date = parsedate_to_datetime(date_str)
            except Exception:
                pass

        message_id = msg.get("Message-ID", "")
        # Use UID as stable ID
        uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
        # Remove the fetch response prefix if present (e.g. "1 (RFC822 {12345}")
        uid_clean = re.sub(r'\s.*', '', uid_str)

        body_html, body_text = self._extract_body(msg)
        body = body_html or body_text or ""

        attachments = self._extract_attachments(msg)

        size_estimate = len(msg.as_bytes()) if hasattr(msg, 'as_bytes') else 0

        return {
            "gmail_id": f"imap_{uid_clean}",  # Unique identifier for IMAP
            "thread_id": msg.get("In-Reply-To", "") or message_id,
            "subject": subject,
            "sender": sender,
            "sender_email": sender_email,
            "recipients": recipients,
            "date": date,
            "snippet": (body_text or body_html or "")[:200].replace('\n', ' ').replace('\r', ''),
            "labels": ["INBOX"],
            "size_estimate": size_estimate,
            "has_attachments": len(attachments) > 0,
            "gmail_link": "",
            "is_read": True,
            "body": body,
            "attachments": attachments,
        }

    def _decode_header(self, header_val: str) -> str:
        if not header_val:
            return ""
        parts = decode_header(header_val)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(part)
        return " ".join(decoded)

    def _extract_email(self, sender: str) -> str:
        match = re.search(r"<(.+?)>", sender)
        if match:
            return match.group(1).lower()
        if "@" in sender:
            return sender.strip().lower()
        return sender

    def _extract_body(self, msg) -> tuple:
        html_body = None
        text_body = None

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disp = str(part.get("Content-Disposition", ""))

                if "attachment" in content_disp:
                    continue

                payload = part.get_payload(decode=True)
                if not payload:
                    continue

                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")

                if content_type == "text/html":
                    html_body = text
                elif content_type == "text/plain":
                    text_body = text
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    html_body = text
                else:
                    text_body = text

        return html_body, text_body

    def _extract_attachments(self, msg) -> list[dict]:
        attachments = []
        if not msg.is_multipart():
            return attachments

        for part in msg.walk():
            content_disp = str(part.get("Content-Disposition", ""))
            if "attachment" not in content_disp:
                continue

            filename = part.get_filename()
            if filename:
                filename = self._decode_header(filename)
                payload = part.get_payload(decode=True)
                size = len(payload) if payload else 0
                attachments.append({
                    "filename": filename,
                    "mimeType": part.get_content_type(),
                    "size": size,
                    "attachmentId": "",  # Not downloadable through IMAP in this context
                })
        return attachments
