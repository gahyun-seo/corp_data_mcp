# backend/routers/finance.py

from fastapi import APIRouter
from ...extractors.flat_finance import build_company_finance
from pathlib import Path

router = APIRouter(prefix="/finance")

@router.get("/{stock_code}")
def get_finance(stock_code: str):
    db_path = Path(__file__).resolve().parents[2] / "mcp_agent_test.db"
    return build_company_finance(str(db_path), stock_code)