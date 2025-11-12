import io
import json
import pandas as pd
from .conversions import is_excel_like

def parse_attachment_bytes(stock_code, corp_name, rcept_no, file_name, file_bytes):
    """
    첨부(엑셀/CSV) 바이트를 판다스로 읽고 행 단위 JSON으로 반환
    return: list of dict rows for report_tables
    """
    if not is_excel_like(file_name):
        return []

    buf = io.BytesIO(file_bytes)

    rows = []
    if file_name.lower().endswith(".csv"):
        df = pd.read_csv(buf)
        sheet_items = [("csv", df)]
    else:
        xls = pd.ExcelFile(buf)
        sheet_items = [(s, xls.parse(s)) for s in xls.sheet_names]

    for sheet_name, tdf in sheet_items:
        tdf = tdf.where(pd.notna(tdf), None)
        for i, rowvals in tdf.iterrows():
            row_json = json.dumps({str(k): v for k, v in rowvals.to_dict().items()}, ensure_ascii=False)
            rows.append({
                "stock_code": stock_code,
                "corp_name": corp_name,
                "rcept_no": rcept_no,
                "file_name": file_name,
                "sheet_name": str(sheet_name),
                "row_idx": int(i) if isinstance(i, (int,)) else None,
                "row_json": row_json
            })
    return rows
