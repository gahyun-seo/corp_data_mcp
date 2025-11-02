from __future__ import annotations
from typing import Optional

def cached_report_html(conn, stock_code: str, rcept_no: str) -> Optional[str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT report_text
        FROM reports
        WHERE stock_code=? AND rcept_no=?
        ORDER BY report_id DESC
        LIMIT 1
        """,
        (stock_code, rcept_no),
    )
    row = cur.fetchone()
    return row[0] if row and row[0] else None