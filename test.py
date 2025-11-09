# mcp_db/test.py

# 11/2 서가현 마지막 수정 파일
# 삼성전자, SK하이닉스 티커로 db 테스트하는 파일
# mcp_agent_test.db 라는 테스트 전용 DB에 저장
# 돌리는 방법: mcp_db 이전 파일로 경로 이동 후 python -m mcp_db.test
# 필요시 mcp_agent_test.db 파일 삭제 후 재실행하면 초기화됨
# 테스트 전용 파이프라인: 소수 티커로 빠르게 전체 흐름 점검


import time
import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .config import dart
from .database import get_conn, init_tables
from .utils.logging_utils import get_logger
from .utils.conversions import get_latest_business_year
from .collectors.company import fetch_and_save as save_company
from .collectors.reports import fetch_and_save_recent
from .collectors.financials import fetch_and_save as save_financials
from .extractors.summary_fin import extract_summary_consolidated
from .collectors.reports.attachments import index_attachments_for_stock
from .extractors.balance_sheet import extract_balance_sheet
from .extractors.balance_sheet import extract_balance_sheet
from .extractors.comprehensive_income import extract_comprehensive_income
from .extractors.equity_changes import extract_equity_changes
from .extractors.cash_flow import extract_cash_flow
from .extractors.notes import extract_financial_notes


# --- 환경설정 ---
KST = timezone(timedelta(hours=9))
log = get_logger("test")

PACKAGE_ROOT = Path(__file__).resolve().parent
TEST_DB = PACKAGE_ROOT / "mcp_agent_test.db"        # 테스트 전용 DB (mcp_db 폴더 내부)
TEST_CSV = PACKAGE_ROOT / "tickers_test.csv"        # ← CSV도 mcp_db 폴더 내부에 둠

def load_tickers_test():
    """테스트용 CSV 로드 (컬럼: stock_code, corp_name)"""
    if not TEST_CSV.exists():
        raise FileNotFoundError(f"테스트 CSV가 없습니다: {TEST_CSV}")

    df = pd.read_csv(TEST_CSV, dtype={"stock_code": str, "corp_name": str})
    df["stock_code"] = df["stock_code"].str.zfill(6)

    # dart.corp_codes와 merge해서 corp_name 보강 (CSV에 없을 때 대비)
    try:
        codes = dart.corp_codes.copy()
        codes["stock_code"] = codes["stock_code"].astype(str).str.zfill(6)
        df = df.merge(
            codes[["stock_code", "corp_name"]],
            on="stock_code", how="left", suffixes=("", "_dart")
        )
        df["corp_name"] = df["corp_name"].fillna(df["corp_name_dart"])
    except Exception as e:
        log.warning(f"corp_codes 병합 생략({e}); CSV 값만 사용합니다.")

    # 최종 컬럼 정리
    return df[["stock_code", "corp_name"]].dropna()


