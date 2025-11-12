# mcp_db/ai_agent/service.py
from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Any

from .loaders import (
    load_docs_for_stocks,
    load_all_stock_codes,
    build_stockname_map,
    load_all_reports_for_stocks,
    load_structured_financial_texts,
)
from .rag import SimpleRAG, Chunk
from .chat_groq import GroqChat

DEFAULT_DB = str(Path(__file__).resolve().parents[1] / "mcp_agent_test.db")

SYSTEM_PROMPT = (
    "너는 기업 공시 보고서 전문가야. 사용자가 질문할 때, 회사명(예: 삼성전자, SK하이닉스)과 분석 주제(예: 재무제표, ROE, 손익, 주석 등)가 함께 들어올 수 있다. "
    "먼저 질문 속에서 회사명을 인식하고, 해당 회사의 자료를 CONTEXT에서 사용해 답해. "
    "사용자가 '비교', '분기별', '최근 연도', '투자 관점', '의견', '전략' 같은 말을 하면, CONTEXT 안에 있는 여러 행을 서로 비교하고 스스로 분석해 "
    "추세/증가감소/수익성/안정성 관점으로 2줄 정도 해석을 덧붙여줘.\n"
    "숫자만 나열하지 말고, 숫자/표가 말해주는 방향성을 간결하게 정리해."
    "질문에서 회사명이 여러 개면 각각의 정보를 비교해서 요약해. "
    "단, CONTEXT 안에서 근거를 찾지 못하면 '자료에 없음'이라고 말한 뒤, 일반적인 답을 해."
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

        # 1) 표 텍스트 미리 만들기
        self.structured_text_map = load_structured_financial_texts(db_path, stocks)

        # 2) 보고서/첨부는 RAG 대상으로
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

        # 3) 종목코드 ↔ 회사명
        self.code2name = build_stockname_map(report_docs)

        # 4) RAG
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
        for c in self.stocks:
            if c in q:
                return [c]

        hits: List[str] = []
        for code, name in self.code2name.items():
            if not name:
                continue
            if name in q or name.lower() in q_low:
                hits.append(code)
        return hits

    # ───────────────────────────────
    # 주석 필요 여부
    # ───────────────────────────────
    def _needs_notes(self, question: str) -> bool:
        q = question.lower()
        return ("주석" in q) or ("note" in q)

    def _extract_notes_block(self, text: str) -> str:
        """전체 텍스트에서 [표: 재무제표주석] 부터만 가져온다."""
        marker = "[표: 재무제표주석]"
        if marker not in text:
            return ""
        idx = text.index(marker)
        return text[idx:]

    def _strip_notes_block(self, text: str) -> str:
        """전체 텍스트에서 [표: 재무제표주석] 블록만 제거한다."""
        marker = "[표: 재무제표주석]"
        if marker not in text:
            return text
        before = text.split(marker)[0].rstrip()
        return before

    # ───────────────────────────────
    # 실제 답변
    # ───────────────────────────────
    def answer(
        self,
        question: str,
        top_k: int = 4,
        explicit_stocks: Optional[List[str]] = None,
        debug: bool = False,
    ) -> dict[str, Any]:

        # 1) 종목 결정
        if explicit_stocks:
            target_stocks = explicit_stocks
        else:
            guessed = self.guess_stocks_from_question(question)
            target_stocks = guessed if guessed else self.stocks

        want_notes = self._needs_notes(question)

        # 2) 표 컨텍스트 만들기 (주석만 vs 주석 뺀 나머지)
        structured_parts: List[str] = []
        for s in target_stocks:
            full_txt = self.structured_text_map.get(s)
            if not full_txt:
                continue

            if want_notes:
                # 사용자가 주석을 물었으면 주석만
                notes_only = self._extract_notes_block(full_txt)
                if notes_only:
                    structured_parts.append(notes_only)
            else:
                # 주석 안 물었으면 주석은 떼고 보냄
                main_only = self._strip_notes_block(full_txt)
                if main_only:
                    structured_parts.append(main_only)

        structured_ctx = "\n".join(structured_parts)

        # 3) RAG 보조
        chunks: List[Chunk] = self.rag.retrieve(
            question,
            top_k=top_k,
            allowed_stocks=target_stocks,
            debug=debug,
            retriever=self.rag_mode,
        )
        rag_ctx = self.rag.format_context(chunks)

        # 4) 최종 컨텍스트
        final_ctx = structured_ctx + "\n\n---\n\n" + rag_ctx

        answer_text = self.llm.ask(
            system=SYSTEM_PROMPT,
            user=question,
            context=final_ctx,
        )

        return {
            "answer": answer_text,
            "used_stocks": target_stocks or [],
            "chunks": [
                {
                    "stock_code": c.stock_code,
                    "title": c.title,
                    "text_preview": c.text[:300],
                }
                for c in chunks
            ],
        }


# 싱글턴
_agent: AgentState | None = None

def get_agent() -> AgentState:
    global _agent
    if _agent is None:
        default_stocks = load_all_stock_codes(DEFAULT_DB)
        if not default_stocks:
            default_stocks = ["005930", "000660"]
        _agent = AgentState(
            db_path=DEFAULT_DB,
            stocks=default_stocks,
            use_all_reports=True,
            max_reports_per_stock=3,
            rag_mode="hybrid",
            groq_model="llama-3.3-70b-versatile",
        )
    return _agent