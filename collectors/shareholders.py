# collectors/shareholders.py
import pandas as pd
import re
from ..config import dart, SH_SECTION_ALIASES
from ..utils.conversions import coalesce_col
from ..utils.logging_utils import get_logger

log = get_logger("shareholders")

def _clean_ratio(s):
    if s is None:
        return None
    s = str(s)
    s = s.replace(",", "").replace("%", "").strip()
    if s == "" or s in ("-", "--"):
        return None
    try:
        return float(s)
    except:
        # '12.34 %p' 같은 경우 숫자만 추출
        m = re.search(r"[-+]?\d*\.?\d+", s)
        return float(m.group()) if m else None

def _save_df(conn, df):
    if df is not None and not df.empty:
        df.to_sql("shareholders", conn, if_exists="append", index=False)
        conn.commit()
        return True
    return False

RATIO_CANDIDATES = [
    "hold_rate",
    "holds_ratio",
    "owns_rt",
    "hold_rto",
    "posesn_rate",
    "posesn_stock_rate",
    "posesn_stock_rt",
    "posesn_ratio",
    "share_ratio",
    "share_rate",
    "hold_stock_rt",
    "hold_stock_rate",
    "rate",
    "지분율",
    "지분율(%)",
    "qota_rt",
]

DATE_CANDIDATES = [
    "rcept_dt",
    "change_dt",
    "change_de",
    "change_on",
    "dt",
    "date",
    "std_dt",
    "as_of_dt",
    "report_dt",
    "event_occur_de",
    " 기준일",
    "기준일자",
]

def fetch_all(conn, stock_code, corp_name, year, prefer_rc=("11012","11011")):
    got = False

    # 보고서 섹션 (최대주주/등)
    for rc in prefer_rc:
        for sec in SH_SECTION_ALIASES:
            try:
                sh = dart.report(stock_code, sec, year, reprt_code=rc)
                if isinstance(sh, pd.DataFrame) and not sh.empty:
                    name_col = coalesce_col(sh, ["nm","shholder_nm","owner_nm","corp_nm","name"])
                    type_col = coalesce_col(sh, ["relate","rel_cd","psitn","rel","title"])
                    ratio_col= coalesce_col(sh, RATIO_CANDIDATES)
                    date_col = coalesce_col(sh, DATE_CANDIDATES, default=None)
                    notes    = coalesce_col(sh, ["rm","etc","remark","비고"])

                    out = pd.DataFrame({
                        "stock_code": stock_code,
                        "corp_name": corp_name,
                        "shareholder_name": name_col,
                        "type": type_col,
                        "holding_ratio": ratio_col.map(_clean_ratio),
                        "change_date": date_col,
                        "notes": notes
                    })
                    out = out[
                        out[["shareholder_name","holding_ratio","change_date"]].notna().any(axis=1)
                    ]
                    if _save_df(conn, out):
                        log.info(f"Shareholders (현황) saved: {stock_code} {sec} {rc}")
                        got = True
                        break
            except Exception as e:
                log.warning(f"shareholders(report:{sec}) error {stock_code}: {e}")
        if got: break

    # 대량보유
    try:
        ms = dart.major_shareholders(stock_code)
        if isinstance(ms, pd.DataFrame) and not ms.empty:
            ratio = coalesce_col(
                ms,
                ["hold_ratio","after_l6mnth_ossos_rt","posesn_stock_rt","posesn_stock_rate","hold_rate"],
                default=None,
            )
            change_date = coalesce_col(ms, DATE_CANDIDATES, default=None)
            out = pd.DataFrame({
                "stock_code": stock_code,
                "corp_name": corp_name,
                "shareholder_name": ms.get("rpt_nm") or ms.get("acq_disp_psn_nm"),
                "type": ms.get("rm") or ms.get("psitn"),
                "holding_ratio": ratio.map(_clean_ratio),
                "change_date": change_date,
                "notes": ms.get("sp_rsn") or ms.get("othr_etc_matter")
            })
            out = out[out[["shareholder_name","holding_ratio","change_date"]].notna().any(axis=1)]
            if _save_df(conn, out):
                log.info(f"Shareholders (대량보유) saved: {stock_code}")
                got = True
    except Exception as e:
        log.warning(f"major_shareholders error {stock_code}: {e}")

    # 임원·주요주주 소유보고
    try:
        mse = dart.major_shareholders_exec(stock_code)
        if isinstance(mse, pd.DataFrame) and not mse.empty:
            change_date = coalesce_col(mse, DATE_CANDIDATES, default=None)
            ratio_series = coalesce_col(
                mse,
                ["after_l6mnth_ossos_rt","posesn_stock_rt","posesn_stock_rate","hold_ratio"],
                default=None,
            )
            out = pd.DataFrame({
                "stock_code": stock_code,
                "corp_name": corp_name,
                "shareholder_name": mse.get("acq_disp_psn_nm"),
                "type": mse.get("psitn"),
                "holding_ratio": pd.to_numeric(ratio_series, errors="coerce"),
                "change_date": change_date,
                "notes": mse.get("othr_etc_matter")
            })
            out = out[out[["shareholder_name","holding_ratio","change_date"]].notna().any(axis=1)]
            if _save_df(conn, out):
                log.info(f"Shareholders (임원·주요주주) saved: {stock_code}")
                got = True
    except Exception as e:
        log.warning(f"major_shareholders_exec error {stock_code}: {e}")

    if not got:
        log.warning(f"No shareholders data: {stock_code}")
