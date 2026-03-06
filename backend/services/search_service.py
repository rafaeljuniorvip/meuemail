import hashlib
import json

from sqlalchemy import text
from config.database import SessionLocal


class SearchService:

    def _get_db(self):
        return SessionLocal()

    def _rows_to_dicts(self, rows, columns):
        return [dict(zip(columns, row)) for row in rows]

    def _email_columns(self):
        return [
            "gmail_id", "thread_id", "subject", "sender", "sender_email",
            "date", "snippet", "labels", "size_estimate", "has_attachments",
            "is_read", "gmail_link",
        ]

    def _email_select(self):
        return """gmail_id, thread_id, subject, sender, sender_email,
                  date, LEFT(snippet, 200) as snippet, labels, size_estimate,
                  has_attachments, is_read, gmail_link"""

    def _account_filter(self, conditions: list, params: dict, account_id: int = None):
        if account_id is not None:
            conditions.append("account_id = :account_id")
            params["account_id"] = account_id

    def _user_filter(self, conditions: list, params: dict, user_id: int = None):
        if user_id is not None:
            conditions.append("user_id = :user_id")
            params["user_id"] = user_id

    def search_body_fulltext(self, query: str, limit: int = 20, account_id: int = None, user_id: int = None) -> list[dict]:
        db = self._get_db()
        try:
            conditions = ["body_tsv @@ plainto_tsquery('portuguese', :query)"]
            params = {"query": query, "limit": limit}
            self._account_filter(conditions, params, account_id)
            self._user_filter(conditions, params, user_id)
            where = " AND ".join(conditions)
            sql = text(f"""
                SELECT {self._email_select()},
                       ts_rank(body_tsv, plainto_tsquery('portuguese', :query)) as rank
                FROM emails
                WHERE {where}
                ORDER BY rank DESC
                LIMIT :limit
            """)
            rows = db.execute(sql, params).fetchall()
            cols = self._email_columns() + ["rank"]
            return self._rows_to_dicts(rows, cols)
        finally:
            db.close()

    def search_subject_keyword(self, keyword: str, limit: int = 20, account_id: int = None, user_id: int = None) -> list[dict]:
        db = self._get_db()
        try:
            conditions = ["subject ILIKE :pattern"]
            params = {"pattern": f"%{keyword}%", "limit": limit}
            self._account_filter(conditions, params, account_id)
            self._user_filter(conditions, params, user_id)
            where = " AND ".join(conditions)
            sql = text(f"""
                SELECT {self._email_select()}
                FROM emails
                WHERE {where}
                ORDER BY date DESC
                LIMIT :limit
            """)
            rows = db.execute(sql, params).fetchall()
            return self._rows_to_dicts(rows, self._email_columns())
        finally:
            db.close()

    def search_sender(self, sender: str, limit: int = 20, account_id: int = None, user_id: int = None) -> list[dict]:
        db = self._get_db()
        try:
            conditions = ["(sender ILIKE :pattern OR sender_email ILIKE :pattern)"]
            params = {"pattern": f"%{sender}%", "limit": limit}
            self._account_filter(conditions, params, account_id)
            self._user_filter(conditions, params, user_id)
            where = " AND ".join(conditions)
            sql = text(f"""
                SELECT {self._email_select()}
                FROM emails
                WHERE {where}
                ORDER BY date DESC
                LIMIT :limit
            """)
            rows = db.execute(sql, params).fetchall()
            return self._rows_to_dicts(rows, self._email_columns())
        finally:
            db.close()

    def search_sender_exact(self, sender_email: str, limit: int = 20, account_id: int = None, user_id: int = None) -> list[dict]:
        db = self._get_db()
        try:
            conditions = ["LOWER(sender_email) = LOWER(:email)"]
            params = {"email": sender_email, "limit": limit}
            self._account_filter(conditions, params, account_id)
            self._user_filter(conditions, params, user_id)
            where = " AND ".join(conditions)
            sql = text(f"""
                SELECT {self._email_select()}
                FROM emails
                WHERE {where}
                ORDER BY date DESC
                LIMIT :limit
            """)
            rows = db.execute(sql, params).fetchall()
            return self._rows_to_dicts(rows, self._email_columns())
        finally:
            db.close()

    def search_date_range(self, date_from: str = None, date_to: str = None, limit: int = 20, account_id: int = None, user_id: int = None) -> list[dict]:
        db = self._get_db()
        try:
            conditions = []
            params = {"limit": limit}
            if date_from:
                conditions.append("date >= :date_from")
                params["date_from"] = date_from
            if date_to:
                conditions.append("date <= :date_to::date + interval '1 day'")
                params["date_to"] = date_to
            self._account_filter(conditions, params, account_id)
            self._user_filter(conditions, params, user_id)
            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            sql = text(f"""
                SELECT {self._email_select()}
                FROM emails
                {where}
                ORDER BY date DESC
                LIMIT :limit
            """)
            rows = db.execute(sql, params).fetchall()
            return self._rows_to_dicts(rows, self._email_columns())
        finally:
            db.close()

    def search_by_label(self, label: str, limit: int = 20, account_id: int = None, user_id: int = None) -> list[dict]:
        db = self._get_db()
        try:
            conditions = [":label = ANY(labels)"]
            params = {"label": label, "limit": limit}
            self._account_filter(conditions, params, account_id)
            self._user_filter(conditions, params, user_id)
            where = " AND ".join(conditions)
            sql = text(f"""
                SELECT {self._email_select()}
                FROM emails
                WHERE {where}
                ORDER BY date DESC
                LIMIT :limit
            """)
            rows = db.execute(sql, params).fetchall()
            return self._rows_to_dicts(rows, self._email_columns())
        finally:
            db.close()

    def search_attachments(self, filename: str = None, has_attachments: bool = True, limit: int = 20, account_id: int = None, user_id: int = None) -> list[dict]:
        db = self._get_db()
        try:
            conditions = ["has_attachments = :has_att"]
            params = {"has_att": has_attachments, "limit": limit}
            if filename:
                conditions.append("attachments::text ILIKE :filename_pattern")
                params["filename_pattern"] = f"%{filename}%"
            self._account_filter(conditions, params, account_id)
            self._user_filter(conditions, params, user_id)
            where = " AND ".join(conditions)
            sql = text(f"""
                SELECT {self._email_select()}
                FROM emails
                WHERE {where}
                ORDER BY date DESC
                LIMIT :limit
            """)
            rows = db.execute(sql, params).fetchall()
            return self._rows_to_dicts(rows, self._email_columns())
        finally:
            db.close()

    def search_thread(self, thread_id: str, account_id: int = None, user_id: int = None) -> list[dict]:
        db = self._get_db()
        try:
            conditions = ["thread_id = :thread_id"]
            params = {"thread_id": thread_id}
            self._account_filter(conditions, params, account_id)
            self._user_filter(conditions, params, user_id)
            where = " AND ".join(conditions)
            sql = text(f"""
                SELECT {self._email_select()}
                FROM emails
                WHERE {where}
                ORDER BY date ASC
            """)
            rows = db.execute(sql, params).fetchall()
            return self._rows_to_dicts(rows, self._email_columns())
        finally:
            db.close()

    def search_combined(
        self,
        sender: str = None,
        subject: str = None,
        body_keyword: str = None,
        date_from: str = None,
        date_to: str = None,
        label: str = None,
        has_attachments: bool = None,
        limit: int = 20,
        account_id: int = None,
        user_id: int = None,
    ) -> list[dict]:
        db = self._get_db()
        try:
            conditions = []
            params = {"limit": limit}
            if sender:
                conditions.append("(sender ILIKE :sender_pat OR sender_email ILIKE :sender_pat)")
                params["sender_pat"] = f"%{sender}%"
            if subject:
                conditions.append("subject ILIKE :subject_pat")
                params["subject_pat"] = f"%{subject}%"
            if body_keyword:
                conditions.append("body_tsv @@ plainto_tsquery('portuguese', :body_kw)")
                params["body_kw"] = body_keyword
            if date_from:
                conditions.append("date >= :date_from")
                params["date_from"] = date_from
            if date_to:
                conditions.append("date <= :date_to::date + interval '1 day'")
                params["date_to"] = date_to
            if label:
                conditions.append(":label = ANY(labels)")
                params["label"] = label
            if has_attachments is not None:
                conditions.append("has_attachments = :has_att")
                params["has_att"] = has_attachments
            self._account_filter(conditions, params, account_id)
            self._user_filter(conditions, params, user_id)
            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            sql = text(f"""
                SELECT {self._email_select()}
                FROM emails
                {where}
                ORDER BY date DESC
                LIMIT :limit
            """)
            rows = db.execute(sql, params).fetchall()
            return self._rows_to_dicts(rows, self._email_columns())
        finally:
            db.close()

    def get_email_detail(self, gmail_id: str, user_id: int = None) -> dict | None:
        db = self._get_db()
        try:
            conditions = ["gmail_id = :gmail_id"]
            params = {"gmail_id": gmail_id}
            self._user_filter(conditions, params, user_id)
            where = " AND ".join(conditions)
            sql = text(f"""
                SELECT gmail_id, thread_id, subject, sender, sender_email,
                       recipients, date, snippet, labels, size_estimate,
                       has_attachments, is_read, gmail_link, body, attachments
                FROM emails
                WHERE {where}
            """)
            row = db.execute(sql, params).fetchone()
            if not row:
                return None
            cols = [
                "gmail_id", "thread_id", "subject", "sender", "sender_email",
                "recipients", "date", "snippet", "labels", "size_estimate",
                "has_attachments", "is_read", "gmail_link", "body", "attachments",
            ]
            return dict(zip(cols, row))
        finally:
            db.close()

    def get_top_senders(self, limit: int = 20, account_id: int = None, user_id: int = None) -> list[dict]:
        db = self._get_db()
        try:
            conditions = []
            params = {"limit": limit}
            self._account_filter(conditions, params, account_id)
            self._user_filter(conditions, params, user_id)
            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            sql = text(f"""
                SELECT sender, sender_email,
                       COUNT(*) as total_emails,
                       COUNT(*) FILTER (WHERE NOT is_read) as unread,
                       MIN(date) as first_email,
                       MAX(date) as last_email
                FROM emails
                {where}
                GROUP BY sender, sender_email
                ORDER BY total_emails DESC
                LIMIT :limit
            """)
            rows = db.execute(sql, params).fetchall()
            return [
                {
                    "sender": row[0],
                    "sender_email": row[1],
                    "total_emails": row[2],
                    "unread": row[3],
                    "first_email": str(row[4]) if row[4] else None,
                    "last_email": str(row[5]) if row[5] else None,
                }
                for row in rows
            ]
        finally:
            db.close()

    def get_email_stats(self, account_id: int = None, user_id: int = None) -> dict:
        db = self._get_db()
        try:
            conditions = []
            params = {}
            self._account_filter(conditions, params, account_id)
            self._user_filter(conditions, params, user_id)
            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            sql = text(f"""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE NOT is_read) as unread,
                    COUNT(*) FILTER (WHERE has_attachments) as with_attachments,
                    MIN(date) as oldest_email,
                    MAX(date) as newest_email,
                    COUNT(DISTINCT sender_email) as unique_senders
                FROM emails
                {where}
            """)
            row = db.execute(sql, params).fetchone()
            # Top labels
            sql_labels = text(f"""
                SELECT unnest_label, COUNT(*) as cnt
                FROM emails, LATERAL unnest(labels) as unnest_label
                {where}
                GROUP BY unnest_label
                ORDER BY cnt DESC
                LIMIT 15
            """)
            label_rows = db.execute(sql_labels, params).fetchall()
            return {
                "total_emails": row[0],
                "unread": row[1],
                "with_attachments": row[2],
                "oldest_email": str(row[3]) if row[3] else None,
                "newest_email": str(row[4]) if row[4] else None,
                "unique_senders": row[5],
                "top_labels": [{"label": r[0], "count": r[1]} for r in label_rows],
            }
        finally:
            db.close()

    def execute_sql(self, query: str) -> dict:
        """Executa uma query SQL read-only no banco de dados."""
        normalized = query.strip().rstrip(";").strip()
        upper = normalized.upper()

        # Only allow SELECT and WITH (CTEs)
        if not (upper.startswith("SELECT") or upper.startswith("WITH")):
            return {"error": "Apenas queries SELECT são permitidas."}

        # Block dangerous keywords
        blocked = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
                    "CREATE", "GRANT", "REVOKE", "EXEC", "EXECUTE"]
        for kw in blocked:
            if kw in upper.split():
                return {"error": f"Keyword '{kw}' não é permitido em queries de leitura."}

        db = self._get_db()
        try:
            result = db.execute(text(normalized))
            columns = list(result.keys()) if result.returns_rows else []
            rows = result.fetchall() if result.returns_rows else []
            # Limit to 100 rows to avoid massive responses
            truncated = len(rows) > 100
            rows = rows[:100]
            data = [dict(zip(columns, [str(v) if v is not None else None for v in row])) for row in rows]
            return {
                "columns": columns,
                "rows": data,
                "row_count": len(data),
                "truncated": truncated,
            }
        except Exception as e:
            return {"error": f"Erro SQL: {str(e)}"}
        finally:
            db.close()

    def get_sender_summary(self, sender_email: str, user_id: int = None) -> dict:
        db = self._get_db()
        try:
            conditions = ["LOWER(sender_email) = LOWER(:email)"]
            params = {"email": sender_email}
            self._user_filter(conditions, params, user_id)
            where = " AND ".join(conditions)
            sql = text(f"""
                SELECT
                    COUNT(*) as total_emails,
                    MIN(date) as first_email,
                    MAX(date) as last_email,
                    SUM(size_estimate) as total_size,
                    COUNT(*) FILTER (WHERE has_attachments) as with_attachments,
                    COUNT(*) FILTER (WHERE NOT is_read) as unread,
                    array_agg(DISTINCT unnest_label) as labels_used
                FROM emails, LATERAL unnest(labels) as unnest_label
                WHERE {where}
            """)
            row = db.execute(sql, params).fetchone()
            if not row or row[0] == 0:
                return {"sender_email": sender_email, "total_emails": 0}
            return {
                "sender_email": sender_email,
                "total_emails": row[0],
                "first_email": str(row[1]) if row[1] else None,
                "last_email": str(row[2]) if row[2] else None,
                "total_size": row[3],
                "with_attachments": row[4],
                "unread": row[5],
                "labels_used": row[6] or [],
            }
        finally:
            db.close()


    def save_query(self, title: str, description: str, sql: str) -> dict:
        """Salva uma consulta SQL para visualização posterior."""
        raw = f"{sql}:{title}"
        query_id = hashlib.md5(raw.encode()).hexdigest()[:8]

        db = self._get_db()
        try:
            db.execute(
                text("""
                    INSERT INTO saved_queries (id, title, description, query_type, query_data)
                    VALUES (:id, :title, :description, 'sql', :query_data)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        query_data = EXCLUDED.query_data,
                        created_at = NOW()
                """),
                {
                    "id": query_id,
                    "title": title,
                    "description": description,
                    "query_data": json.dumps({"sql": sql}),
                },
            )
            db.commit()
            return {
                "id": query_id,
                "title": title,
                "link": f"#/query/{query_id}",
            }
        finally:
            db.close()


    def find_contact_email(self, name: str, limit: int = 10, user_id: int = None) -> list[dict]:
        """Find a contact's email by searching sender names/emails and recipients."""
        db = self._get_db()
        try:
            params = {"pattern": f"%{name}%", "limit": limit}
            user_clause = ""
            if user_id is not None:
                user_clause = "AND user_id = :user_id"
                params["user_id"] = user_id

            sql = text(f"""
                WITH contacts AS (
                    -- From received emails (sender)
                    SELECT
                        sender_email AS email,
                        sender AS name,
                        COUNT(*) AS freq,
                        MAX(date) AS last_seen,
                        'remetente' AS source
                    FROM emails
                    WHERE (sender ILIKE :pattern OR sender_email ILIKE :pattern)
                      AND sender_email IS NOT NULL AND sender_email != ''
                      {user_clause}
                    GROUP BY sender_email, sender

                    UNION ALL

                    -- From sent emails (recipients)
                    SELECT
                        LOWER(TRIM(
                            CASE
                                WHEN r.addr LIKE '%<%>%'
                                THEN SUBSTRING(r.addr FROM '<([^>]+)>')
                                ELSE r.addr
                            END
                        )) AS email,
                        TRIM(
                            CASE
                                WHEN r.addr LIKE '%<%>%'
                                THEN SUBSTRING(r.addr FROM '^(.+)<')
                                ELSE ''
                            END
                        ) AS name,
                        COUNT(*) AS freq,
                        MAX(e.date) AS last_seen,
                        'destinatario' AS source
                    FROM emails e,
                         LATERAL unnest(string_to_array(e.recipients, ',')) AS r(addr)
                    WHERE (r.addr ILIKE :pattern)
                      AND e.recipients IS NOT NULL AND e.recipients != ''
                      {user_clause.replace('user_id', 'e.user_id') if user_id else ''}
                    GROUP BY 1, 2
                ),
                ranked AS (
                    SELECT
                        email,
                        MAX(name) FILTER (WHERE name != '' AND name IS NOT NULL) AS name,
                        SUM(freq) AS total_interactions,
                        MAX(last_seen) AS last_interaction,
                        array_agg(DISTINCT source) AS sources
                    FROM contacts
                    WHERE email != '' AND email IS NOT NULL
                      AND email NOT LIKE '%@.%'
                      AND email LIKE '%@%.%'
                    GROUP BY email
                    ORDER BY SUM(freq) DESC
                    LIMIT :limit
                )
                SELECT email, COALESCE(name, '') AS name, total_interactions, last_interaction, sources
                FROM ranked
                ORDER BY total_interactions DESC
            """)
            rows = db.execute(sql, params).fetchall()
            return [
                {
                    "email": row[0],
                    "name": row[1].strip().strip('"').strip("'").strip() if row[1] else "",
                    "total_interactions": row[2],
                    "last_interaction": str(row[3]) if row[3] else None,
                    "sources": list(row[4]) if row[4] else [],
                }
                for row in rows
            ]
        finally:
            db.close()


search_service = SearchService()
