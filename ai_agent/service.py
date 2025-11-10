# mcp_db/ai_agent/service.py
from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Any

from .loaders import (
    load_docs_for_stocks,
    load_all_stock_codes,
    build_stockname_map,
    load_all_reports_for_stocks,
    load_structured_financial_texts,  # 👈 우리가 방금 만든 함수
)
from .rag import SimpleRAG, Chunk
from .chat_groq import GroqChat

DEFAULT_DB = str(Path(__file__).resolve().parents[1] / "mcp_agent_test.db")

SYSTEM_PROMPT = (
    "너는 한국 기업의 DART 공시를 기반으로 답변하는 AI 비서야.\n\n"
    "아래 CONTEXT에는 여러 회사의 공시에서 뽑은 '표 기반(raw) 재무데이터'와 "
    "'보고서/첨부에서 자른 본문'이 섞여 있다.\n"
    "표 기반 데이터는 다음과 같은 형식으로 들어온다:\n\n"
    "너는 사용자의 질문에서\n"
    "1) 어떤 회사(들)를 말하는지,\n"
    "2) 어떤 표 이름을 말하는지 (예: 연결재무상태표, 연결포괄손익계산서, 연결현금흐름표, 재무제표주석),\n"
    "3) 어떤 연도/분기/접수번호를 말하는지\n"
    "를 먼저 파악한 뒤, CONTEXT 안에서 그에 해당하는 부분을 찾아서 설명해야 한다.\n\n"
    "규칙:\n"
    "- CONTEXT에 전혀 없는 표/주석/연도라면 '자료에 없음'이라고 먼저 말하고, "
    "그 다음에 일반적인 회계 설명을 짧게 덧붙여라.\n"
    "- 숫자는 가능하면 CONTEXT 그대로 써라. 모를 때는 추정하지 마라.\n"
    "- 여러 회사가 CONTEXT에 있으면, 사용자가 말한 회사 것을 먼저 설명하고, "
    "필요하면 다른 회사와 비교해도 된다.\n\n"
    "비서 말투로, 요약, 근거가 된 내용, 해석/의견. 필요한 내용들만 간결하고 친절하게 답변."
    # "1. 요약 (한두 문장)\n"
    # "2. 근거가 된 표/주석 이름과 주요 숫자\n"
    # "3. (선택) 해석/의견\n"
)


class AgentState:
    def __init__(
        self,
        db_path: str,
        stocks: List[str],
        use_all_reports: bool = False,
        max_reports_per_stock: int | None = None,
        rag_mode: str = "hybrid",
        groq_model: str = "llama-3.3-70b-versatile",
    ):
        self.db_path = db_path
        self.stocks = stocks
        self.use_all_reports = use_all_reports
        self.max_reports_per_stock = max_reports_per_stock
        self.rag_mode = rag_mode

        # 1) ★ 표를 텍스트로 미리 뽑아둔다 (질문마다 앞에 깔아줄 거라 RAG에는 안 넣음)
        self.structured_text_map = load_structured_financial_texts(db_path, stocks)

        # 2) 보고서/첨부는 RAG로 쓸 문서만 로드
        if use_all_reports:
            report_docs = load_all_reports_for_stocks(
                db_path,
                stocks,
                max_reports_per_stock=max_reports_per_stock,
                include_attachments=True,
            )
        else:
            report_docs = load_docs_for_stocks(db_path, stocks)

        if not report_docs:
            raise RuntimeError("DB에서 문서를 하나도 불러오지 못했습니다.")

        # 3) 종목코드 ↔ 회사명 맵
        self.code2name = build_stockname_map(report_docs)

        # 4) RAG 인덱스 (보고서/첨부만)
        self.rag = SimpleRAG(
            report_docs,
            chunk_size=1000,
            overlap=200,
            mode=rag_mode,
        )

        # 5) LLM
        self.llm = GroqChat(model=groq_model)

    # ───────────────────────────────
    # 질문에서 종목 추론
    # ───────────────────────────────
    def guess_stocks_from_question(self, q: str) -> List[str]:
        q_low = q.lower()

        # 코드가 직접 들어온 경우
        for c in self.stocks:
            if c in q:
                return [c]

        # 회사명이 들어온 경우
        hits: List[str] = []
        for code, name in self.code2name.items():
            if not name:
                continue
            if name in q or name.lower() in q_low:
                hits.append(code)
        return hits

    # ───────────────────────────────
    # 실제 답변 함수
    # ───────────────────────────────
    def answer(
        self,
        question: str,
        top_k: int = 4,  # ✅ 2. 보고서 RAG는 3~4개만
        explicit_stocks: Optional[List[str]] = None,
        debug: bool = False,
    ) -> dict[str, Any]:

        # 1) 종목 결정
        if explicit_stocks:
            target_stocks = explicit_stocks