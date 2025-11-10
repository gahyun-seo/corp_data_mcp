# backend/routers/ai_agent.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional, Any
from ...ai_agent.service import get_agent

router = APIRouter(prefix="/ai", tags=["AI Agent"])

class ChatRequest(BaseModel):
    question: str
    stocks: Optional[List[str]] = None
    top_k: int = 6
    debug: bool = False

@router.post("/chat")
def chat(req: ChatRequest):
    agent = get_agent()
    resp = agent.answer(
        question=req.question,
        top_k=req.top_k,
        explicit_stocks=req.stocks,
        debug=req.debug,
    )
    return resp

@router.get("/stocks")
def list_stocks():
    agent = get_agent()
    return {"stocks": [{"code": c, "name": agent.code2name.get(c