# mcp_db/ai_agent/loaders.py
from __future__ import annotations
import warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# bs4가 XML을 HTML로 파싱할 때 내는 경고 끄기
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

import re
import sqlite3
from typing import List, Optional
from io import BytesIO
from dataclasses import dataclass

import requests

from ..config import dart  # 그대로 둔다

import json


try:
    from pdfminer.high_level import extract_text as pdf_extract_text
except Exception:
    pdf_extract_text = None


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "lxml")
    for bad in soup(["script", "style"]):
        bad.decompose()
    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text


@dataclass
class Doc:
    stock_code: str
    corp_name: Optional[str]
    rcept_no: str
    source: str        # 'report_html' | 'report_html_live' | 'attachment_pdf' | 'attachment_html'
    title: str
    text: str
    section: str = ""


def _fetch_attachment(url: str, timeout: int = 30) -> Optional[bytes]:
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.content
    except Exception:
        return None


def _pdf_bytes_to_text(data: bytes) -> str:
    if not data:
        return ""
    if pdf_extract_text is None:
        return ""
    try:
        return pdf_extract_text(BytesIO(data)) or ""
    except Exception:
        return ""


def _html_bytes_to_text(data: bytes) -> str:
    try:
        txt = data.decode("utf-8", errors="ignore")
        return html_to_text(txt)
    except Exception:
        return ""


def build_stockname_map(docs: List[Doc]) -> dict[str, str]:
    m: dict[str, str] = {}
    for d in docs:
        if d.stock_code and d.corp_name and d.stock_code not in m:
            m[d.stock_code] = d.corp_name
    return m


