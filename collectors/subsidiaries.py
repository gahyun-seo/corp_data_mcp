# collectors/subsidiaries.py
import pandas as pd
from ..config import dart
from ..utils.conversions import coalesce_col
from ..utils.logging_utils import get_logger

log = get_logger("subsidiaries")

CHILD_CODE_CANDS = ["inv_prmttd_corp_code","corp_code","afflt_corp_code","child_corp_code","inv_corp_code"]
CHILD_NAME_CANDS = ["inv_prmttd_corp_nm","afflt_corp_nm","child_corp_nm","corp_nm","nm","company_nm"]  # "corp_name" 제거!
REL_CANDS = ["rltn","relation","rel","rltn_type","관계"]
RATIO_CANDS = ["hold_ratio","posesn_rate","hold_rto","bsis_posesn_rate","지분율"]
NOTE_CANDS = ["rm","etc","remark","비고"]

def fetch_and_save(conn, stock_code, corp_name, year, prefer_rc=("11012","11011")):
    for rc in prefer_rc:
        try:
            df = dart.report(stock_code, "타법인출자", year, reprt_code=rc)
            if isinstance(df, pd.DataFrame) and not df.empty:
                child_code = coalesce_col(df, CHILD_CODE_CANDS)
                child_name = coalesce_col(df, CHILD_NAME_CANDS)
                relation  = coalesce_col(df, REL_CANDS, default=None)
                ratio     = coalesce_col(df, RATIO_CANDS, default=None)
                notes     = coalesce_col(df, NOTE_CANDS, default=None)

                out = pd.DataFrame({
                    "parent_stock_code": stock_code,
                    "corp_name": corp_name,                     # 부모 명칭(조회 주체)
                    "child_stock_code": child_code,
                    "child_corp_name": child_name,
                    "relation_type": relation,
                    "shareholding": pd.to_numeric(ratio, errors="coerce"),
                    "notes": notes
                })
                # 자회사명이 부모와 같은 행은 제거
                out = out[out["child_corp_name"].astype(str).str.strip() != str(corp_name).strip()]
                # 완전히 비어있는 행 제거
                out = out[out[["child_stock_code","child_corp_name","shareholding","relation_type"]].notna().any(axis=1)]

                if not out.empty:
                    out.to_sql("subsidiaries", conn, if_exists="append", index=False)
                    conn.commit()
                    log.info(f"Subsidiaries saved: {stock_code} ({len(out)})")
                    return True
        except Exception as e:
            log.warning(f"subs error {stock_code} {rc}: {e}")
    log.warning(f"No subsidiaries: {stock_code}")
    return False
