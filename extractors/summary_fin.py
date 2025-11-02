# mcp_db/extractors/summary_fin.py
from __future__ import annotations

import json
import re
import warnings
from typing import List, Tuple, Optional

import pandas as pd
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from ..utils.logging_utils import get_logger
from ..config import dart

from io import StringIO  # ← 추가

log = get_logger("summary_fin")

# HTML을 XML 파서로 읽을 때 경고 억제 (lxml 사용)
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# ─────────────────────────────────────────────────────────────────────────────
# 텍스트 정규화 & 섹션 매칭 정규식
# ─────────────────────────────────────────────────────────────────────────────

NBSP = "\u00A0"
FW_DOT = "\uFF0E"  # '．'
ROMAN_UNI = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ"
ROMAN_ASC = "I II III IV V VI VII VIII IX X".split()

# LV1: III./Ⅲ. 재무에 관한 사항
LV1_RE = re.compile(
    r"(?:^[\s\(\)\[\]-]*"
    r"(?:[0-9]+|[IⅤVⅩXⅠⅡⅢⅣⅤⅥⅦⅧⅨ]+|[가-힣])?\s*[\.\)]?\s*)?"
    r"재무\s*에?\s*관한\s*사항"
    r"(?:\s*[\(\)\[\]‐\-–—·\:：]*.*)?$"
)

# LV2: 1. 요약재무정보 (공백/마침표 유연)
LV2_RE = re.compile(r"요약\s*재무\s*정보")


# LV3: 가. 요약연결재무정보 (가/나/다 + . 또는 ) 허용)
LV3_RE = re.compile(r"[가-힣]\s*[\.\)]?\s*요약\s*연결\s*재무\s*정보")


def _normalize_text(s: str) -> str:
    """공백·전각·로마숫자·nbsp 등을 정규화"""
    if s is None:
        return ""
    t = s.replace(NBSP, " ").replace(FW_DOT, ".")
    # 전각/유니코드 로마숫자를 ASCII 로 치환(대충만: Ⅰ→I, Ⅱ→II, Ⅲ→III ...)
    for u, a in zip(ROMAN_UNI, ROMAN_ASC):
        t = t.replace(u, a)
    # 다중 공백 축소
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _iter_heading_nodes(soup: BeautifulSoup):
    """
    보고서에서 제목이 될 만한 모든 노드를 문서 순서대로 순회.
    h1~h4, p, div, span, b, strong 등 텍스트 노드를 대상으로 한다.
    """
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "p", "div", "span", "b", "strong"]):
        txt = _normalize_text(tag.get_text(" ", strip=True))
        if txt:
            yield tag, txt


def _seek_section_chain(soup: BeautifulSoup) -> Tuple[Optional[object], Optional[object], Optional[object]]:
    """
    LV1 → LV2 → LV3 순으로 최초로 나타나는 노드를 찾는다.
    실패 시 해당 수준(None)을 반환.
    """
    lv1 = lv2 = lv3 = None
    # 1) LV1 찾기
    for node, txt in _iter_heading_nodes(soup):
        if LV1_RE.search(txt):
            lv1 = node
            break
    if not lv1:
        return None, None, None

    # 2) LV1 이후에서 LV2 찾기
    cur = lv1
    while True:
        cur = cur.find_next()
        if cur is None:
            break
        # 태그만 검사
        if not hasattr(cur, "get_text"):
            continue
        txt = _normalize_text(cur.get_text(" ", strip=True))
        if LV2_RE.search(txt):
            lv2 = cur
            break
    if not lv2:
        return lv1, None, None

    # 3) LV2 이후에서 LV3 찾기
    cur = lv2
    while True:
        cur = cur.find_next()
        if cur is None:
            break
        if not hasattr(cur, "get_text"):
            continue
        txt = _normalize_text(cur.get_text(" ", strip=True))
        if LV3_RE.search(txt):
            lv3 = cur
            break

    return lv1, lv2, lv3


def _extract_first_table_after(node) -> Optional[pd.DataFrame]:
    """
    주어진 노드 이후에 처음 등장하는 <table> 하나를 pandas로 파싱
    """
    if node is None:
        return None
    table = node.find_next("table")
    if table is None:
        return None
    try:
        # table 하나만 문자열로 넘겨 안전 파싱
        dfs = pd.read_html(str(table))
        if isinstance(dfs, list) and len(dfs) > 0:
            return dfs[0]
        return None
    except Exception as e:
        log.warning(f"read_html failed: {e}")
        return None


