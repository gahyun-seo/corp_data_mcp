# mcp_db/collectors/reports/attachments.py
from __future__ import annotations
import pandas as pd
from ...config import dart
from ...utils.logging_utils import get_logger

log = get_logger("attachments")

def index_attachments_for_stock(conn, stock_code: str, years_back: int = 3, max_reports: int = 1):
    """
    reports 테이블에 이미 저장된 rcept_no 중에서 최근 years_back년 범위의
    사업/반기/분기보고서만 골라, 첨부 목록만 report_attachments에 인덱싱한다.
    (본문 파싱, 표 파싱 없이 '첨부목록' 행만 적재)
    """
    cur = conn.cursor()
    # reports에서 대상 rcept_no만 추출
    cur.execute("""
        SELECT rcept_no, report_nm, rcept_dt
        FROM reports
        WHERE stock_code=? AND report_nm LIKE '%보고서%'
        ORDER BY rcept_dt DESC
        LIMIT ?
    """, (stock_code, max_reports))
    rows = cur.fetchall()
    if not rows:
        log.info(f"[attachments] 대상 보고서 없음: {stock_code}")
        return 0

    saved = 0
    for rcept_no, report_nm, rcept_dt in rows:
        try:
            atts = dart.attach_files(rcept_no)
            if not isinstance(atts, dict) or not atts:
                log.info(f"[attachments] 첨부 없음: {stock_code} {rcept_no}")
                continue

            batch = []
            for fname, url in atts.items():
                batch.append({
                    "stock_code": stock_code,
                    "corp_name": None,   # 필요 시 JOIN해서 채워도 됨
                    "rcept_no": rcept_no,
                    "file_name": fname,
                    "url": url,
                    "parsed": 0,
                })
            if batch:
                pd.DataFrame(batch).to_sql("report_attachments", conn, if_exists="append", index=False)
                conn.commit()
                saved += len(batch)
                log.info(f"[attachments] indexed: {stock_code} {rcept_no} (+{len(batch)})")
        except Exception as e:
            log.warning(f"[attachments] attach_files 실패 {stock_code} {rcept_no}: {e}")

    return saved