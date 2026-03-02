from datetime import datetime, timezone

import pymysql
from sqlalchemy.orm import Session

from services.imap_service import ImapService, encrypt_password, decrypt_password


class IRedMailService:

    def _get_connection(self, config: dict):
        import os
        password = decrypt_password(config["mariadb_password_encrypted"])
        host = os.getenv("IREDMAIL_DB_HOST", config["mariadb_host"])
        port = int(os.getenv("IREDMAIL_DB_PORT", config["mariadb_port"]))
        return pymysql.connect(
            host=host,
            port=port,
            user=config["mariadb_user"],
            password=password,
            database=config["mariadb_database"],
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
            read_timeout=30,
        )

    def test_connection(self, config: dict) -> dict:
        try:
            conn = self._get_connection(config)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM mailbox")
            row = cursor.fetchone()
            conn.close()
            return {"success": True, "message": f"Conectado! {row['cnt']} caixas postais encontradas."}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def discover_domains(self, config: dict) -> list[dict]:
        conn = self._get_connection(config)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.domain, d.description, d.active,
                   COUNT(m.username) as mailbox_count
            FROM domain d
            LEFT JOIN mailbox m ON m.domain = d.domain
            GROUP BY d.domain, d.description, d.active
            ORDER BY mailbox_count DESC, d.domain
        """)
        domains = cursor.fetchall()
        conn.close()
        return domains

    def discover_mailboxes(self, config: dict, domain: str = None) -> list[dict]:
        conn = self._get_connection(config)
        cursor = conn.cursor()

        query = """
            SELECT m.username, m.name, m.domain, m.quota, m.active,
                   m.created,
                   COALESCE(uq.bytes, 0) as used_bytes,
                   COALESCE(uq.messages, 0) as message_count,
                   ll.imap as last_login_imap
            FROM mailbox m
            LEFT JOIN used_quota uq ON uq.username = m.username
            LEFT JOIN last_login ll ON ll.username = m.username
        """
        params = []
        if domain:
            query += " WHERE m.domain = %s"
            params.append(domain)

        query += " ORDER BY m.domain, m.username"

        cursor.execute(query, params)
        mailboxes = cursor.fetchall()
        conn.close()

        for m in mailboxes:
            if m.get("created"):
                m["created"] = m["created"].isoformat() if hasattr(m["created"], "isoformat") else str(m["created"])

        return mailboxes

    def get_import_status(self, db: Session, mailboxes: list[dict]) -> list[dict]:
        from models.account import Account

        emails = [m["username"] for m in mailboxes]
        if not emails:
            return mailboxes

        existing = (
            db.query(Account.iredmail_source_email, Account.id)
            .filter(Account.iredmail_source_email.in_(emails))
            .all()
        )
        imported_map = {row.iredmail_source_email: row.id for row in existing}

        for m in mailboxes:
            m["already_imported"] = m["username"] in imported_map
            m["meugmail_account_id"] = imported_map.get(m["username"])

        return mailboxes

    def import_mailboxes(
        self,
        db: Session,
        config: dict,
        selected_emails: list[str],
        user_id: int = None,
    ) -> dict:
        from models.account import Account
        from services.account_service import account_service

        created = []
        skipped = []
        errors = []

        for email_addr in selected_emails:
            try:
                existing = (
                    db.query(Account)
                    .filter(Account.iredmail_source_email == email_addr)
                    .first()
                )
                if existing:
                    skipped.append(email_addr)
                    continue

                imap_username = email_addr
                imap_password = None

                if config.get("master_password_encrypted"):
                    master_password = decrypt_password(config["master_password_encrypted"])
                    master_user = config.get("master_user", "dovecotadmin")
                    imap_username = f"{email_addr}*{master_user}"
                    imap_password = master_password

                local_part = email_addr.split("@")[0]
                domain = email_addr.split("@")[1]
                account_name = f"{local_part} ({domain})"

                account_data = {
                    "name": account_name,
                    "email": email_addr,
                    "provider": "imap",
                    "imap_host": config.get("imap_host", "email2.viptecnologia.com.br"),
                    "imap_port": config.get("imap_port", 993),
                    "imap_username": imap_username,
                    "imap_password": imap_password,
                    "imap_use_ssl": True,
                    "user_id": user_id,
                }

                result = account_service.create_account(db, account_data)

                account_obj = db.query(Account).filter(Account.id == result["id"]).first()
                account_obj.iredmail_source_email = email_addr
                db.commit()

                created.append(email_addr)

            except Exception as e:
                errors.append({"email": email_addr, "error": str(e)})

        return {
            "created": created,
            "skipped": skipped,
            "errors": errors,
            "total_created": len(created),
            "total_skipped": len(skipped),
            "total_errors": len(errors),
        }

    def test_master_user(self, config: dict, test_email: str) -> dict:
        try:
            master_password = decrypt_password(config["master_password_encrypted"])
            master_user = config.get("master_user", "dovecotadmin")

            svc = ImapService(
                host=config.get("imap_host", "email2.viptecnologia.com.br"),
                port=config.get("imap_port", 993),
                username=f"{test_email}*{master_user}",
                password=master_password,
                use_ssl=True,
            )
            success = svc.test_connection()
            return {
                "success": success,
                "message": "Master user OK!" if success else "Falha na autenticação master user",
            }
        except Exception as e:
            return {"success": False, "message": str(e)}


iredmail_service = IRedMailService()
