import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from config.database import SessionLocal
from models.account import Account
from models.email import Email
from services.imap_service import ImapService, encrypt_password, decrypt_password

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TOKEN_FILE = PROJECT_ROOT / "token.json"

# Granular sync progress: {account_id: {"status", "folder", "folders_done", "folders_total", "total", "synced", "skipped"}}
sync_progress = {}


class AccountService:

    def get_all_accounts(self, db: Session, user_id: int = None) -> list[dict]:
        q = db.query(Account)
        if user_id:
            q = q.filter(Account.user_id == user_id)
        accounts = q.order_by(Account.created_at).all()
        return [self._account_to_dict(a) for a in accounts]

    def get_account(self, db: Session, account_id: int) -> Optional[dict]:
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return None
        return self._account_to_dict(account)

    def create_account(self, db: Session, data: dict) -> dict:
        account = Account(
            name=data["name"],
            email=data["email"],
            provider=data["provider"],
            user_id=data.get("user_id"),
        )

        if data["provider"] == "gmail":
            account.oauth_token = data.get("oauth_token", "")
        elif data["provider"] == "imap":
            account.imap_host = data.get("imap_host", "")
            account.imap_port = data.get("imap_port", 993)
            account.imap_username = data.get("imap_username", "")
            if data.get("imap_password"):
                account.imap_password_encrypted = encrypt_password(data["imap_password"])
            account.imap_use_ssl = data.get("imap_use_ssl", True)

        db.add(account)
        db.commit()
        db.refresh(account)
        return self._account_to_dict(account)

    def update_account(self, db: Session, account_id: int, data: dict) -> Optional[dict]:
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return None

        if "name" in data:
            account.name = data["name"]
        if "email" in data:
            account.email = data["email"]

        if account.provider == "imap":
            if "imap_host" in data:
                account.imap_host = data["imap_host"]
            if "imap_port" in data:
                account.imap_port = data["imap_port"]
            if "imap_username" in data:
                account.imap_username = data["imap_username"]
            if data.get("imap_password"):
                account.imap_password_encrypted = encrypt_password(data["imap_password"])
            if "imap_use_ssl" in data:
                account.imap_use_ssl = data["imap_use_ssl"]

        if "is_active" in data:
            account.is_active = data["is_active"]

        db.commit()
        db.refresh(account)
        return self._account_to_dict(account)

    def delete_account(self, db: Session, account_id: int) -> bool:
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return False

        # Always delete associated emails to avoid orphans
        db.query(Email).filter(Email.account_id == account_id).delete(synchronize_session=False)

        db.delete(account)
        db.commit()
        return True

    def test_imap_connection(self, data: dict) -> dict:
        try:
            svc = ImapService(
                host=data.get("imap_host", ""),
                port=data.get("imap_port", 993),
                username=data.get("imap_username", ""),
                password=data.get("imap_password", ""),
                use_ssl=data.get("imap_use_ssl", True),
            )
            success = svc.test_connection()
            return {"success": success, "message": "Conexão OK" if success else "Falha na conexão"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def test_account_connection(self, db: Session, account_id: int) -> dict:
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return {"success": False, "message": "Conta não encontrada"}

        if account.provider == "imap":
            try:
                password = decrypt_password(account.imap_password_encrypted) if account.imap_password_encrypted else ""
                svc = ImapService(
                    host=account.imap_host,
                    port=account.imap_port,
                    username=account.imap_username,
                    password=password,
                    use_ssl=account.imap_use_ssl,
                )
                success = svc.test_connection()
                return {"success": success, "message": "Conexão OK" if success else "Falha na conexão"}
            except Exception as e:
                return {"success": False, "message": str(e)}

        elif account.provider == "gmail":
            try:
                token_data = json.loads(account.oauth_token or "{}")
                has_token = bool(token_data.get("refresh_token"))
                return {
                    "success": has_token,
                    "message": "Gmail conectado (OAuth)" if has_token else "Gmail não conectado - reconecte via OAuth",
                }
            except Exception as e:
                return {"success": False, "message": f"Erro: {e}"}

        return {"success": False, "message": "Provedor desconhecido"}

    def sync_imap_account(self, account_id: int):
        """Sync an IMAP account in background thread."""
        db = SessionLocal()
        try:
            account = db.query(Account).filter(Account.id == account_id).first()
            if not account or account.provider != "imap":
                return

            account.sync_status = "syncing"
            account.sync_error = None
            db.commit()

            sync_progress[account_id] = {
                "status": "connecting",
                "folder": "",
                "folders_done": 0,
                "folders_total": 0,
                "total": 0,
                "synced": 0,
                "skipped": 0,
            }

            password = decrypt_password(account.imap_password_encrypted) if account.imap_password_encrypted else ""
            svc = ImapService(
                host=account.imap_host,
                port=account.imap_port,
                username=account.imap_username,
                password=password,
                use_ssl=account.imap_use_ssl,
            )
            svc.connect()

            folders = svc.fetch_folders()
            target_folders = [f for f in folders if f.upper() in ("INBOX", "SENT", "DRAFTS", "SPAM", "TRASH", "JUNK")]
            if not target_folders:
                target_folders = ["INBOX"]

            sync_progress[account_id]["status"] = "syncing"
            sync_progress[account_id]["folders_total"] = len(target_folders)

            total_synced = 0
            for folder_idx, folder in enumerate(target_folders):
                sync_progress[account_id]["folder"] = folder
                sync_progress[account_id]["folders_done"] = folder_idx

                try:
                    uids = svc.fetch_email_ids(folder=folder)
                    if not uids:
                        continue

                    # Check existing
                    uid_strs = [f"imap_{uid.decode()}" for uid in uids]
                    existing = set(
                        row[0] for row in
                        db.query(Email.gmail_id).filter(Email.gmail_id.in_(uid_strs)).all()
                    )
                    new_uids = [uid for uid in uids if f"imap_{uid.decode()}" not in existing]
                    skipped = len(uids) - len(new_uids)

                    sync_progress[account_id]["total"] = len(new_uids)
                    sync_progress[account_id]["synced"] = 0
                    sync_progress[account_id]["skipped"] = skipped

                    if not new_uids:
                        continue

                    # Fetch in batches
                    batch_size = 50
                    for i in range(0, len(new_uids), batch_size):
                        chunk = new_uids[i:i + batch_size]
                        emails_data = svc.fetch_emails_batch(chunk, folder=folder)

                        for data in emails_data:
                            em = Email(
                                gmail_id=data["gmail_id"],
                                thread_id=data["thread_id"],
                                subject=data["subject"],
                                sender=data["sender"],
                                sender_email=data["sender_email"],
                                recipients=data["recipients"],
                                date=data["date"],
                                snippet=data["snippet"],
                                labels=data["labels"],
                                size_estimate=data["size_estimate"],
                                has_attachments=data["has_attachments"],
                                gmail_link=data["gmail_link"],
                                is_read=data["is_read"],
                                body=data.get("body", ""),
                                attachments=data.get("attachments", []),
                                account_id=account_id,
                                user_id=account.user_id,
                            )
                            db.add(em)
                            total_synced += 1

                        db.commit()
                        sync_progress[account_id]["synced"] = min(i + batch_size, len(new_uids))
                except Exception as e:
                    print(f"[IMAP Sync] Error syncing folder {folder}: {e}")
                    continue

            sync_progress[account_id]["folders_done"] = len(target_folders)

            svc.disconnect()
            account.sync_status = "idle"
            account.last_sync_at = datetime.now(timezone.utc)
            db.commit()
            print(f"[IMAP Sync] Account {account.email}: synced {total_synced} new emails")

        except Exception as e:
            print(f"[IMAP Sync] Error: {e}")
            try:
                account = db.query(Account).filter(Account.id == account_id).first()
                if account:
                    account.sync_status = "error"
                    account.sync_error = str(e)
                    db.commit()
            except Exception:
                pass
        finally:
            sync_progress.pop(account_id, None)
            db.close()

    def sync_gmail_account(self, account_id: int):
        """Sync a Gmail account using OAuth refresh_token via Gmail API."""
        db = SessionLocal()
        try:
            account = db.query(Account).filter(Account.id == account_id).first()
            if not account or account.provider != "gmail":
                return

            account.sync_status = "syncing"
            account.sync_error = None
            db.commit()

            sync_progress[account_id] = {
                "status": "connecting",
                "folder": "Gmail",
                "folders_done": 0,
                "folders_total": 1,
                "total": 0,
                "synced": 0,
                "skipped": 0,
            }

            # Parse oauth_token for refresh_token
            token_data = json.loads(account.oauth_token or "{}")
            refresh_token = token_data.get("refresh_token")
            if not refresh_token:
                raise Exception("No refresh_token found in oauth_token")

            from config.auth import GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request as GoogleAuthRequest
            from googleapiclient.discovery import build

            creds = Credentials(
                token=token_data.get("access_token"),
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=GMAIL_CLIENT_ID,
                client_secret=GMAIL_CLIENT_SECRET,
                scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            )

            if not creds.valid:
                creds.refresh(GoogleAuthRequest())
                # Update stored access_token
                token_data["access_token"] = creds.token
                account.oauth_token = json.dumps(token_data)
                db.commit()

            service = build("gmail", "v1", credentials=creds)

            sync_progress[account_id]["status"] = "syncing"

            # Fetch all message IDs
            total_synced = 0
            page_token = None
            all_msg_ids = []

            while True:
                results = (
                    service.users()
                    .messages()
                    .list(userId="me", maxResults=500, pageToken=page_token)
                    .execute()
                )
                messages = results.get("messages", [])
                all_msg_ids.extend([m["id"] for m in messages])
                page_token = results.get("nextPageToken")
                if not page_token:
                    break

            # Filter existing
            existing = set()
            batch_size_check = 5000
            for i in range(0, len(all_msg_ids), batch_size_check):
                chunk = all_msg_ids[i : i + batch_size_check]
                rows = db.query(Email.gmail_id).filter(Email.gmail_id.in_(chunk)).all()
                existing.update(r[0] for r in rows)

            new_ids = [mid for mid in all_msg_ids if mid not in existing]
            skipped = len(all_msg_ids) - len(new_ids)

            sync_progress[account_id]["total"] = len(new_ids)
            sync_progress[account_id]["skipped"] = skipped

            if not new_ids:
                sync_progress[account_id]["status"] = "done"
                account.sync_status = "idle"
                account.last_sync_at = datetime.now(timezone.utc)
                db.commit()
                print(f"[Gmail Sync] Account {account.email}: 0 new emails (skipped {skipped})")
                return

            # Fetch in batches using Gmail API batch
            from services.gmail_service import GmailService
            parser = GmailService()
            parser.service = service

            batch_size = 50
            for i in range(0, len(new_ids), batch_size):
                chunk = new_ids[i : i + batch_size]
                emails_data = parser.fetch_emails_batch(chunk)

                for data in emails_data:
                    em = Email(
                        gmail_id=data["gmail_id"],
                        thread_id=data["thread_id"],
                        subject=data["subject"],
                        sender=data["sender"],
                        sender_email=data["sender_email"],
                        recipients=data["recipients"],
                        date=data["date"],
                        snippet=data["snippet"],
                        labels=data["labels"],
                        size_estimate=data["size_estimate"],
                        has_attachments=data["has_attachments"],
                        gmail_link=data["gmail_link"],
                        is_read=data["is_read"],
                        body=data.get("body", ""),
                        attachments=data.get("attachments", []),
                        account_id=account_id,
                        user_id=account.user_id,
                    )
                    db.add(em)
                    total_synced += 1

                db.commit()
                sync_progress[account_id]["synced"] = min(i + batch_size, len(new_ids))

            sync_progress[account_id]["folders_done"] = 1
            account.sync_status = "idle"
            account.last_sync_at = datetime.now(timezone.utc)
            db.commit()
            print(f"[Gmail Sync] Account {account.email}: synced {total_synced} new emails")

        except Exception as e:
            print(f"[Gmail Sync] Error: {e}")
            try:
                account = db.query(Account).filter(Account.id == account_id).first()
                if account:
                    account.sync_status = "error"
                    account.sync_error = str(e)
                    db.commit()
            except Exception:
                pass
        finally:
            sync_progress.pop(account_id, None)
            db.close()

    def start_sync(self, account_id: int):
        """Start sync in background thread, dispatching to gmail or imap."""
        db = SessionLocal()
        try:
            account = db.query(Account).filter(Account.id == account_id).first()
            if not account:
                return
            provider = account.provider
        finally:
            db.close()

        if provider == "gmail":
            target = self.sync_gmail_account
        else:
            target = self.sync_imap_account

        thread = threading.Thread(target=target, args=(account_id,), daemon=True)
        thread.start()

    def migrate_existing_gmail(self):
        """Migrate existing Gmail data to accounts system on first run."""
        db = SessionLocal()
        try:
            existing_count = db.query(Account).count()
            if existing_count > 0:
                return  # Already migrated

            if not TOKEN_FILE.exists():
                return  # No Gmail configured

            from services.gmail_service import gmail_service
            if not gmail_service.is_authenticated():
                return

            user_email = gmail_service.user_email or "gmail@unknown.com"

            # Read token data
            token_data = TOKEN_FILE.read_text()

            account = Account(
                name="Gmail Principal",
                email=user_email,
                provider="gmail",
                oauth_token=token_data,
                is_active=True,
                sync_status="idle",
            )
            db.add(account)
            db.commit()
            db.refresh(account)

            # Backfill account_id in batches
            batch_size = 10000
            while True:
                result = db.execute(
                    text("""
                        UPDATE emails SET account_id = :account_id
                        WHERE id IN (
                            SELECT id FROM emails WHERE account_id IS NULL LIMIT :batch_size
                        )
                    """),
                    {"account_id": account.id, "batch_size": batch_size},
                )
                db.commit()
                if result.rowcount == 0:
                    break
                print(f"[Migration] Backfilled {result.rowcount} emails with account_id={account.id}")

            print(f"[Migration] Gmail account created: {user_email} (id={account.id})")

        except Exception as e:
            print(f"[Migration] Failed: {e}")
            db.rollback()
        finally:
            db.close()

    def _account_to_dict(self, account: Account) -> dict:
        return {
            "id": account.id,
            "name": account.name,
            "email": account.email,
            "provider": account.provider,
            "is_active": account.is_active,
            "imap_host": account.imap_host,
            "imap_port": account.imap_port,
            "imap_username": account.imap_username,
            "imap_use_ssl": account.imap_use_ssl,
            "last_sync_at": account.last_sync_at.isoformat() if account.last_sync_at else None,
            "sync_status": account.sync_status,
            "sync_error": account.sync_error,
            "created_at": account.created_at.isoformat() if account.created_at else None,
            "iredmail_source_email": account.iredmail_source_email,
        }


account_service = AccountService()