def run_test_pipeline(drop_tables=True, sleep_sec=0.15):
    """테스트 전용 파이프라인 (삼성/하이닉스 등 소수 티커로 빠르게)"""
    conn = get_conn(db_path=str(TEST_DB))
    init_tables(conn, drop_all=drop_tables)

    tickers = load_tickers_test()
    latest_year = get_latest_business_year()
    years_to_collect = [latest_year - i for i in range(3)]

    for _, r in tickers.iterrows():
        stock = r["stock_code"]
        corp  = r["corp_name"]
        log.info(f"=== [TEST] Processing {stock} - {corp} ===")

        # 1) 기업기본
        save_company(conn, stock, corp)

        # 2) 최근 3년 보고서(메타만) 저장
        fetch_and_save_recent(conn, stock, corp, years_back=3)
        
        # 3) 보고서 첨부파일 인덱싱 (최신 보고서 1건)
        try:
            new_atts = index_attachments_for_stock(conn, stock_code=stock, years_back=3, max_reports=1)
            log.info(f"[TEST] attachments indexed: {stock} (+{new_atts})")
        except Exception as e:
            log.warning(f"[TEST] attachments index failed {stock}: {e}")

        # 4) 재무(최근 3개년)
        for yr in years_to_collect:
            try:
                save_financials(conn, stock, corp, year=yr)
            except Exception as e:
                log.warning(f"Financials fetch failed {stock} {yr}: {e}")

        time.sleep(sleep_sec)
        
        # 5) 요약연결재무정보
        try:
            saved_rows = extract_summary_consolidated(conn, stock, corp)
            log.info(f"[TEST] summary_consolidated saved rows: {stock} -> {saved_rows}")
        except Exception as e:
            log.warning(f"[TEST] summary_consolidated extract failed {stock}: {e}")

        # 6) 연결재무상태표
        try:
            saved_rows = extract_balance_sheet(conn, stock, corp)
            log.info(f"[TEST] balance_sheet saved rows: {stock} -> {saved_rows}")
        except Exception as e:
            log.warning(f"[TEST] balance_sheet extract failed {stock}: {e}")
        
        # 7) 연결포괄손익계산서
        try:
            saved_rows = extract_comprehensive_income(conn, stock, corp)
            log.info(f"[TEST] comprehensive_income saved rows: {stock} -> {saved_rows}")
        except Exception as e:
            log.warning(f"[TEST] comprehensive_income extract failed {stock}: {e}")
        
        # 8) 연결자본변동표
        try:
            saved_rows = extract_equity_changes(conn, stock, corp)
            log.info(f"[TEST] equity_changes saved rows: {stock} -> {saved_rows}")
        except Exception as e:
            log.warning(f"[TEST] equity_changes extract failed {stock}: {e}")
        
        # 9) 연결현금흐름표
        try:
            saved_rows = extract_cash_flow(conn, stock, corp)
            log.info(f"[TEST] cash_flow saved rows: {stock} -> {saved_rows}")
        except Exception as e:
            log.warning(f"[TEST] cash_flow extract failed {stock}: {e}")

        # 10) 연결재무제표 주석 추출
        try:
            saved_rows = extract_financial_notes(conn, stock, corp)
            log.info(f"[TEST] financial_notes saved rows: {stock} -> {saved_rows}")
        except Exception as e:
            log.warning(f"[TEST] financial_notes extract failed {stock}: {e}")

        time.sleep(sleep_sec)


    log.info("[TEST] ✅ All test data collection complete.")
    conn.close()

    # 간단한 집계 출력
    conn = get_conn(db_path=str(TEST_DB))
    cur = conn.cursor()
    
    # 기본 테이블
    print("\n=== 기본 테이블 ===")
    cur.execute("SELECT COUNT(*) FROM reports")
    print(f"reports: {cur.fetchone()[0]}행")
    cur.execute("SELECT COUNT(*) FROM financials")
    print(f"financials: {cur.fetchone()[0]}행")
    
    # 추출된 재무제표 테이블
    print("\n=== 추출된 재무제표 ===")
    tables_to_check = [
        'summary_fin_raw',
        'balance_sheet_raw',
        'comprehensive_income_raw',
        'equity_changes_raw',
        'cash_flow_raw',
        'financial_notes_raw'
    ]
    
    for table_name in tables_to_check:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cur.fetchone()[0]
            print(f"{table_name}: {count}행")

            if table_name == 'financial_notes_raw' and count > 0:
                cur.execute("""
                    SELECT DISTINCT note_number, note_title 
                    FROM financial_notes_raw 
                    ORDER BY CAST(note_number AS INTEGER)
                """)
                notes = cur.fetchall()
                print(f"  - 추출된 주석: {len(notes)}개")
                
                for num, title in notes[:5]:  # 처음 5개만 표시
                    print(f"    {num}. {title[:30]}...")
        except:
            print(f"{table_name}: 테이블 없음")
    
    print(f"\n테스트 DB 경로: {TEST_DB}")
    conn.close()
     
if __name__ == "__main__":
    run_test_pipeline(drop_tables=True, sleep_sec=0.1)