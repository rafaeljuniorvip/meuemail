import hashlib
import json
import math

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from config.database import SessionLocal

router = APIRouter(prefix="/api/queries", tags=["queries"])


class SaveQueryRequest(BaseModel):
    title: str
    description: str = ""
    sql: str


def _generate_hash(sql: str, title: str) -> str:
    raw = f"{sql}:{title}"
    return hashlib.md5(raw.encode()).hexdigest()[:8]


@router.post("")
def save_query(req: SaveQueryRequest):
    query_id = _generate_hash(req.sql, req.title)
    db = SessionLocal()
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
                "title": req.title,
                "description": req.description,
                "query_data": json.dumps({"sql": req.sql}),
            },
        )
        db.commit()
        return {"id": query_id, "title": req.title, "link": f"#/query/{query_id}"}
    finally:
        db.close()


@router.get("/{query_id}")
def get_query(query_id: str):
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT id, title, description, query_type, query_data, created_at FROM saved_queries WHERE id = :id"),
            {"id": query_id},
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Query não encontrada")
        query_data = row[4] if isinstance(row[4], dict) else json.loads(row[4])
        return {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "type": row[3],
            "sql": query_data.get("sql", ""),
            "created_at": str(row[5]) if row[5] else None,
        }
    finally:
        db.close()


@router.get("/{query_id}/results")
def get_query_results(
    query_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT title, description, query_type, query_data FROM saved_queries WHERE id = :id"),
            {"id": query_id},
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Query não encontrada")

        title, description, query_type, query_data_raw = row
        query_data = query_data_raw if isinstance(query_data_raw, dict) else json.loads(query_data_raw)
        sql = query_data.get("sql", "")

        if not sql:
            raise HTTPException(status_code=400, detail="Query SQL vazia")

        normalized = sql.strip().rstrip(";").strip()
        upper = normalized.upper()

        if not (upper.startswith("SELECT") or upper.startswith("WITH")):
            raise HTTPException(status_code=400, detail="Apenas queries SELECT são permitidas")

        blocked = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
                    "CREATE", "GRANT", "REVOKE", "EXEC", "EXECUTE"]
        for kw in blocked:
            if kw in upper.split():
                raise HTTPException(status_code=400, detail=f"Keyword '{kw}' não permitido")

        # Count total rows using subquery
        count_sql = text(f"SELECT COUNT(*) FROM ({normalized}) AS _subq")
        try:
            total = db.execute(count_sql).scalar()
        except Exception:
            total = None

        # Execute with pagination
        offset = (page - 1) * per_page
        paginated_sql = text(f"{normalized} LIMIT :_limit OFFSET :_offset")
        result = db.execute(paginated_sql, {"_limit": per_page, "_offset": offset})
        columns = list(result.keys()) if result.returns_rows else []
        rows = result.fetchall() if result.returns_rows else []

        data = [
            dict(zip(columns, [str(v) if v is not None else None for v in r]))
            for r in rows
        ]

        total_count = total if total is not None else len(data)
        total_pages = max(1, math.ceil(total_count / per_page)) if total is not None else 1

        return {
            "query": {
                "title": title,
                "description": description,
                "type": query_type,
                "sql": sql,
            },
            "results": {
                "columns": columns,
                "rows": data,
                "total": total_count,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao executar query: {str(e)}")
    finally:
        db.close()
