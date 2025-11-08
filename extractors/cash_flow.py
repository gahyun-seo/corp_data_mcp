# extractors/cash_flow.py
from __future__ import annotations

import json
import re
import warnings
from io import StringIO

import pandas as pd
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from ..utils.logging_utils import get_logger
from ..config import dart

log = get_logger("cash_flow")
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

def _ensure_cash_flow_table(conn):
    """연결현금흐름표 테이블 생성"""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cash_flow_raw (
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

def extract_cash_flow(conn, stock_code: str, corp_name: str) -> int:
    """연결현금흐름표 추출 - 실제 작동 버전"""
    _ensure_cash_flow_table(conn)
    
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
    
    # 현금흐름표 섹션 찾기
    target_section = None
    
    # 패턴 1: title 태그
    for title in soup.find_all('title'):
        title_text = title.get_text(strip=True)
        # 2-4, 2-5 등 다양한 번호 가능
        if re.search(r'2-[4-5].*현금\s*흐름표', title_text) or '연결현금흐름표' in title_text:
            target_section = title
            log.info(f"Found via title tag: {title_text}")
            break
    
    # 패턴 2: 텍스트 노드
    if not target_section:
        for text_node in soup.find_all(string=re.compile(r'연결\s*현금\s*흐름표')):
            parent = text_node.parent
            if parent:
                parent_text = parent.get_text(strip=True)
                if len(parent_text) < 100:
                    target_section = parent
                    log.info(f"Found via text node: {parent_text[:50]}")
                    break
    
    if not target_section:
        log.warning(f"Cash flow section not found: {stock_code}")
        return 0
    
    # 테이블 찾기
    current = target_section
    records = []
    running_idx = 0
    tables_processed = 0
    
    # 최대 20개 테이블 확인
    for i in range(20):
        table = current.find_next('table')
        if not table:
            break
        
        # pandas로 읽기
        try:
            dfs = pd.read_html(StringIO(str(table)), header=None)
            if not dfs or dfs[0].empty:
                current = table
                continue
                
            df = dfs[0]
            table_text = df.to_string()
            
            # 현금흐름표 특징 확인
            has_activities = any(act in table_text for act in [
                '영업활동', '투자활동', '재무활동'
            ])
            
            has_cash_items = any(item in table_text for item in [
                '당기순이익', '반기순이익', '조정', '현금및현금성자산',
                '영업에서', '영업으로', '이자', '배당', '법인세'
            ])
            
            log.info(f"Table {i+1}: {df.shape}, activities={has_activities}, items={has_cash_items}")
            
            # 현금흐름표 조건: 활동이 있고, 충분한 행
            if has_activities and has_cash_items and df.shape[0] >= 15:
                log.info(f"  ✅ Processing this table as cash flow")
                
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
                                # 괄호로 된 음수 처리
                                if cleaned.startswith('(') and cleaned.endswith(')'):
                                    cleaned = '-' + cleaned[1:-1]
                                if cleaned.replace('-', '').replace('.', '').isdigit():
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
                        "section_tag": "연결현금흐름표",
                        "row_idx": running_idx,
                        "row_json": json.dumps(row_data, ensure_ascii=False),
                    })
                    running_idx += 1
                
                tables_processed += 1
                
                # 현금흐름표는 보통 1개
                if tables_processed >= 1:
                    break
                    
        except Exception as e:
            log.debug(f"Table {i+1} parsing failed: {e}")
        
        current = table
    
    if records:
        pd.DataFrame(records).to_sql("cash_flow_raw", conn, if_exists="append", index=False)
        conn.commit()
        log.info(f"✅ cash_flow_raw saved: {stock_code} ({len(records)} rows)")
        return len(records)
    
    log.warning(f"No cash flow data extracted: {stock_code}")
    return 0