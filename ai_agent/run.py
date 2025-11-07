# mcp_db/ai_agent/run.py
from __future__ import annotations
import argparse
from pathlib import Path
import time

from .loaders import (
    load_docs_for_stocks,
    load_all_stock_codes,
    build_stockname_map,
    load_all_reports_for_stocks,   # ← 추가
)
from .rag import SimpleRAG
from .chat_groq import GroqChat
from .chat import OllamaChat
# 테스트 시 mcp_agent_test.db ------- 실제 경로 mcp_agent.db
DEFAULT_DB = str(Path(__file__).resolve().parents[1] / "mcp_agent_test.db")

SYSTEM_PROMPT = (
    "너는 기업 공시 보고서 전문가야. 아래 CONTEXT는 주어진 회사의 최신 또는 과거 정기보고서 본문/첨부에서 추출한 내용이야. "
    "반드시 CONTEXT에서 근거를 찾아 답하고, 찾지 못했으면 '자료에 없음'이라고 말한 뒤, 너가 스스로 답변을 해."
)

def guess_stocks_from_question(q: str, code_list: list[str], code2name: dict[str, str]) -> list[str]:
    q_low = q.lower()
    for c in code_list:
        if c in q:
            return [c]
    hits = []
    for code, name in code2name.items():
        if not name:
            continue
        if name in q or name.lower() in q_low:
            hits.append(code)
    return hits


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--stocks", default="")
    parser.add_argument("--all", action="store_true", help="reports에 있는 모든 종목 사용")
    parser.add_argument("--all-reports", action="store_true", help="각 종목의 모든 보고서를 DB에서 불러옴")
    parser.add_argument("--max-reports-per-stock", type=int, default=None, help="--all-reports일 때 종목당 최대 보고서 수")
    parser.add_argument("--topk", type=int, default=6)
    parser.add_argument("--provider", default="groq", choices=["groq", "ollama"])
    parser.add_argument("--model", default="mistral")
    parser.add_argument("--groq-model", default="llama-3.3-70b-versatile")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--rag-mode", default="hybrid", choices=["tfidf", "semantic", "hybrid"], help="RAG 검색 모드 선택")
    args = parser.parse_args()

    start_time = time.time()

    print("=" * 80)
    print(f"[INFO] DB 경로: {args.db}")
    print(f"[INFO] Provider: {args.provider}")
    print("=" * 80)

    # 1) 종목 결정
    if args.all:
        stocks = load_all_stock_codes(args.db)
    else:
        if args.stocks.strip():
            stocks = [s.strip() for s in args.stocks.split(",") if s.strip()]
        else:
            stocks = ["005930", "000660"]

    print(f"[INFO] 불러올 종목 수: {len(stocks)}개")
    print(f"[INFO] 대상 종목: {stocks[:10]}{' ...' if len(stocks) > 10 else ''}")
    print("-" * 80)

    # 2) 문서 로드
    print("[STEP 1] 보고서/첨부 문서 불러오는 중...")
    if args.all_reports:
        docs = load_all_reports_for_stocks(
            args.db,
            stocks,
            max_reports_per_stock=args.max_reports_per_stock,
            include_attachments=True,
        )
    else:
        docs = load_docs_for_stocks(args.db, stocks)

    print(f"[RESULT] 총 {len(docs)}개 문서 로드 완료.")
    code2name = build_stockname_map(docs)

    for d in docs[:5]:
        print(f"   - {d.stock_code} | {d.title} | 길이: {len(d.text):,}자")
    if len(docs) > 5:
        print(f"   ... (이하 {len(docs)-5}건 생략)")
    if not docs:
        print("[WARN] 문서를 하나도 불러오지 못했습니다.")
        return
    print("-" * 80)

    # 3) RAG 인덱스
    print("[STEP 2] TF-IDF 인덱스 구축 중...")
    rag = SimpleRAG(docs, chunk_size=1000, overlap=200, mode=args.rag_mode)

    if rag.tfidf_matrix is None and rag.semantic_matrix is None:
        print("[WARN] 인덱스를 하나도 만들지 못했습니다.")
        return
    print(f"[RESULT] 인덱싱된 청크 수: {len(rag.chunks):,}개")
    print("-" * 80)

    # 4) LLM
    if args.provider == "groq":
        llm = GroqChat(model=args.groq_model)
    else:
        llm = OllamaChat(model=args.model)
    print(f"[STEP 3] 모델 준비 완료 → {args.provider} / {llm.model}")
    print("-" * 80)

    # 5) 루프
    print("\n=== AI Report Chat (DB 전체 모드) ===")
    print("질문을 입력하세요. 종료: /exit\n")

    while True:
        q = input("Q> ").strip()
        if q.lower() in ("/exit", "exit", "quit"):
            break

        guessed = guess_stocks_from_question(q, stocks, code2name)
        if guessed:
            print(f"[INFO] 질문에서 감지한 종목: {guessed}")
            chunks = rag.retrieve(q, top_k=args.topk, allowed_stocks=guessed, debug=args.debug, retriever=args.rag_mode)
        else:
            print("[INFO] 종목을 질문에서 못 찾음 → 전체에서 검색")
            chunks = rag.retrieve(q, top_k=args.topk, debug=args.debug, retriever=args.rag_mode)

        print(f"[INFO] 관련 청크 {len(chunks)}개 선택됨.")
        print("[INFO] 질문을 분석하고 문서 검색 중...")
        ctx = rag.format_context(chunks)
        if args.debug:
            print("[DEBUG] context preview:")
            print(ctx[:600])
        print("[INFO] LLM 호출 중...")

        answer = llm.ask(SYSTEM_PROMPT, q, ctx)
        print("\n--- 답변 ---")
        print(answer)
        print("-------------\n")

    print("=" * 80)
    print(f"[END] 전체 실행 시간: {time.time() - start_time:.1f}초")
    print("=" * 80)
    
if __name__ == "__main__":
    main()