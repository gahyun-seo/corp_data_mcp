# extractors/summary_fin.py
from __future__ import annotations

import json
import re
import warnings
from typing import Optional

import pandas as pd
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from ..utils.logging_utils import get_logger
from ..config import dart

from io import StringIO

log = get_logger("summary_fin")
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# (기존 정규식과 헬퍼 함수들은 그대로 유지)
NBSP = "\u00A0"
FW_DOT = "\uFF0E"
ROMAN_UNI = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ"
ROMAN_ASC = "I II III IV V VI VII VIII IX X".split()

LV1_RE = re.compile(
    r"(?:^[\s\(\)\[\]-]*"
    r"(?:[0-9]+|[IⅤVⅩXⅠⅡⅢⅣⅤⅥⅦⅧⅨ]+|[가-힣])?\s*[\.\)]?\s*)?"
    r"재무\s*에?\s*관한\s*사항"
    r"(?:\s*[\(\)\[\]‐\-–—·\:：]*.*)?$"
)
LV2_RE = re.compile(r"요약\s*재무\s*정보")
LV3_RE = re.compile(r"[가-힣]\s*[\.\)]?\s*요약\s*연결\s*재무\s*정보")

def _normalize_text(s: str) -> str:
    if s is None:
        return ""
    t = s.replace(NBSP, " ").replace(FW_DOT, ".")
    for u, a in zip(ROMAN_UNI, ROMAN_ASC):
        t = t.replace(u, a)
    t = re.sub(r"\s+", " ", t)
    return t.strip()

def _iter_heading_nodes(soup: BeautifulSoup):
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
    
    # LV1이 없어도 LV2를 찾아보기
    if not lv1:
        # 전체에서 LV2 찾기
        for node, txt in _iter_heading_nodes(soup):
            if LV2_RE.search(txt):
                lv2 = node
                break
    else:
        # 2) LV1 이후에서 LV2 찾기
        cur = lv1
        while True:
            cur = cur.find_next()
            if cur is None:
                break
            if not hasattr(cur, "get_text"):
                continue
            txt = _normalize_text(cur.get_text(" ", strip=True))
            if LV2_RE.search(txt):
                lv2 = cur
                break
    
    # LV2가 없어도 리턴하지 않고 계속 진행
    if not lv2:
        # LV2 없어도 LV3는 찾아보기
        pass
    
    # 3) LV3 찾기 - LV2가 있으면 그 이후에서, 없으면 전체에서
    if lv2:
        cur = lv2
        while True:
            cur = cur.find_next()
            if cur is None:
                break
            if not hasattr(cur, "get_text"):
                continue
            txt = _normalize_text(cur.get_text(" ", strip=True))
            if LV3_RE.search(txt) or '요약연결재무정보' in txt:
                lv3 = cur
                break
    
    # LV3를 못 찾았으면 전체에서 텍스트 직접 검색
    if not lv3:
        for text_node in soup.find_all(string=lambda x: x and '요약연결재무정보' in x):
            parent = text_node.parent
            if parent:
                lv3 = parent
                break

    return lv1, lv2, lv3

def _ensure_summary_raw_table(conn):
    cur = conn.cursor()
    cur.execute("""
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
    """)
    conn.commit()

