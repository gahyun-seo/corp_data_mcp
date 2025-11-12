# mcp_db/extractors/flat_finance.py

from __future__ import annotations
import argparse
import json
import sqlite3
import re
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_DB = str(Path(__file__).resolve().parents[1] / "mcp_agent_test.db")

TABLE_NAME_MAP = {
    "balance_sheet_raw": "연결재무상태표",
    "comprehensive_income_raw": "연결포괄손익계산서",
    "cash_flow_raw": "연결현금흐름표",
    "summary_fin_raw": "요약연결재무정보",
}

TABLE_WHITELISTS: dict[str, set[str]] = {
    "연결재무상태표": {
        "유동자산",
        "현금및현금성자산",
        "단기금융상품",
        "매출채권",
        "재고자산",
        "기타유동금융자산",
        "비유동자산",
        "관계기업 및 공동기업에 대한 투자",
        "유형자산",
        "무형자산",
        "이연법인세자산",
        "기타비유동자산",
        "자산총계",
        "유동부채",
        "매입채무",
        "단기차입금",
        "미지급금",
        "기타유동금융부채",
        "당기법인세부채",
        "비유동부채",
        "장기차입금",
        "비유동충당부채",
        "기타비유동부채",
        "부채총계",
        "자본금",
        "보통주자본금",
        "주식발행초과금",
        "이익잉여금",
        "기타자본항목",
        "비지배지분",
        "자본총계",
    },
    "연결포괄손익계산서": {
        "반기순이익",
        "기타포괄손익",
        "후속적으로 당기손익으로 재분류되지 않는 포괄손익",
        "기타포괄손익-공정가치금융자산평가손익",
        "관계기업 및 공동기업의 기타포괄손익에 대한 지분",
        "후속적으로 당기손익으로 재분류되는 포괄손익",
        "해외사업환산손익",
        "현금흐름위험회피파생상품평가손익",
        "기타",
        "반기총포괄손익",
        "반기포괄손익의 귀속",
        "지배기업 소유주지분",
        "비지배지분",
    },
    "연결현금흐름표": {
        "영업활동현금흐름",
        "영업에서 창출된 현금흐름",
        "반기순이익",
        "이자의 수취",
        "이자의 지급",
        "배당금 수입",
        "법인세 납부액",
        "투자활동현금흐름",
        "재무활동현금흐름",
        "배당금의 지급",
        "단기차입금의 순증가(감소)",
        "장기차입금의 차입",
        "사채 및 장기차입금의 상환",
        "자기주식의 취득",
        "현금및현금성자산의 증가(감소)",
        "기초현금및현금성자산",
        "반기말의 현금및현금성자산",
    },
    "요약연결재무정보": {
        "유동자산",
        "비유동자산",
        "자산총계",
        "유동부채",
        "비유동부채",
        "부채총계",
        "자본금",
        "이익잉여금",
        "자본총계",
        "매출액",
        "영업이익",
        "법인세차감전 순이익",
        "당기순이익",
        "총포괄손익",
    },
}

# 여기에 앞에 붙는 잡기호들 모아둔 거 (점, 중점, 대괄호 등)
BULLET_CHARS = "[](){}ㆍ·•-—"  # <- 이게 문제였음


def normalize_for_match(s: str) -> str:
    if not s:
      return ""
    s = s.strip()

    # ✅ 안전하게 이스케이프한 패턴 만들기
    bullet_escaped = re.escape(BULLET_CHARS)

    # 앞쪽에 붙은 괄호/점/대괄호/공백 제거
    s = re.sub(rf"^[{bullet_escaped}\s]+", "", s)
    # 뒤쪽에 붙은 괄호/점/대괄호/공백 제거
    s = re.sub(rf"[{bullet_escaped}\s]+$", "", s)

    # 중간에 있는 희한한 중점· 도 전부 일반 공백으로
    s = s.replace("ㆍ", " ").replace("·", " ")

    # 연속 공백 1개로
    s = re.sub(r"\s+", " ", s)

    return s


def best_match(name: str, whitelist: set[str]) -> str | None:
    """실제 DB에서 온 name이랑 우리가 가진 화이트리스트 이름이 조금 달라도 붙여주는 함수"""
    if not name:
        return None

    norm_name = normalize_for_match(name)
    norm_map = {normalize_for_match(w): w for w in whitelist}

    # 1) 완전 일치
    if norm_name in norm_map:
        return norm_map[norm_name]

    # 2) 부분 일치 (화이트리스트가 더 짧은 경우)
    for norm_w, raw_w in norm_map.items():
        if norm_w and norm_w in norm_name:
            return raw_w
    # 3) 반대 방향 부분 일치
    for norm_w, raw_w in norm_map.items():
        if norm_name and norm_name in norm_w:
            return raw_w

    return None


def load_financials_latest(conn: sqlite3.Connection, stock_code: str) -> Dict[str, Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT year, period_label, period_order, account_nm, amount
        FROM financials
        WHERE stock_code=?
        ORDER BY year DESC, period_order DESC
        """,
        (stock_code,),
    )
    rows = cur.fetchall()
    out: Dict[str, Dict[str, Any]] = {}
    for year, period_label, period_order, account_nm, amount in rows:
        if not account_nm:
            continue
        key = account_nm.strip()
        label = f"{year}/{period_label}" if period_label else str(year)
        if key not in out:
            out[key] = {}
        if label in out[key]:
            continue
        out[key][label] = amount
    return out


def _pick(obj: dict, *candidates: str) -> Any:
    for c in candidates:
        val = obj.get(c)
        if val not in (None, ""):
            return val
    return None


def load_simple_raw_table(
    conn: sqlite3.Connection,
    table: str,
    stock_code: str,
    pretty_name: str,
) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            SELECT section_tag, row_idx, row_json
            FROM {table}
            WHERE stock_code=?
            ORDER BY row_idx ASC
            """,
            (stock_code,),
        )
    except sqlite3.OperationalError:
        return []

    rows = cur.fetchall()
    items: List[Dict[str, Any]] = []
    whitelist = TABLE_WHITELISTS.get(pretty_name)

    for section_tag, row_idx, row_json in rows:
        try:
            obj = json.loads(row_json)
        except Exception:
            continue

        name_raw = _pick(obj, "col_0", "구분", "구 분", "0")
        current = _pick(obj, "col_1", "col_3", "제57기", "1")
        previous = _pick(obj, "col_2", "col_4", "제56기", "2")

        # 단위행/제목행 버리기
        if (not name_raw or name_raw.strip() == "") and not current and not previous:
            continue
        if isinstance(name_raw, str) and "단위" in name_raw:
            continue

        # 화이트리스트가 있으면 여기서 매칭
        if whitelist is not None:
            matched = best_match(name_raw, whitelist)
            if not matched:
                continue
            name = matched
        else:
            name = name_raw

        items.append(
            {
                "name": name,
                "current": current,
                "previous": previous,
                "section": section_tag or pretty_name,
            }
        )

    return items


def build_company_finance(
    db_path: str,
    stock_code: str,
    include_notes: bool = False,
) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        try:
            financials = load_financials_latest(conn, stock_code)
        except sqlite3.OperationalError:
            financials = {}

        raw_tables: Dict[str, Any] = {}
        for tbl, pretty in TABLE_NAME_MAP.items():
            raw_tables[pretty] = load_simple_raw_table(conn, tbl, stock_code, pretty)

        return {
            "stock_code": stock_code,
            "financials": financials,
            "tables": raw_tables,
            "notes": [],
        }
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--stock", required=True)
    args = parser.parse_args()

    data = build_company_finance(args.db, args.stock)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()