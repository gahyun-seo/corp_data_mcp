# extractors/balance_sheet.py
from __future__ import annotations

import json
import re
import warnings
from typing import Optional, Tuple

import pandas as pd
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from ..utils.logging_utils import get_logger
from ..config import dart

from io import StringIO

log = get_logger("balance_sheet")
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# 텍스트 정규화 상수
NBSP = "\u00A0"
FW_DOT = "\uFF0E"

def _normalize_text(s: str) -> str:
    if s is None:
        return ""
    t = s.replace(NBSP, " ").replace(FW_DOT, ".")
    t = re.sub(r"\s+", " ", t)
    return t.strip()

def _ensure_balance_sheet_table(conn):
    """연결재무상태표 테이블 생성"""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS balance_sheet_raw (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT,
            corp_name TEXT,
            rcept_no TEXT,
            section_tag TEXT,
            row_idx INTEGER,
            row_json TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()

def extract_balance_sheet(conn, stock_code: str, corp_name: str) -> int:
    """연결재무상태표 추출 - 개선된 버전"""
    _ensure_balance_sheet_table(conn)
    
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
    
    # CRITICAL: te 태그를 td로 변환 - 이것이 핵심!
    html = html.replace('<te ', '<td ').replace('</te>', '</td>')
    html = html.replace('<TE ', '<TD ').replace('</TE>', '</TD>')
    
    try:
        soup = BeautifulSoup(html, "lxml")
    except:
        soup = BeautifulSoup(html, "html.parser")
    
    # "2-1. 연결 재무상태표" 찾기
    target = None
    
    # 패턴 1: title 태그로 찾기 (DART HTML 특징)
    for title_tag in soup.find_all('title'):
        title_text = title_tag.get_text(strip=True)
        if '2-1' in title_text and '연결' in title_text and '재무상태표' in title_text:
            target = title_tag
            log.info(f"Found via title tag: {title_text}")
            break
    
    # 패턴 2: 일반 텍스트로 찾기
    if not target:
        for element in soup.find_all(string=re.compile(r'2-1.*연결.*재무상태표')):
            if len(str(element)) < 50:
                target = element.parent
                log.info(f"Found via text: {element.strip()}")
                break
    
    if not target:
        log.warning(f"Balance sheet section not found: {stock_code}")
        return 0
    
    # 다음 테이블 찾기 - 실제 재무상태표 테이블
    current = target
    main_table = None
    
    for i in range(5):  # 최대 5개 테이블 확인
        table = current.find_next('table')
        if not table:
            break
            
        # 테이블 내용 확인
        table_text = table.get_text()
        
        # 재무상태표 키워드 확인
        if any(kw in table_text for kw in ['자산', '부채', '자본', '유동자산', '비유동자산']):
            rows = table.find_all('tr')
            if len(rows) > 20:  # 충분한 데이터
                main_table = table
                log.info(f"Found main table with {len(rows)} rows")
                break
        
        current = table
    
    if not main_table:
        log.warning(f"No suitable balance sheet table found: {stock_code}")
        return 0
    
    # 데이터 추출
    records = []
    running_idx = 0
    
    # 모든 행 처리
    rows = main_table.find_all('tr')
    
    for row_idx, row in enumerate(rows):
        # th와 td 모두 찾기
        cells = row.find_all(['th', 'td'])
        
        if not cells:
            continue
        
        # 각 셀의 텍스트 추출
        row_data = {}
        for cell_idx, cell in enumerate(cells):
            # 텍스트 추출 및 정리
            text = cell.get_text(strip=True)
            
            # 빈 값 처리
            if text in ['', '　', '-', '_']:
                text = None
            # 숫자 포맷 처리
            elif text:
                # 괄호 제거 (주석 번호 등)
                text = re.sub(r'\([^)]*\)', '', text).strip()
                # 쉼표가 있는 숫자 처리
                if ',' in text:
                    cleaned = text.replace(',', '').replace(' ', '')
                    if cleaned.replace('-', '').replace('.', '').isdigit():
                        text = cleaned
            
            row_data[f"col_{cell_idx}"] = text
        
        # 모든 값이 None인 행은 스킵
        if all(v is None for v in row_data.values()):
            continue
        
        # 저장
        records.append({
            "stock_code": stock_code,
            "corp_name": corp_name,
            "rcept_no": rcept_no,
            "section_tag": "연결재무상태표",
            "row_idx": running_idx,
            "row_json": json.dumps(row_data, ensure_ascii=False),
        })
        running_idx += 1
    
    # DB 저장
    if records:
        df = pd.DataFrame(records)
        df.to_sql("balance_sheet_raw", conn, if_exists="append", index=False)
        conn.commit()
        log.info(f"✅ balance_sheet_raw saved: {stock_code} ({len(records)} rows)")
        return len(records)
    
    log.warning(f"No data extracted from balance sheet: {stock_code}")
    return 0