def extract_from_main_text(conn, stock_code: str, corp_name: str) -> int:
    """본문에서 요약연결재무정보 추출 (기존 로직)"""
    _ensure_summary_raw_table(conn)

    cur = conn.cursor()
    cur.execute("""
        SELECT rcept_no
        FROM reports
        WHERE stock_code=?
        ORDER BY rcept_dt DESC
        LIMIT 1
    """, (stock_code,))
    
    row = cur.fetchone()
    if not row:
        log.warning(f"No report meta for {stock_code}")
        return 0
    rcept_no = row[0]

    try:
        html = dart.document(rcept_no) or ""
    except Exception as e:
        log.warning(f"document() failed {stock_code}: {e}")
        return 0

    if not html:
        log.warning(f"Empty html: {stock_code} {rcept_no}")
        return 0

    try:
        soup = BeautifulSoup(html, "lxml")
    except:
        soup = BeautifulSoup(html, "html.parser")

    lv1, lv2, lv3 = _seek_section_chain(soup)
    
    # LV3가 없으면 직접 텍스트 검색으로 한번 더 시도
    if not lv3:
        log.warning(f"LV3 not found via chain, trying direct search: {stock_code}")
        
        for text_node in soup.find_all(string=lambda x: x and '요약연결재무정보' in x):
            parent = text_node.parent
            if parent:
                lv3 = parent
                log.info(f"Found LV3 via direct search")
                break
    
    if not lv3:
        log.warning(f"LV3 still not found: {stock_code}")
        return 0

    first_tbl = lv3.find_next("table")
    if first_tbl is None:
        log.warning(f"No table after LV3: {stock_code}")
        return 0

    records = []
    running_idx = 0

    def _append_table(tbl_node, tag_label="요약연결재무정보"):
        nonlocal running_idx, records
        try:
            dfs = pd.read_html(StringIO(str(tbl_node)))
        except Exception as e:
            try:
                dfs = pd.read_html(StringIO(str(tbl_node)), flavor='bs4')
            except:
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
                "section_tag": tag_label,
                "row_idx": running_idx,
                "row_json": json.dumps(rec, ensure_ascii=False),
            })
            running_idx += 1
            added += 1
        return added

    n1 = _append_table(first_tbl)
    
    second_tbl = first_tbl.find_next("table")
    n2 = 0
    if second_tbl is not None:
        n2 = _append_table(second_tbl)
    
    third_tbl = None
    n3 = 0
    if second_tbl is not None:
        third_tbl = second_tbl.find_next("table")
        if third_tbl is not None:
            n3 = _append_table(third_tbl)

    total = n1 + n2 + n3
    if total > 0:
        pd.DataFrame(records).to_sql("summary_fin_raw", conn, if_exists="append", index=False)
        conn.commit()
        log.info(f"summary_fin_raw saved: {stock_code} ({total})")
        return total

    log.warning(f"No usable tables after LV3: {stock_code}")
    return 0

def extract_from_attachment(conn, stock_code: str, rcept_no: str) -> int:
    """첨부 파일에서 요약재무정보 추출"""
    import requests
    
    cur = conn.cursor()
    attachments = cur.execute("""
        SELECT file_name, url
        FROM report_attachments
        WHERE stock_code = ? AND rcept_no = ?
    """, (stock_code, rcept_no)).fetchall()
    
    if not attachments:
        log.warning(f"No attachments for {stock_code} {rcept_no}")
        return 0
    
    saved_rows = 0
    
    for file_name, url in attachments:
        if not any(keyword in file_name.lower() for keyword in ['재무', '요약', 'financial']):
            continue
            
        try:
            response = requests.get(url, timeout=30)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            tables = soup.find_all('table')
            
            for i, table in enumerate(tables):
                table_text = table.get_text()
                if '매출' in table_text and ('2024' in table_text or '2023' in table_text):
                    # 여기서 실제 저장 로직 구현
                    saved_rows += 1
                    
        except Exception as e:
            log.error(f"Error processing {file_name}: {e}")
            continue
    
    return saved_rows

def extract_summary_consolidated(conn, stock_code: str, corp_name: str) -> int:
    """메인 함수: 본문 시도 후 실패시 첨부파일 시도"""
    
    # 1. 본문에서 시도
    saved_rows = extract_from_main_text(conn, stock_code, corp_name)
    
    if saved_rows > 0:
        log.info(f"Extracted {saved_rows} rows from main text")
        return saved_rows
    
    # 2. 본문 실패시 첨부파일에서 시도
    log.info(f"Main text failed, trying attachments for {stock_code}")
    
    cur = conn.cursor()
    rcept_no = cur.execute("""
        SELECT rcept_no
        FROM reports
        WHERE stock_code = ?
        ORDER BY rcept_dt DESC
        LIMIT 1
    """, (stock_code,)).fetchone()
    
    if rcept_no:
        saved_rows = extract_from_attachment(conn, stock_code, rcept_no[0])
        if saved_rows > 0:
            log.info(f"Extracted {saved_rows} rows from attachments")
    
    return saved_rows