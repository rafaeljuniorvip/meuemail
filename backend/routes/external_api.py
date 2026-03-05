from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from services.agent_service import agent_service

router = APIRouter(prefix="/api/v1", tags=["external-api"])


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class QueryResponse(BaseModel):
    answer: str
    tools_used: list
    model: str | None


@router.post("/agent/query", response_model=QueryResponse)
async def agent_query(body: QueryRequest, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado")
    if not user.get("ai_enabled"):
        raise HTTPException(status_code=403, detail="IA não habilitada para esta conta")

    user_id = user.get("id")
    messages = [{"role": "user", "content": body.question}]
    result = await agent_service.chat(messages, user_id=user_id)

    return QueryResponse(
        answer=result.get("response", ""),
        tools_used=result.get("tools_used", []),
        model=result.get("model"),
    )


@router.get("/health")
def health():
    return {"status": "ok", "api": "v1"}
