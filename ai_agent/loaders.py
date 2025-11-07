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