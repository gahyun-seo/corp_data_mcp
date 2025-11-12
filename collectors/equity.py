# collectors/equity.py
from __future__ import annotations

import re
import ast
import json
from datetime import datetime
from typing import Optional, Dict, List

import pandas as pd

from ..config import dart, REPRTS
from ..utils.conversions import coalesce_col
from ..utils.logging_utils import get_logger

log = get_logger("equity")

# ──────────────────────────────────────────────────────────────────────────────
# 1) DART가 허용하는 키(전부 순회)
# ──────────────────────────────────────────────────────────────────────────────
ALLOWED_EQUITY_KEYS: List[str] = [
    "조건부자본증권미상환","미등기임원보수","회사채미상환","단기사채미상환","기업어음미상환",
    "채무증권발행","사모자금사용","공모자금사용","임원전체보수승인","임원전체보수유형",
    "주식총수","회계감사","감사용역","회계감사용역계약","사외이사","신종자본증권미상환",
    "증자","배당","자기주식","최대주주","최대주주변동","소액주주","임원","직원",
    "임원개인보수","임원전체보수","개인별보수","타법인출자"
]
# 요청대로: 허용 키 전부 돌림
EQUITY_KEYS_RUN = ALLOWED_EQUITY_KEYS

# ──────────────────────────────────────────────────────────────────────────────
# 2) 섹션별 ‘정밀 매핑’ (존재하면 우선 사용)
# ──────────────────────────────────────────────────────────────────────────────
COLMAP: Dict[str, Dict[str, List[str]]] = {
    "증자": {
        "change_type":   ["isu_knd", "isu_mth_nm", "isu_mth", "kind", "dcd_knd"],
        "change_date":   ["isu_de", "dcd_de", "rcept_dt", "dt", "date", "pay_de", "pay_dt", "decision_de"],
        "before_amount": ["bfnum", "before_amt", "pre_amt", "bf_stock_co", "bf_tot_stock_co"],
        "after_amount":  ["afnum", "after_amt", "post_amt", "af_stock_co", "af_tot_stock_co"],
        "notes":         ["rm", "etc", "remark", "sp_rsn", "purpose"],
    },
    "감자": {
        "change_type":   ["kind", "isu_knd", "chg_knd"],
        "change_date":   ["reduce_de","rcept_dt","dt","date"],
        "before_amount": ["bfnum","bf_stock_co","before_amt"],
        "after_amount":  ["afnum","af_stock_co","after_amt"],
        "notes":         ["rm","etc","remark","sp_rsn"],
    },
    "무상증자": {
        "change_type":   ["kind","isu_knd"],
        "change_date":   ["pay_de","pay_dt","rcept_dt","dt","date"],
        "before_amount": ["bfnum","bf_stock_co","bf_tot_stock_co"],
        "after_amount":  ["afnum","af_stock_co","af_tot_stock_co"],
        "notes":         ["rm","etc","remark","sp_rsn"],
    },
    "자기주식": {
        "change_type":   ["acqs_mth","prch_mthd","kind","type"],
        "change_date":   ["acqs_de","sell_de","dispose_de","rcept_dt","dt","date"],
        "before_amount": ["bfnum","bf_own_co","bf_shr_co","bf_stock_co"],
        "after_amount":  ["afnum","af_own_co","af_shr_co","af_stock_co"],
        "notes":         ["rm","etc","purpose","remark","sp_rsn"],
    },
    "배당": {
        "change_type":   ["dcd_knd","dvdnd_knd","dcd_ty","kind"],
        "change_date":   ["dcd_de","dvdnd_pay_de","rcept_dt","dt","date","pay_de","pay_dt"],
        "before_amount": ["bfnum","pre_tot_stk_co","bf_stock_co","bf_tot_stock_co"],
        "after_amount":  ["afnum","post_tot_stk_co","af_stock_co","af_tot_stock_co"],
        "notes":         ["rm","etc","remark","sp_rsn"],
    },
    "주식총수": {
        "change_type":   ["kind","chg_knd"],
        "change_date":   ["chgd_de","rcept_dt","dt","date"],
        "before_amount": ["bf_tisstk_co","bf_stock_co","bfnum","before_amt","bf_tot_stock_co"],
        "after_amount":  ["af_tisstk_co","af_stock_co","afnum","after_amt","af_tot_stock_co"],
        "notes":         ["rm","etc","remark","sp_rsn"],
    },
    "기타자본": {
        "change_type":   ["kind","chg_knd"],
        "change_date":   ["rcept_dt","dt","date"],
        "before_amount": ["bfnum","bf_stock_co","before_amt"],
        "after_amount":  ["afnum","af_stock_co","after_amt"],
        "notes":         ["rm","etc","remark"],
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# 3) 자동 추정(정밀 매핑이 없을 때 사용)
# ──────────────────────────────────────────────────────────────────────────────
_DATE_CAND = [
    "rcept_dt","dt","date","isu_de","dcd_de","pay_de","pay_dt","decision_de",
    "chgd_de","acqs_de","sell_de","dispose_de","dvdnd_pay_de","reduce_de",
]
_BEFORE_PAT = re.compile(r"^(bf|pre|before|bf_).*", re.IGNORECASE)
_AFTER_PAT  = re.compile(r"^(af|post|after|af_).*", re.IGNORECASE)
NOTES_LIKE  = [
    "rm","etc","remark","sp_rsn","purpose","content","title","sj","cn",
    "비고","기타","사유","내용","notes","note","rmk","etc_cn",
]

def _guess_cols(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    cols = [str(c) for c in df.columns]

    # date
    date_col = next((c for c in _DATE_CAND if c in cols), None)

    # before/after
    before_col = next((c for c in cols if _BEFORE_PAT.match(c)), None)
    after_col  = next((c for c in cols if _AFTER_PAT.match(c)), None)

    # notes
    notes_col  = next((c for c in NOTES_LIKE if c in cols), None)

    return {
        "change_type": None,   # 없으면 키워드명으로 채움
        "change_date": date_col,
        "before_amount": before_col,
        "after_amount": after_col,
        "notes": notes_col,
    }

# ──────────────────────────────────────────────────────────────────────────────
# 4) 유틸
# ──────────────────────────────────────────────────────────────────────────────
def _has_keyword_api() -> bool:
    """dart에 keyword 또는 report(내부에서 keyword 라우팅)가 있으면 True"""
    return hasattr(dart, "keyword") or hasattr(dart, "report")

def _pick(df: pd.DataFrame, keys: Optional[List[str]]):
    return coalesce_col(df, keys or [], default=None)

def _to_date(x) -> Optional[str]:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    s = str(x).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            pass
    if re.fullmatch(r"\d{8}", s):
        try:
            return datetime.strptime(s, "%Y%m%d").date().isoformat()
        except Exception:
            return s
    return s or None

def _normalize_block(stock_code: str, corp_name: str, key: str, df: pd.DataFrame) -> pd.DataFrame:
    """키워드 결과 df → equity_changes 규격으로 변환"""
    cmap = COLMAP.get(key) or _guess_cols(df)

    change_type_s = _pick(df, cmap.get("change_type"))
    change_date_s = _pick(df, cmap.get("change_date"))
    before_s      = _pick(df, cmap.get("before_amount"))
    after_s       = _pick(df, cmap.get("after_amount"))
    notes_s       = _pick(df, cmap.get("notes"))

    out = pd.DataFrame({
        "stock_code":    stock_code,
        "corp_name":     corp_name,
        "change_type":   (change_type_s if change_type_s is not None else pd.Series([key] * len(df))),
        "change_date":   change_date_s.apply(_to_date) if change_date_s is not None else None,
        "before_amount": pd.to_numeric(before_s, errors="coerce") if before_s is not None else None,
        "after_amount":  pd.to_numeric(after_s,  errors="coerce") if after_s  is not None else None,
        "notes":         notes_s,
    })

    # 의미 있는 행만 유지(한 컬럼이라도 값이 있으면)
    use_cols = ["change_type","change_date","before_amount","after_amount","notes"]
    keep = pd.Series([False] * len(out))
    for c in use_cols:
        if c in out.columns and out[c] is not None:
            keep = keep | out[c].notna()
    out = out[keep.fillna(False)]
    if out.empty:
        return out

    # ‘증자’ 세분화(무상/유상 표식), ‘주식총수’에서 감자 추론
    if key == "증자":
        def _tag(ct, note):
            s = (str(ct) if ct is not None else "") + " " + (str(note) if note is not None else "")
            s = s.replace(" ", "")
            if ("무상" in s) or ("무증" in s) or ("bonus" in s.lower()):
                return "무상증자"
            if "유상" in s or "paid-in" in s.lower():
                return "유상증자"
            return "증자"
        out["change_type"] = out.apply(lambda r: _tag(r.get("change_type"), r.get("notes")), axis=1)

    if key == "주식총수":
        def _infer(ct, bf, af):
            try:
                if pd.notna(bf) and pd.notna(af):
                    if af < bf:
                        return "감자"
                    elif af > bf:
                        return ct or "주식총수증가"
            except Exception:
                pass
            return ct or "주식총수"
        out["change_type"] = out.apply(lambda r: _infer(r.get("change_type"), r.get("before_amount"), r.get("after_amount")), axis=1)

    return out

def print_allowed_equity_keys():
    """허용 키 전체를 에러 메시지로부터 추출(개발 확인용)"""
    try:
        dart.keyword(stock_code="005930", key_word="__invalid__", year=2024)
    except Exception as e:
        msg = str(e)
        m = re.search(r"dict_keys\(\[(.*?)\]\)", msg)
        if m:
            items = "[" + m.group(1) + "]"
            keys = ast.literal_eval(items)
            print("ALLOWED_EQUITY_KEYS =", keys)
        else:
            print("원본문:", msg)

# ──────────────────────────────────────────────────────────────────────────────
# 5) 메인 수집 함수
# ──────────────────────────────────────────────────────────────────────────────
def fetch_and_save(conn, stock_code: str, corp_name: str, year: Optional[int] = None):
    """
    1) dart.keyword / dart.report 경로가 있으면 모든 ALLOWED_EQUITY_KEYS × REPRTS 순회
       - 성공 시 정규화하여 equity_changes 적재
    2) (대부분의 환경) keyword 미지원이면 report_tables(최신 보고서)에서 폴백 마이닝
    """
    got = False

    # ── 1) API 경로 시도 ───────────────────────────────────────────────
    if _has_keyword_api():
        for rc, _label in REPRTS:
            for key in EQUITY_KEYS_RUN:
                try:
                    # dart.report가 내부에서 keyword 라우팅하는 래퍼일 수 있음
                    df = None
                    try:
                        df = dart.report(stock_code, key, year, reprt_code=rc)
                    except TypeError:
                        # reprt_code 미지원 래퍼일 수도 있음
                        df = dart.report(stock_code, key, year)

                    if isinstance(df, dict) and df.get("status") == "013":
                        # "조회된 데이타가 없습니다." → 스킵
                        continue
                    if not isinstance(df, pd.DataFrame) or df.empty:
                        continue

                    out = _normalize_block(stock_code, corp_name, key, df)
                    if out.empty:
                        continue

                    # 중복 제거(같은 내용 여러 번 들어온 경우 방어)
                    out = out.drop_duplicates(subset=["stock_code","change_type","change_date","before_amount","after_amount","notes"])
                    out.to_sql("equity_changes", conn, if_exists="append", index=False)
                    conn.commit()
                    got = True
                    log.info(f"Equity saved: {stock_code} {key} {rc} ({len(out)})")
                except Exception as e:
                    log.warning(f"equity error {stock_code} {key} {rc}: {e}")

    # ── 2) 폴백: report_tables에서 마이닝 ─────────────────────────────
    if not got:
        cur = conn.cursor()
        # 최신 보고서만 대상으로 스캔(노이즈 감소)
        cur.execute(
            """
            SELECT t.file_name, t.row_json
            FROM report_tables t
            JOIN vw_reports_latest r
              ON r.stock_code = t.stock_code AND r.rcept_no = t.rcept_no
            WHERE t.stock_code = ?
            """,
            (stock_code,),
        )
        rows = cur.fetchall()

        if not rows:
            log.warning(f"Equity fallback: no report_tables for {stock_code}")
        else:
            # 파일명/내용에서 키워드 후보 추출
            KEYWORDS = [
                "증자","감자","무상증자","자본","배당","자기주식","주식총수",
                "increase","issuance","bonus issue","capital reduction",
                "dividend","treasury","buyback","shares outstanding",
            ]
            batch_out = []

            for fname, row_json in rows:
                low_fname = (fname or "").lower()

                try:
                    rec = json.loads(row_json)
                except Exception:
                    continue

                joined_low = " ".join([str(v).lower() for v in rec.values() if v is not None])
                if not any(k.lower() in low_fname or k.lower() in joined_low for k in KEYWORDS):
                    continue

                # 라벨 분류(간단 규칙)
                label = None
                low_all = (low_fname + " " + joined_low)

                if ("감자" in low_all) or ("capital reduction" in low_all):
                    label = "감자"
                elif ("무상증자" in low_all) or ("bonus issue" in low_all):
                    label = "무상증자"
                elif ("증자" in low_all) or ("issu" in low_all) or ("increase" in low_all):
                    label = "증자"
                elif ("자기주식" in low_all) or ("treasury" in low_all) or ("buyback" in low_all):
                    label = "자기주식"
                elif ("배당" in low_all) or ("dividend" in low_all):
                    label = "배당"
                elif ("주식총수" in low_all) or ("shares outstanding" in low_all):
                    label = "주식총수"
                elif "자본" in low_all or "capital" in low_all:
                    label = "기타자본"

                if not label:
                    continue

                # 매핑 키 선택
                cmap = COLMAP.get(label, {})
                def pick_from_rec(keys: List[str]):
                    for k in keys:
                        if k in rec and rec[k] not in (None, ""):
                            return rec[k]
                    return None

                change_type   = pick_from_rec(cmap.get("change_type", [])) or label
                change_date   = pick_from_rec(cmap.get("change_date", []))
                before_amount = pd.to_numeric(pick_from_rec(cmap.get("before_amount", [])), errors="coerce")
                after_amount  = pd.to_numeric(pick_from_rec(cmap.get("after_amount", [])), errors="coerce")

                # notes: 후보 우선 → 그래도 없다면 행 전체 텍스트 일부
                notes = pick_from_rec(cmap.get("notes", []))
                if notes in (None, ""):
                    # 의미 있는 텍스트 한 줄 정도만 남김
                    notes = None
                    for k in NOTES_LIKE:
                        if k in rec and rec[k]:
                            notes = rec[k]
                            break
                    if notes in (None, ""):
                        # 과도한 저장 방지: 너무 길면 자름
                        txt = " ".join([str(v) for v in rec.values() if v not in (None, "")])
                        notes = (txt[:200] + "...") if len(txt) > 200 else txt

                # 날짜 표준화
                change_date = _to_date(change_date)

                # 유효성(한 컬럼이라도 유의미하면 저장)
                if any(pd.notna([change_type, change_date, before_amount, after_amount, notes])):
                    batch_out.append({
                        "stock_code": stock_code,
                        "corp_name": corp_name,
                        "change_type": change_type,
                        "change_date": change_date,
                        "before_amount": before_amount if pd.notna(before_amount) else None,
                        "after_amount":  after_amount  if pd.notna(after_amount)  else None,
                        "notes": notes,
                    })

            if batch_out:
                out = pd.DataFrame(batch_out)
                out = out.drop_duplicates(subset=["stock_code","change_type","change_date","before_amount","after_amount","notes"])
                out.to_sql("equity_changes", conn, if_exists="append", index=False)
                conn.commit()
                got = True
                log.info(f"Equity (fallback from report_tables) saved: {stock_code} ({len(out)})")

    if not got:
        log.warning(f"No equity changes: {stock_code}")