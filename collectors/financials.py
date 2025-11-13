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

# collectors/financials.py

def load_latest_snapshot(conn, stock_code: str, year: int | None = None) -> dict[str, float]:
    """
    financials 테이블에서 가장 최근 연도(FY or 지정 year) 한 번 뽑아서
    { '자산총계': 1234..., '부채총계': ..., ... } 같은 dict로 반환
    """
    import pandas as pd

    cur = conn.cursor()

    if year is None:
        row = cur.execute(
            "SELECT MAX(year) FROM financials WHERE stock_code=?",
            (stock_code,)
        ).fetchone()
        if not row or row[0] is None:
            return {}
        year = row[0]

    df = pd.read_sql(
        """
        SELECT account_nm, amount
        FROM financials
        WHERE stock_code = ?
          AND year = ?
          AND reprt_code = '11011'      -- FY 기준 (필요하면 조정)
          AND fs_div LIKE '%연결%'      -- 연결만 사용
        """,
        conn,
        params=[stock_code, year]
    )

    snap = (
        df.groupby("account_nm")["amount"]
        .sum()
        .to_dict()
    )
    return snap

# collectors/financials.py 또는 별도 utils 쪽
def compute_indicators_from_snapshot(snap: dict[str, float]) -> dict[str, float | None]:
    get = lambda k: float(snap.get(k)) if k in snap else None

    asset = get("자산총계")
    debt = get("부채총계")
    equity = get("자본총계")
    ca = get("유동자산")
    cl = get("유동부채")
    ar = get("매출채권")
    inv = get("재고자산")

    revenue = get("매출액")
    op = get("영업이익")
    ni = get("당기순이익")

    # 이자/법인세 (필요시)
    interest = get("이자의 지급")
    tax = get("법인세 납부액")

    def safe_div(x, y):
        return (x / y) if (x is not None and y not in (None, 0)) else None

    return {
        "roe":           safe_div(ni, equity),
        "op_margin":     safe_div(op, revenue),
        "ni_margin":     safe_div(ni, revenue),

        "debt_ratio":    safe_div(debt, equity),
        "current_ratio": safe_div(ca, cl),
        "interest_cov":  safe_div(op, interest),

        "asset_turnover":  safe_div(revenue, asset),
        "equity_turnover": safe_div(revenue, equity),
        "ar_turnover":     safe_div(revenue, ar),
        "inv_turnover":    safe_div(revenue, inv),
    }

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