import pandas as pd
from ..config import dart
from ..utils.conversions import coalesce_col
from ..utils.logging_utils import get_logger

log = get_logger("executives")

def fetch_and_save(conn, stock_code, corp_name, year, prefer_rc=("11012","11011")):
    cur = conn.cursor()
    for rc in prefer_rc:
        try:
            df = dart.report(stock_code, "임원", year, reprt_code=rc)
            if isinstance(df, pd.DataFrame) and not df.empty:
                out = {
                    "stock_code": stock_code,
                    "corp_name": corp_name,
                    "name": coalesce_col(df, ["nm"]),
                    "position": coalesce_col(df, ["ofcps","position"]),
                    "birth_date": coalesce_col(df, ["brth_yy","birth"]),
                    "appointment_date": coalesce_col(df, ["ternt_begin_dt","appt_dt"]),
                    "tenure": coalesce_col(df, ["fnl_edt","tenure"]),
                    "shareholding": pd.to_numeric(coalesce_col(df, ["hold_stock_co","hold_stk_co","hold_shr"]), errors="coerce"),
                    "nationality": coalesce_col(df, ["ntnat","nation"]),
                    "bio": coalesce_col(df, ["edu","career","resume"]),
                    "notes": coalesce_col(df, ["rm","etc"])
                }
                out_df = pd.DataFrame(out)
                out_df.to_sql("executives", conn, if_exists="append", index=False)
                conn.commit()
                log.info(f"Executives saved: {stock_code}")
                return True
        except Exception as e:
            log.warning(f"exec error {stock_code} {rc}: {e}")
    log.warning(f"No executives: {stock_code}")
    return False
