# mcp_db/quick_inspect.py
import os
import sqlite3
import pandas as pd

# === 경로 설정 ===
DB_PATH = "mcp_agent.db"
OUTPUT_DIR = "outputs"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# === DB 연결 ===
conn = sqlite3.connect(DB_PATH)

def save_and_show(sql, title, filename):
    """SQL 실행 결과를 화면 출력 + CSV 저장"""
    print(f"\n### {title}")
    df = pd.read_sql(sql, conn)
    if df.empty:
        print("(no rows)")
    else:
        print(df.head(20).to_string(index=False))
        csv_path = os.path.join(OUTPUT_DIR, filename)
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"→ saved to {csv_path}")
    print("-" * 100)

# === 조회 및 저장 ===

save_and_show("""
SELECT stock_code, corp_name, rcept_no, report_nm, rcept_dt, LENGTH(report_text) AS txt_len
FROM reports
ORDER BY rcept_dt DESC
LIMIT 5;
""", "📄 Latest Reports", "reports_latest.csv")

save_and_show("""
SELECT * FROM report_sections
WHERE stock_code='005930'
LIMIT 20;
""", "🗂 Sections (삼성전자)", "sections_005930.csv")

save_and_show("""
SELECT stock_code, file_name, url, parsed
FROM report_attachments
WHERE stock_code='005930';
""", "📎 Attachments (삼성전자)", "attachments_005930.csv")

save_and_show("""
SELECT stock_code, file_name, sheet_name, COUNT(*) AS rows
FROM report_tables
WHERE stock_code='005930'
GROUP BY 1,2,3
ORDER BY rows DESC
LIMIT 10;
""", "📊 Parsed Tables (삼성전자)", "tables_005930.csv")

save_and_show("""
SELECT stock_code, corp_name, year, reprt_code, 매출액, 영업이익, 당기순이익
FROM vw_financials_wide
WHERE stock_code='005930'
ORDER BY year DESC;
""", "💰 Financial Summary (삼성전자)", "financials_005930.csv")

# === 종료 ===
conn.close()
print("\n✅ All exports completed! Check the 'outputs/' folder.")