def _ensure_summary_raw_table(conn):
    """요약표 원시 저장 테이블(요약연결재무정보) 보장"""
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS summary_fin_raw (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT,
            corp_name  TEXT,
            rcept_no   TEXT,
            section_tag TEXT,
            row_idx    INTEGER,
            row_json   TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
        """
    )
    conn.commit()


def extract_summary_consolidated(conn, stock_code: str, corp_name: str) -> int:
    """
    [III. 재무에 관한 사항] → [1. 요약재무정보] → [가. 요약연결재무정보]
    정확히 이 경로의 첫 번째 표(<table>)를 찾아 summary_fin_raw에 저장.
    반환: 저장 행 수
    """
    _ensure_summary_raw_table(conn)

    # 최신 보고서(rcept_dt 최대) 중 가장 최근 1건의 rcept_no 가져오기
    cur = conn.cursor()
    cur.execute(
        """
        SELECT rcept_no
        FROM reports
        WHERE stock_code=?
        ORDER BY rcept_dt DESC
        LIMIT 1
        """,
        (stock_code,),
    )
    row = cur.fetchone()
    if not row:
        log.warning(f"No report meta for {stock_code}")
        return 0
    rcept_no = row[0]

    # 본문 HTML 가져오기
    try:
        html = dart.document(rcept_no) or ""
    except Exception as e:
        log.warning(f"document() failed {stock_code}: {e}")
        return 0

    if not html:
        log.warning(f"Empty html: {stock_code} {rcept_no}")
        return 0

    # 파싱
    soup = BeautifulSoup(html, "lxml")

    lv1, lv2, lv3 = _seek_section_chain(soup)
    if not lv1:
        log.warning(f"LV1 not found: {stock_code}")
        return 0
    if not lv2:
        log.warning(f"LV2 not found after LV1: {stock_code}")
        return 0
    if not lv3:
        log.warning(f"LV3 not found after LV2: {stock_code}")
        return 0
    
    full_text_norm = _normalize_text(soup.get_text(" ", strip=True))
    if not LV2_RE.search(full_text_norm):
        log.info(f"[diagnose] 본문 전체에 '요약재무정보' 없음 → 첨부 fallback 시도: {stock_code}")

    # LV3 이후 첫 테이블 + 이후
    first_tbl = lv3.find_next("table")
    if first_tbl is None:
        log.warning(f"No table right after LV3: {stock_code}")
        return 0

    records = []
    running_idx = 0  # row_idx를 연속 증가시키기 위한 카운터

    def _append_table(tbl_node, tag_label="요약연결재무정보"):
        nonlocal running_idx, records
        try:
            dfs = pd.read_html(StringIO(str(tbl_node)))
        except Exception as e:
            log.warning(f"read_html failed: {e}")
            return 0
        if not isinstance(dfs, list) or len(dfs) == 0 or dfs[0].empty:
            return 0
        df_local = dfs[0].where(pd.notna(dfs[0]), None)
        cols = [str(c) for c in df_local.columns]
        added = 0
        for i in range(len(df_local)):
            rec = {cols[c]: df_local.iat[i, c] for c in range(len(cols))}
            records.append({
                "stock_code": stock_code,
                "corp_name": corp_name,
                "rcept_no": rcept_no,
                "section_tag": tag_label,  # 스키마 변경 없이 동일 태그 유지
                "row_idx": int(running_idx),
                "row_json": json.dumps(rec, ensure_ascii=False),
            })
            running_idx += 1
            added += 1
        return added

    # 1) 첫 번째 표 (대개 '단위: 백만원'처럼 짧은 안내 표일 수 있음)
    n1 = _append_table(first_tbl)

    # 2) 두 번째 표(실제 수치 테이블) 시도
    second_tbl = first_tbl.find_next("table")
    n2 = 0
    if second_tbl is not None:
        n2 = _append_table(second_tbl)

    total = n1 + n2
    if total > 0:
        pd.DataFrame(records).to_sql("summary_fin_raw", conn, if_exists="append", index=False)
        conn.commit()
        log.info(f"summary_fin_raw saved: {stock_code} ({total})")
        return total

    log.warning(f"No usable tables after LV3: {stock_code}")
    return 0
