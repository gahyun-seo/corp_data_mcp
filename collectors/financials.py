import pandas as pd
from ..config import dart, REPRTS
from ..utils.conversions import to_num, coalesce_col, get_latest_business_year
from ..utils.logging_utils import get_logger
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

log = get_logger("financials")

PERIOD_MAP = {
    "11013": ("Q1", 1, 1),
    "11012": ("H1", 2, 2),
    "11014": ("Q3", 3, 3),
    "11011": ("FY", 4, 4),
}

def _infer_latest_year(stock_code: str, fallback_year: int) -> int:
    try:
        rep_df = dart.list(stock_code, kind="A", final=True)
        if isinstance(rep_df, pd.DataFrame) and not rep_df.empty:
            rep_df = rep_df.sort_values("rcept_dt", ascending=False)
            for col in ("bsns_year", "year"):
                if col in rep_df.columns:
                    candidates = rep_df[col].dropna()
                    for val in candidates:
                        try:
                            return int(str(val).strip()[:4])
                        except Exception:
                            continue
    except Exception as exc:
        log.debug(f"Year inference failed {stock_code}: {exc}")
    return fallback_year

def _collect_year_rows(stock_code, corp_name, year):
    rows = []
    
    current_year = datetime.now(tz=KST).year
    if year == current_year:
        reprt_codes = ['11012','11013','11014']   # 올해는 반기/분기만
    else:
        reprt_codes = ['11011','11012','11013','11014']  # 과거연도는 연간 포함

    for rc in reprt_codes:
        try:
            fdf = dart.finstate(stock_code, year, reprt_code=rc)
            if isinstance(fdf, pd.DataFrame) and not fdf.empty:
                account = coalesce_col(fdf, ["account_nm","account_id"])
                th_amt  = coalesce_col(fdf, ["thstrm_amount","thstrm_add_amount","thstrm_nm"], default=None)
                sj_div  = coalesce_col(fdf, ["sj_div","sj_nm"])
                fs_div  = coalesce_col(fdf, ["fs_div","fs_nm"])
                
                label, order, q = PERIOD_MAP.get(rc, (rc, 9, None))


                rows.append(pd.DataFrame({
                    "stock_code": stock_code,
                    "corp_name": corp_name,
                    "year": year,               # ← 사업연도(2025 반기/분기도 year=2025로 저장)
                    "reprt_code": rc,
                    "period_label": label,
                    "period_order": order,
                    "quarter": q,
                    "fs_div": fs_div,
                    "sj_div": sj_div,
                    "account_nm": account,
                    "amount": th_amt.map(to_num)
                }))
        except Exception as e:
            log.warning(f"finstate error {stock_code} {year} {rc}: {e}")
    return rows

def fetch_and_save(conn, stock_code, corp_name, year=None):
    cur = conn.cursor()
    target_year = year or get_latest_business_year()  # year를 명시해서 호출할 예정

    # 같은 연도 데이터 갈아끼우기
    cur.execute("DELETE FROM financials WHERE stock_code=? AND year=?", (stock_code, target_year))
    conn.commit()

    rows = _collect_year_rows(stock_code, corp_name, target_year)
    if rows:
        pd.concat(rows, ignore_index=True).to_sql("financials", conn, if_exists="append", index=False)
        conn.commit()
        log.info(f"Financials saved: {stock_code} {target_year} ({len(rows)})")
    else:
        log.warning(f"No financial rows: {stock_code} {target_year}")