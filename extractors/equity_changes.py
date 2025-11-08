# extractors/equity_changes.py
from __future__ import annotations

import json
import re
import warnings
from io import StringIO

import pandas as pd
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from ..utils.logging_utils import get_logger
from ..config import dart

log = get_logger("equity_changes")
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

def _ensure_equity_changes_table(conn):
    """연결자본변동표 테이블 생성"""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS equity_changes_raw (
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

def extract_equity_changes(conn, stock_code: str, corp_name: str) -> int:
    """연결자본변동표 추출 - 실제 작동 버전"""
    _ensure_equity_changes_table(conn)
    
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
    
    # 자본변동표 섹션 찾기 - 여러 패턴 시도
    target_section = None
    
    # 패턴 1: title 태그에서 자본변동표 찾기
    for title in soup.find_all('title'):
        title_text = title.get_text(strip=True)
        # 2-3, 2-4, 2-5 등 다양한 번호 가능
        if re.search(r'2-[3-5].*자본\s*변동표', title_text) or '연결자본변동표' in title_text:
            target_section = title
            log.info(f"Found via title tag: {title_text}")
            break
    
    # 패턴 2: 텍스트 노드에서 찾기
    if not target_section:
        for text_node in soup.find_all(string=re.compile(r'연결\s*자본\s*변동표')):
            parent = text_node.parent
            if parent:
                parent_text = parent.get_text(strip=True)
                if len(parent_text) < 100:  # 제목일 가능성
                    target_section = parent
                    log.info(f"Found via text node: {parent_text[:50]}")
                    break
    
    if not target_section:
        log.warning(f"Equity changes section not found: {stock_code}")
        return 0
    
    # 이제 테이블을 찾되, pd.read_html로 파싱 가능한 테이블 찾기
    current = target_section
    records = []
    running_idx = 0
    tables_processed = 0
    
    # 최대 20개 테이블 확인
    for i in range(20):
        table = current.find_next('table')
        if not table:
            break
        
        # 테이블을 pandas로 읽기 시도
        try:
            # pandas로 읽기
            dfs = pd.read_html(StringIO(str(table)), header=None)
            if not dfs or dfs[0].empty:
                current = table
                continue
                
            df = dfs[0]
            
            # 데이터프레임을 텍스트로 변환해서 확인
            table_text = df.to_string()
            
            # 자본변동표 특징 확인
            has_equity_keywords = any(kw in table_text for kw in [
                '자본금', '이익잉여금', '기타자본', '주식발행초과금', '자본합계'
            ])
            
            has_transactions = any(kw in table_text for kw in [
                '반기순이익', '당기순이익', '배당', '총포괄', '기초', '기말'
            ])
            
            has_date = bool(re.search(r'20\d{2}', table_text))
            
            log.info(f"Table {i+1}: {df.shape}, equity={has_equity_keywords}, trans={has_transactions}, date={has_date}")
            
            # 자본변동표 조건
            if has_equity_keywords and (has_transactions or has_date) and df.shape[0] >= 10:
                log.info(f"  ✅ Processing this table as equity changes")
                
                # 각 행을 JSON으로 저장
                cols = [f"col_{j}" for j in range(len(df.columns))]
                
                for row_idx in range(len(df)):
                    row_data = {}
                    for col_idx, col in enumerate(cols):
                        value = df.iat[row_idx, col_idx]
                        if pd.isna(value):
                            row_data[col] = None
                        else:
                            # 숫자 포맷 정리
                            str_val = str(value)
                            if ',' in str_val:
                                cleaned = str_val.replace(',', '')
                                if cleaned.replace('-', '').replace('.', '').replace('(', '').replace(')', '').isdigit():
                                    row_data[col] = cleaned
                                else:
                                    row_data[col] = str_val
                            else:
                                row_data[col] = str_val
                    
                    # 빈 행 스킵
                    if all(v is None or v == '' for v in row_data.values()):
                        continue
                    
                    # 단위 행 스킵
                    first_val = str(row_data.get('col_0', ''))
                    if '단위' in first_val or '백만원' in first_val:
                        continue
                    
                    records.append({
                        "stock_code": stock_code,
                        "corp_name": corp_name,
                        "rcept_no": rcept_no,
                        "section_tag": "연결자본변동표",
                        "row_idx": running_idx,
                        "row_json": json.dumps(row_data, ensure_ascii=False),
                    })
                    running_idx += 1
                
                tables_processed += 1
                
                # 자본변동표는 보통 1개 테이블
                if tables_processed >= 1:
                    break
                    
        except Exception as e:
            log.debug(f"Table {i+1} parsing failed: {e}")
        
        current = table
    
    if records:
        pd.DataFrame(records).to_sql("equity_changes_raw", conn, if_exists="append", index=False)
        conn.commit()
        log.info(f"✅ equity_changes_raw saved: {stock_code} ({len(records)} rows)")
        return len(records)
    
    log.warning(f"No equity changes data extracted: {stock_code}")
    return 0