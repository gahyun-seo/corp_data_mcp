
import time
from pathlib import Path

import pandas as pd

from datetime import datetime, timezone, timedelta
KST = timezone(timedelta(hours=9))

PACKAGE_ROOT = Path(__file__).resolve().parent
KOSPI_CODES_PATH = PACKAGE_ROOT / "kospi200_codes.csv"



if __package__ is None or __package__ == "":
    import sys

    sys.path.append(str(PACKAGE_ROOT.parent))
    from mcp_db.config import dart
    from mcp_db.database import get_conn, init_tables
    from mcp_db.utils.logging_utils import get_logger
    from mcp_db.utils.conversions import get_latest_business_year
    from mcp_db.collectors.company import fetch_and_save as save_company
    from mcp_db.collectors.reports import (
        fetch_and_save_recent,
        index_sections_and_attachments,
    )
    from mcp_db.collectors.financials import fetch_and_save as save_financials
    from mcp_db.collectors.shareholders import fetch_all as save_shareholders
    from mcp_db.collectors.executives import fetch_and_save as save_executives
    from mcp_db.collectors.subsidiaries import fetch_and_save as save_subs
    from mcp_db.collectors.equity import fetch_and_save as save_equity
else:
    from .config import dart
    from .database import get_conn, init_tables
    from .utils.logging_utils import get_logger
    from .utils.conversions import get_latest_business_year
    from .collectors.company import fetch_and_save as save_company
    from .collectors.reports import fetch_and_save_recent
    from .collectors.financials import fetch_and_save as save_financials
    from .collectors.shareholders import fetch_all as save_shareholders
    from .collectors.executives import fetch_and_save as save_executives
    from .collectors.subsidiaries import fetch_and_save as save_subs
    from .collectors.equity import fetch_and_save as save_equity

log = get_logger("main")

latest_year = datetime.now(tz=KST).year   # 2025
years_to_collect = [latest_year - i for i in range(3)]  # [2025, 2024, 2023]

def load_tickers():
    df = pd.read_csv(KOSPI_CODES_PATH, dtype={"stock_code": str, "corp_name": str})
    df["stock_code"] = df["stock_code"].str.zfill(6)

    codes = dart.corp_codes
    codes["stock_code"] = codes["stock_code"].astype(str).str.zfill(6)
    df = df.merge(codes[["corp_code","corp_name","stock_code"]], on="stock_code", how="left", suffixes=("", "_dart"))
    # corp_name 우선순위: csv > dart
    df["corp_name"] = df["corp_name"].fillna(df["corp_name_dart"])
    return df[["stock_code","corp_name","corp_code"]]

def run_pipeline(drop_tables=True, sleep_sec=0.3):
    conn = get_conn()
    init_tables(conn, drop_all=drop_tables)

    tickers = load_tickers()
    year = get_latest_business_year()
    
    log.info(f"[debug] financials year target = {year}")
    
    latest_year = get_latest_business_year()
    

    for _, r in tickers.iterrows():
        stock = r["stock_code"]
        corp  = r["corp_name"]
        log.info(f"=== Processing {stock} - {corp} ===")

        # 1) 기업기본
        save_company(conn, stock, corp)

        # 2) 최신 보고서 + 본문/섹션/첨부
        fetch_and_save_recent(conn, stock, corp, years_back=3)
        
        # (선택) 첨부 '목록'만 인덱싱하고 싶을 때만 켜기
        # from mcp_db.collectors.reports import index_attachments_for_stock
        # index_attachments_for_stock(conn, stock, years_back=3, max_reports=1)
        
        # rcept_no = fetch_and_save_recent(conn, stock, corp)
        # if rcept_no:
        #     try:
        #         index_sections_and_attachments(conn, stock, corp, rcept_no)
        #     except Exception as e:
        #         log.warning(f"[WARN] Parsing failed {stock} {corp}: {e}")
        
        # 3) 재무
        for yr in years_to_collect:
            try:
                save_financials(conn, stock, corp, year=yr)
            except Exception as e:
                log.warning(f"Financials fetch failed {stock} {yr}: {e}")

        # # 4) 주주 (현황+변동)
        # save_shareholders(conn, stock, corp, year)

        # # 5) 임원
        # save_executives(conn, stock, corp, year)

        # # 6) 자회사
        # save_subs(conn, stock, corp, year)

        # # 7) 자본변동(증감)
        # save_equity(conn, stock, corp, year)

        time.sleep(sleep_sec)

    conn.close()
    log.info("All recent data collection complete.")

if __name__ == "__main__":
    run_pipeline(drop_tables=True, sleep_sec=0.3)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("PRAGMA database_list")
    print("DB files:", cur.fetchall())  # 실제 사용하는 DB 경로 확인

    cur.execute("SELECT COUNT(*) FROM report_tables")
    print("report_tables 전체행:", cur.fetchone()[0])