def load_all_stock_codes(db_path: str) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT stock_code
            FROM reports
            WHERE stock_code IS NOT NULL AND stock_code <> ''
            ORDER BY stock_code
        """)
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


# ─────────────────────────────────────────────
# 기존: 종목마다 "가장 최신 1건"만 라이브로 다시 받는 버전
# ─────────────────────────────────────────────
def load_docs_for_stocks(db_path: str, stocks: List[str]) -> List[Doc]:
    conn = sqlite3.connect(db_path)
    out: List[Doc] = []
    try:
        for stock in stocks:
            cur = conn.cursor()
            cur.execute("""
                SELECT rcept_no, corp_name, report_nm
                FROM reports
                WHERE stock_code=?
                ORDER BY rcept_dt DESC
                LIMIT 1
            """, (stock,))
            row = cur.fetchone()
            if not row:
                continue
            rcept_no, corp_name, report_nm = row

            # 1) 매번 DART에서 전체 HTML 다시
            try:
                html = dart.document(rcept_no) or ""
            except Exception:
                html = ""
            if html:
                out.append(
                    Doc(
                        stock_code=stock,
                        corp_name=corp_name,
                        rcept_no=rcept_no,
                        source="report_html_live",
                        title=f"{corp_name or stock} 보고서({rcept_no})",
                        text=html_to_text(html),
                    )
                )

            # 2) 첨부도 추가
            out.extend(_load_attachment_docs(conn, stock, rcept_no, limit=5))
    finally:
        conn.close()
    return out


def _load_attachment_docs(conn: sqlite3.Connection, stock_code: str, rcept_no: str, limit: int = 5) -> List[Doc]:
    cur = conn.cursor()
    cur.execute("""
        SELECT corp_name, file_name, url
        FROM report_attachments
        WHERE stock_code=? AND rcept_no=?
        ORDER BY id ASC
        LIMIT ?
    """, (stock_code, rcept_no, limit))
    ret: List[Doc] = []
    for corp_name, fname, url in cur.fetchall():
        data = _fetch_attachment(url)
        if not data:
            continue
        lower = (fname or "").lower()
        if lower.endswith(".pdf") or "pdf" in lower:
            text = _pdf_bytes_to_text(data)
            if text:
                ret.append(Doc(stock_code, corp_name, rcept_no, "attachment_pdf", f"{corp_name} [{fname}]", text))
        else:
            text = _html_bytes_to_text(data)
            if text:
                ret.append(Doc(stock_code, corp_name, rcept_no, "attachment_html", f"{corp_name} [{fname}]", text))
    return ret


# ─────────────────────────────────────────────
# 새로 추가: “DB에 있는 보고서 전부” 불러오는 버전
#   - DART 다시 때리지 않고, reports.report_text 그대로 씀
#   - 종목별로 N건 제한 가능
# ─────────────────────────────────────────────
def load_all_reports_for_stocks(
    db_path: str,
    stocks: List[str],
    max_reports_per_stock: int | None = None,
    include_attachments: bool = True,
) -> List[Doc]:
    conn = sqlite3.connect(db_path)
    out: List[Doc] = []
    try:
        for stock in stocks:
            cur = conn.cursor()
            if max_reports_per_stock:
                cur.execute("""
                    SELECT rcept_no, corp_name, report_nm, report_text
                    FROM reports
                    WHERE stock_code=?
                    ORDER BY rcept_dt DESC
                    LIMIT ?
                """, (stock, max_reports_per_stock))
            else:
                cur.execute("""
                    SELECT rcept_no, corp_name, report_nm, report_text
                    FROM reports
                    WHERE stock_code=?
                    ORDER BY rcept_dt DESC
                """, (stock,))
            rows = cur.fetchall()
            for rcept_no, corp_name, report_nm, report_text in rows:
                if report_text:  # text가 있는 것만
                    out.append(
                        Doc(
                            stock_code=stock,
                            corp_name=corp_name,
                            rcept_no=rcept_no,
                            source="report_html",   # DB에서 온거니까
                            title=f"{corp_name or stock} {report_nm}",
                            text=html_to_text(report_text),
                        )
                    )
                if include_attachments:
                    out.extend(_load_attachment_docs(conn, stock, rcept_no, limit=5))
    finally:
        conn.close()
    return out

def _rows_to_docs_from_table(conn: sqlite3.Connection, table: str, stock_code: str) -> List[Doc]:
    """
    주어진 테이블에서 해당 종목의 행들을 전부 Doc으로 바꾼다.
    테이블마다 컬럼 구성이 달라도 일단 key=value로 나열해서 텍스트를 만든다.
    """
    cur = conn.cursor()
    # stock_code 컬럼 이름이 테이블마다 다를 수 있으면 여기서 조건을 바꿔야 함
    # 일단 네가 추출 파이프라인에서 만든 raw 테이블들은 stock_code / corp_name 거의 다 있을 거라고 가정
    try:
        cur.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in cur.fetchall()]
    except Exception:
        return []

    if "stock_code" in cols:
        cur.execute(f"SELECT * FROM {table} WHERE stock_code = ?", (stock_code,))
    else:
        # stock_code 없으면 그냥 전부
        cur.execute(f"SELECT * FROM {table}")

    rows = cur.fetchall()
    if not rows:
        return []

    docs: List[Doc] = []
    for row in rows:
        row_dict = {col: row[i] for i, col in enumerate(cols)}
        corp_name = row_dict.get("corp_name") or row_dict.get("corp_nm") or None
        # 사람이 읽기 좋게 key=value로 나열
        parts = []
        for k, v in row_dict.items():
            if v is None or v == "":
                continue
            parts.append(f"{k}={v}")
        text = " ; ".join(parts)
        title = f"{corp_name or stock_code} {table} 행"
        docs.append(
            Doc(
                stock_code=stock_code,
                corp_name=corp_name,
                rcept_no=row_dict.get("rcept_no", ""),
                source=f"table:{table}",
                title=title,
                text=text,
                section=table,
            )
        )
    return docs


def load_structured_financial_docs(
    db_path: str,
    stocks: List[str],
    tables: List[str] | None = None,
) -> List[Doc]:
    """
    팀원이 분리해둔 표(raw 테이블)들을 우선 RAG에 올리기 위해 불러오는 함수.
    """
    if tables is None:
        tables = [
            "summary_fin_raw",
            "balance_sheet_raw",
            "comprehensive_income_raw",
            "equity_changes_raw",
            "cash_flow_raw",
            "financial_notes_raw",
        ]

    conn = sqlite3.connect(db_path)
    out: List[Doc] = []
    try:
        for stock in stocks:
            for tbl in tables:
                try:
                    out.extend(_rows_to_docs_from_table(conn, tbl, stock))
                except Exception:
                    # 테이블이 없거나 컬럼이 달라도 전체 파이프라인이 죽지 않게
                    continue
    finally:
        conn.close()
    return out

import sqlite3
import json

import sqlite3
import json

# mcp_db/ai_agent/loaders.py 안에

import sqlite3, json

def load_structured_financial_texts(
    db_path: str,
    stocks: list[str],
    tables: list[str] | None = None,
) -> dict[str, str]:
    """
    각 raw 테이블을 LLM이 읽기 쉬운 텍스트로 변환한다.
    중복되는 stock_code, corp_name, rcept_no 는 위에 한 번만 쓰고
    그 아래에 실제 row_json 값들만 나열해서 길이를 줄인다.
    또한 [표: 재무제표주석] 블록은 한 덩어리로 만들어두고,
    service.py에서 질문에 '주석'이 있으면 이 블록만 뽑아서 보낼 수 있게 한다.
    """
    if tables is None:
        tables = [
            "summary_fin_raw",
            "balance_sheet_raw",
            "comprehensive_income_raw",
            "equity_changes_raw",
            "cash_flow_raw",
            "financial_notes_raw",
        ]

    TABLE_NAME_MAP = {
        "summary_fin_raw": "요약연결재무정보",
        "balance_sheet_raw": "연결재무상태표",
        "comprehensive_income_raw": "연결포괄손익계산서",
        "equity_changes_raw": "연결자본변동표",
        "cash_flow_raw": "연결현금흐름표",
        "financial_notes_raw": "재무제표주석",
    }

    conn = sqlite3.connect(db_path)
    stock2lines: dict[str, list[str]] = {s: [] for s in stocks}

    try:
        cur = conn.cursor()
        for tbl in tables:
            # 테이블이 없으면 스킵
            try:
                cur.execute(f"SELECT 1 FROM {tbl} LIMIT 1")
            except Exception:
                continue

            pretty_name = TABLE_NAME_MAP.get(tbl, tbl)

            for stock in stocks:
                if tbl == "financial_notes_raw":
                    # ───────── 주석 테이블은 note 번호 단위로 묶기 ─────────
                    cur.execute(
                        f"""
                        SELECT
                            corp_name,
                            rcept_no,
                            note_number,
                            note_title,
                            section_tag,
                            row_idx,
                            row_json
                        FROM {tbl}
                        WHERE stock_code=?
                        ORDER BY CAST(note_number AS INTEGER) ASC, row_idx ASC
                        """,
                        (stock,),
                    )
                    rows = cur.fetchall()
                    if not rows:
                        continue

                    lines = stock2lines[stock]
                    lines.append(f"[표: {pretty_name}]")  # 이걸로 나중에 서비스에서 구분할 거임

                    current_rcept = None
                    current_note = None

                    for (
                        corp_name,
                        rcept_no,
                        note_number,
                        note_title,
                        section_tag,
                        row_idx,
                        row_json,
                    ) in rows:
                        if rcept_no != current_rcept:
                            lines.append(f"- 보고서 {rcept_no}")
                            current_rcept = rcept_no
                            current_note = None  # 새 보고서면 노트도 초기화

                        note_id = (note_number or "") + (note_title or "")
                        if note_id != current_note:
                            # 주석 헤더
                            title_part = ""
                            if note_number:
                                title_part = f"주석 {note_number}"
                            if note_title:
                                if title_part:
                                    title_part += f". {note_title}"
                                else:
                                    title_part = note_title
                            lines.append(f"  - {title_part}")
                            current_note = note_id

                        # 실제 행 내용 펼치기
                        try:
                            obj = json.loads(row_json)
                            vals = []
                            for k in sorted(obj.keys()):
                                v = obj[k]
                                if not v:
                                    continue
                                vals.append(str(v))
                            row_txt = " / ".join(vals)
                        except Exception:
                            row_txt = row_json or ""

                        if row_txt:
                            lines.append(f"    · {row_txt}")

                else:
                    # ───────── 일반 재무표: rcept_no 단위로 묶기 ─────────
                    cur.execute(
                        f"""
                        SELECT
                            corp_name,
                            rcept_no,
                            section_tag,
                            row_idx,
                            row_json
                        FROM {tbl}
                        WHERE stock_code=?
                        ORDER BY rcept_no DESC, row_idx ASC
                        """,
                        (stock,),
                    )
                    rows = cur.fetchall()
                    if not rows:
                        continue

                    lines = stock2lines[stock]
                    lines.append(f"[표: {pretty_name}]")

                    current_rcept = None
                    for (
                        corp_name,
                        rcept_no,
                        section_tag,
                        row_idx,
                        row_json,
                    ) in rows:
                        if rcept_no != current_rcept:
                            lines.append(f"- 보고서 {rcept_no}")
                            current_rcept = rcept_no

                        try:
                            obj = json.loads(row_json)
                            vals = []
                            for k in sorted(obj.keys()):
                                v = obj[k]
                                if not v:
                                    continue
                                vals.append(str(v))
                            row_txt = " / ".join(vals)
                        except Exception:
                            row_txt = row_json or ""

                        if row_txt:
                            lines.append(f"  · {row_txt}")
    finally:
        conn.close()

    # 종목별 하나의 큰 문자열로
    return {s: "\n".join(lines) for s, lines in stock2lines.items()}