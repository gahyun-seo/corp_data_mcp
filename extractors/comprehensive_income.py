# extractors/comprehensive_income.py
from __future__ import annotations

import json
import re
import warnings

import pandas as pd
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from ..utils.logging_utils import get_logger
from ..config import dart

log = get_logger("comprehensive_income")
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

def _ensure_comprehensive_income_table(conn):
    """연결포괄손익계산서 테이블 생성"""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS comprehensive_income_raw (
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

def extract_comprehensive_income(conn, stock_code: str, corp_name: str) -> int:
    """연결포괄손익계산서 추출"""
    _ensure_comprehensive_income_table(conn)
    
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
    
    # te 태그 변환
    html = html.replace('<te ', '<td ').replace('</te>', '</td>')
    html = html.replace('<TE ', '<TD ').replace('</TE>', '</TD>')
    
    soup = BeautifulSoup(html, "lxml")
    
    # 포괄손익계산서 찾기
    target = None
    
    # title 태그로 찾기 - 섹션 번호 옵션
    for title_tag in soup.find_all('title'):
        title_text = title_tag.get_text(strip=True)
        # 2-3이 있을 수도, 없을 수도
        if '포괄손익' in title_text and '연결' in title_text:
            target = title_tag
            log.info(f"Found comprehensive income: {title_text}")
            break
    
    # 텍스트로 찾기
    if not target:
        patterns = [
            r'연결\s*포괄손익계산서',
            r'포괄손익계산서',
            r'연결.*포괄.*손익'
        ]
        for pattern in patterns:
            for element in soup.find_all(string=re.compile(pattern)):
                if len(str(element)) < 100:
                    target = element.parent
                    log.info(f"Found via pattern: {pattern}")
                    break
            if target:
                break
    
    if not target:
        log.warning(f"Comprehensive income section not found: {stock_code}")
        return 0
    
    # 테이블 찾기 - 여러 개 가능
    current = target
    tables_to_process = []
    
    for i in range(5):
        table = current.find_next('table')
        if not table:
            break
        
        rows = table.find_all('tr')
        table_text = table.get_text()
        
        # 포괄손익 필수 키워드
        keywords = ['당기순이익', '반기순이익', '기타포괄', '총포괄', '세후']
        keyword_count = sum(1 for kw in keywords if kw in table_text)
        
        # 숫자 데이터 확인
        has_numbers = bool(re.search(r'\d{3,}', table_text.replace(',', '')))
        
        log.info(f"Table {i+1}: {len(rows)} rows, keywords={keyword_count}, has_numbers={has_numbers}")
        
        # 조건: 키워드가 있거나, 3행 이상이면서 숫자가 있음
        if keyword_count > 0 or (len(rows) >= 3 and has_numbers):
            tables_to_process.append(table)
            log.info(f"  -> Added to processing list")
            
            # 포괄손익계산서는 보통 작은 테이블이므로 2개까지만
            if len(tables_to_process) >= 2:
                break
        
        current = table
    
    if not tables_to_process:
        log.warning(f"No comprehensive income tables found: {stock_code}")
        return 0
    
    # 데이터 추출
    records = []
    running_idx = 0
    
    for table in tables_to_process:
        for row in table.find_all('tr'):
            cells = row.find_all(['th', 'td'])
            if not cells:
                continue
            
            row_data = {}
            for cell_idx, cell in enumerate(cells):
                text = cell.get_text(strip=True)
                
                if text in ['', '　', '-']:
                    text = None
                elif text:
                    # 주석 제거
                    text = re.sub(r'\([^)]*\)', '', text).strip()
                    # 숫자 포맷
                    if ',' in text:
                        cleaned = text.replace(',', '')
                        if cleaned.replace('-', '').replace('.', '').isdigit():
                            text = cleaned
                
                row_data[f"col_{cell_idx}"] = text
            
            # 빈 행 스킵
            if all(v is None for v in row_data.values()):
                continue
            
            # 단위 행 스킵
            first_val = str(row_data.get('col_0', ''))
            if '단위' in first_val or '백만원' in first_val:
                continue
            
            records.append({
                "stock_code": stock_code,
                "corp_name": corp_name,
                "rcept_no": rcept_no,
                "section_tag": "연결포괄손익계산서",
                "row_idx": running_idx,
                "row_json": json.dumps(row_data, ensure_ascii=False),
            })
            running_idx += 1
    
    if records:
        pd.DataFrame(records).to_sql("comprehensive_income_raw", conn, if_exists="append", index=False)
        conn.commit()
        log.info(f"✅ comprehensive_income_raw saved: {stock_code} ({len(records)} rows)")
        return len(records)
    
    return 0