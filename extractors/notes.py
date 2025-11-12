from __future__ import annotations

import json
import re
import warnings
from typing import Optional, List, Dict
from io import StringIO

import pandas as pd
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from ..utils.logging_utils import get_logger
from ..config import dart

log = get_logger("notes")
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

def _ensure_notes_table(conn):
    """연결재무제표 주석 테이블 생성"""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS financial_notes_raw (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT,
            corp_name TEXT,
            rcept_no TEXT,
            note_number TEXT,
            note_title TEXT,
            section_tag TEXT,
            row_idx INTEGER,
            row_json TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()

def extract_financial_notes(conn, stock_code: str, corp_name: str) -> int:
    """연결재무제표 주석 추출 - TITLE 태그 기반"""
    _ensure_notes_table(conn)
    
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
    
    # te/TE 태그 변환
    html = html.replace('<te ', '<td ').replace('</te>', '</td>')
    html = html.replace('<TE ', '<TD ').replace('</TE>', '</TD>')
    
    soup = BeautifulSoup(html, "lxml")
    
    # "3. 연결재무제표 주석" 섹션 찾기
    notes_section_title = None
    for title in soup.find_all('title'):
        title_text = title.get_text(strip=True)
        # "3. 연결재무제표 주석" 패턴 매칭
        if re.match(r'^3\.\s*연결재무제표\s*주석', title_text):
            notes_section_title = title
            log.info(f"Found notes section: {title_text}")
            break
    
    if not notes_section_title:
        log.warning(f"Notes section not found: {stock_code}")
        return 0
    
    # 주석 섹션 이후의 모든 TITLE 태그에서 주석 찾기
    all_notes = []
    current = notes_section_title
    
    # 주석 섹션 이후 모든 TITLE 태그 탐색
    while True:
        next_title = current.find_next('title')
        if not next_title:
            break
        
        title_text = next_title.get_text(strip=True)
        
        # "4. " 또는 "5. " 등 다른 대섹션이 나오면 중단 (재무제표 주석 끝)
        if re.match(r'^[4-9]\.\s', title_text):
            log.info(f"End of notes section detected: {title_text}")
            break
        
        # 주석 번호 패턴 매칭: "숫자. 제목" 형태
        # 예: "1. 일반적 사항 (연결)", "2. 중요한 회계처리방침 (연결)"
        match = re.match(r'^(\d{1,2})\.\s+(.+)', title_text)
        if match:
            note_num = match.group(1)
            note_title = match.group(2).strip()
            
            # 영문 제목 부분 제거 (있는 경우)
            # 예: "1. Corporate information..." 같은 영문 제목은 제외
            if not re.search(r'[가-힣]', note_title):
                # 한글이 없으면 스킵
                current = next_title
                continue
            
            # "(연결)" 또는 "(Consolidated)" 제거
            note_title = re.sub(r'\s*\(연결\)\s*$', '', note_title)
            note_title = re.sub(r'\s*\(Consolidated\)\s*$', '', note_title)
            
            # 제목 길이 제한
            if len(note_title) > 100:
                note_title = note_title[:100]
            
            all_notes.append({
                'number': note_num,
                'title': note_title,
                'element': next_title
            })
            
            log.info(f"Found note {note_num}: {note_title}")
        
        current = next_title
    
    if not all_notes:
        log.warning(f"No notes found in section: {stock_code}")
        return 0
    
    log.info(f"Total notes found: {len(all_notes)}")
    
    # 각 주석에 대해 테이블 추출
    records = []
    running_idx = 0
    
    for i, note_info in enumerate(all_notes):
        note_num = note_info['number']
        note_title = note_info['title']
        note_elem = note_info['element']
        
        # 다음 주석의 시작 위치 확인
        if i < len(all_notes) - 1:
            next_note_elem = all_notes[i + 1]['element']
        else:
            next_note_elem = None
        
        # 현재 주석부터 다음 주석까지의 모든 테이블 찾기
        tables_in_note = []
        current_elem = note_elem
        
        # 다음 주석이 나오기 전까지 테이블 수집
        for _ in range(200):  # 최대 200번 반복
            table = current_elem.find_next('table')
            if not table:
                break
            
            # 다음 주석을 지나쳤는지 확인
            if next_note_elem:
                # 테이블이 다음 주석보다 뒤에 있는지 체크
                # (모든 요소를 순회하며 순서 확인)
                all_elements = list(soup.descendants)
                try:
                    table_idx = all_elements.index(table)
                    next_idx = all_elements.index(next_note_elem)
                    if table_idx >= next_idx:
                        break
                except (ValueError, IndexError):
                    # 인덱스를 찾을 수 없으면 중단
                    break
            
            tables_in_note.append(table)
            current_elem = table
        
        log.info(f"Note {note_num}: Found {len(tables_in_note)} tables")
        
        # 각 테이블 파싱 및 저장
        for table_idx, table in enumerate(tables_in_note):
            try:
                # pandas로 테이블 읽기
                dfs = pd.read_html(StringIO(str(table)), header=None)
                if not dfs or dfs[0].empty:
                    continue
                
                df = dfs[0]
                
                # 테이블이 너무 작으면 스킵 (최소 2행)
                if len(df) < 2:
                    continue
                
                # 각 행을 JSON으로 저장
                for row_idx in range(len(df)):
                    row_data = {}
                    
                    for col_idx in range(len(df.columns)):
                        value = df.iat[row_idx, col_idx]
                        
                        if pd.isna(value):
                            row_data[f"col_{col_idx}"] = None
                        else:
                            str_val = str(value)
                            
                            # 숫자 포맷 정리 (쉼표 제거)
                            if ',' in str_val:
                                cleaned = str_val.replace(',', '')
                                # 괄호로 감싸진 음수 처리
                                cleaned = cleaned.replace('(', '-').replace(')', '')
                                # 숫자인지 확인
                                if cleaned.replace('-', '').replace('.', '').isdigit():
                                    row_data[f"col_{col_idx}"] = cleaned
                                else:
                                    row_data[f"col_{col_idx}"] = str_val
                            else:
                                row_data[f"col_{col_idx}"] = str_val
                    
                    # 빈 행 스킵
                    if all(v is None or v == '' or v == 'nan' for v in row_data.values()):
                        continue
                    
                    # 단위 행 스킵 (예: "단위: 백만원")
                    first_val = str(row_data.get('col_0', ''))
                    if '단위' in first_val and ':' in first_val and len(first_val) < 30:
                        continue
                    
                    # 레코드 추가
                    records.append({
                        "stock_code": stock_code,
                        "corp_name": corp_name,
                        "rcept_no": rcept_no,
                        "note_number": note_num,
                        "note_title": note_title,
                        "section_tag": f"table_{table_idx}",
                        "row_idx": running_idx,
                        "row_json": json.dumps(row_data, ensure_ascii=False),
                    })
                    running_idx += 1
                    
            except Exception as e:
                log.debug(f"Error parsing table in note {note_num}, table {table_idx}: {e}")
                continue
    
    # DB 저장
    if records:
        pd.DataFrame(records).to_sql("financial_notes_raw", conn, if_exists="append", index=False)
        conn.commit()
        
        # 저장된 주석 요약
        unique_notes = {}
        for r in records:
            if r["note_number"] not in unique_notes:
                unique_notes[r["note_number"]] = r["note_title"]
        
        sorted_notes = sorted([(int(k), v) for k, v in unique_notes.items()])
        log.info(f"✅ financial_notes_raw saved: {stock_code} ({len(records)} rows)")
        log.info(f"   Extracted notes: {', '.join([f'{n}. {t[:30]}...' if len(t) > 30 else f'{n}. {t}' for n, t in sorted_notes[:5]])}")
        if len(sorted_notes) > 5:
            log.info(f"   ... and {len(sorted_notes) - 5} more notes")
        
        return len(records)
    
    log.warning(f"No notes data extracted: {stock_code}")
    return 0