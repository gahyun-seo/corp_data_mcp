from __future__ import annotations
import datetime as dt
from typing import Optional

import pandas as pd

from ...config import dart                   # ← 점 3개 (mcp_db/config.py)
from ...utils.logging_utils import get_logger

log = get_logger("reports.listing")
KST = dt.timezone(dt.timedelta(hours=9))

def pick_latest_report(df: pd.DataFrame) -> Optional[pd.Series]:
    if df is None or df.empty:
        return None
    semi = df[df["report_nm"].str.contains("반기보고서", na=False)].sort_values("rcept_dt", ascending=False)
    if not semi.empty:
        return semi.iloc[0]
    return df.sort_values("rcept_dt", ascending=False).iloc[0]

def fetch_and_save_recent(conn, stock_code: str, corp_name: str, years_back: int = 3) -> int:
    """
    최근 years_back년 동안의 정기보고서(사업/반기/분기)를 모두 조회하여 reports 테이블에 저장.
    반환: 저장(신규 삽입)된 건수
    """
    cur = conn.cursor()
    saved = 0
    try:
        rep_df = dart.list(stock_code, kind="A", final=True)
        if not isinstance(rep_df, pd.DataFrame) or rep_df.empty:
            log.warning(f"No regular reports: {stock_code}")
            return 0

        rep_df = rep_df.copy()
        # rcept_dt -> timezone-aware 로 정규화
        if "rcept_dt" in rep_df.columns:
            rep_df["rcept_dt"] = pd.to_datetime(rep_df["rcept_dt"], errors="coerce", utc=True).dt.tz_convert(KST)

        now = dt.datetime.now(tz=KST)
        start_dt = dt.datetime(now.year - (years_back - 1), 1, 1, tzinfo=KST)

        # pandas(TZ-aware) 비교는 둘 다 tz-aware 여야 함
        rep_df = rep_df[rep_df["rcept_dt"] >= pd.Timestamp(start_dt)]

        # 사업/반기/분기만
        mask = rep_df["report_nm"].str.contains("사업보고서|반기보고서|분기보고서", na=False)
        rep_df = rep_df[mask].sort_values("rcept_dt", ascending=True)

        for _, row in rep_df.iterrows():
            rcept_no  = str(row.get("rcept_no") or "").strip()
            report_nm = str(row.get("report_nm") or "").strip()
            rcept_dt  = row.get("rcept_dt")
            rcept_dt  = rcept_dt.date().isoformat() if pd.notna(rcept_dt) else None

            # 본문 스니펫(무거운 파싱은 생략)
            html_snippet = ""
            try:
                html = dart.document(rcept_no)
                if html:
                    html_snippet = html[:200000]
            except Exception:
                pass

            try:
                cur.execute(
                    """
                    INSERT INTO reports (stock_code, corp_name, rcept_no, report_nm, rcept_dt, report_text)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (stock_code, corp_name, rcept_no, report_nm, rcept_dt, html_snippet),
                )
                saved += 1
            except Exception:
                # UNIQUE(rcept_no) 충돌 시 무시
                pass

        conn.commit()
        log.info(f"Recent reports saved: {stock_code} (+{saved})")
        return saved

    except Exception as e:
        log.error(f"fetch_and_save_recent error {stock_code}: {e}")
        return 0