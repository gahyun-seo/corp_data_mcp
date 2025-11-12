# mcp_db/database.py
import sqlite3
from .config import DB_PATH

DDL = """
CREATE TABLE IF NOT EXISTS companies (
    stock_code TEXT PRIMARY KEY,
    corp_name  TEXT,
    ceo_nm     TEXT,
    sector_code TEXT,
    sector     TEXT,
    address    TEXT,
    homepage   TEXT,
    listing_date TEXT,
    registration_no TEXT
);

-- 보고서 메타 + 본문 샘플
CREATE TABLE IF NOT EXISTS reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT,
    corp_name  TEXT,
    rcept_no   TEXT,
    report_nm  TEXT,
    rcept_dt   TEXT,
    report_text TEXT
);

-- 재무
CREATE TABLE IF NOT EXISTS financials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT,
    corp_name  TEXT,
    year       INTEGER,
    reprt_code TEXT,
    fs_div     TEXT,
    sj_div     TEXT,
    account_nm TEXT,
    amount     REAL,
    period_label TEXT,
    period_order INTEGER,
    quarter INTEGER
);

-- 주주 현황/변동 통합
CREATE TABLE IF NOT EXISTS shareholders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT,
    corp_name  TEXT,
    shareholder_name TEXT,
    type        TEXT,
    holding_ratio REAL,
    change_date TEXT,
    notes       TEXT
);

-- 임원
CREATE TABLE IF NOT EXISTS executives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT,
    corp_name  TEXT,
    name       TEXT,
    position   TEXT,
    birth_date TEXT,
    appointment_date TEXT,
    tenure     TEXT,
    shareholding REAL,
    nationality TEXT,
    bio        TEXT,
    notes      TEXT
);

-- 자회사/타법인 출자
CREATE TABLE IF NOT EXISTS subsidiaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_stock_code TEXT,
    corp_name  TEXT,
    child_stock_code  TEXT,
    child_corp_name   TEXT,
    relation_type     TEXT,
    shareholding      REAL,
    notes             TEXT
);

-- 증자/감자/자본변동
CREATE TABLE IF NOT EXISTS equity_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code   TEXT,
    corp_name    TEXT,
    change_type  TEXT,
    change_date  TEXT,
    before_amount REAL,
    after_amount  REAL,
    notes        TEXT
);

-- 보고서 섹션 인덱스
CREATE TABLE IF NOT EXISTS report_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT,
    corp_name  TEXT,
    rcept_no   TEXT,
    section_title TEXT,
    section_url   TEXT
);

-- 보고서 첨부 인덱스
CREATE TABLE IF NOT EXISTS report_attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT,
    corp_name  TEXT,
    rcept_no   TEXT,
    file_name  TEXT,
    url        TEXT,
    parsed     INTEGER DEFAULT 0
);

-- 첨부 테이블 파싱결과 (원본 행 JSON 보존)
CREATE TABLE IF NOT EXISTS report_tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT,
    corp_name  TEXT,
    rcept_no   TEXT,
    file_name  TEXT,
    sheet_name TEXT,
    row_idx    INTEGER,
    row_json   TEXT
);

-- 요약(요약연결재무정보) 원시 행 저장용
CREATE TABLE IF NOT EXISTS summary_fin_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT,
    corp_name  TEXT,
    rcept_no   TEXT,
    section_tag TEXT,      -- '요약연결재무정보' 등 탐지 라벨
    row_idx    INTEGER,
    row_json   TEXT,       -- 원시 행(JSON)
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

"""

INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_reports_rcept ON reports(rcept_no);
"""

VIEWS_FIN_CFS_BASE = """
-- CFS + 기간 컬럼이 채워진 재무만 사용
DROP VIEW IF EXISTS vw_fin_cfs_long;
CREATE VIEW vw_fin_cfs_long AS
SELECT
  stock_code, corp_name, year, reprt_code,
  fs_div, sj_div, account_nm, amount,
  period_label, period_order, quarter
FROM financials
WHERE fs_div='CFS' AND period_label IS NOT NULL;

-- 계정명 → 표준 메트릭 매핑
DROP VIEW IF EXISTS vw_fin_cfs_metrics_base;
CREATE VIEW vw_fin_cfs_metrics_base AS
SELECT
  stock_code, corp_name, year, reprt_code,
  period_label, period_order, quarter,
  sj_div, account_nm, amount,
  CASE
    -- BS
    WHEN account_nm IN ('유동자산')                                         THEN '유동자산'
    WHEN account_nm IN ('비유동자산','고정자산','비유동자산(고정자산)')      THEN '비유동자산'
    WHEN account_nm IN ('자산총계','총자산')                                 THEN '자산총계'
    WHEN account_nm IN ('유동부채')                                         THEN '유동부채'
    WHEN account_nm IN ('비유동부채','고정부채','비유동부채(고정부채)')      THEN '비유동부채'
    WHEN account_nm IN ('부채총계','총부채')                                 THEN '부채총계'
    WHEN account_nm IN ('자본금','지배기업의자본금')                         THEN '자본금'
    WHEN account_nm IN ('이익잉여금','이익잉여금(결손금)','이익잉여금(누적)') THEN '이익잉여금'
    WHEN account_nm IN ('자본총계','지배기업의소유주지분','지배지분')        THEN '자본총계'

    -- IS/CIS
    WHEN account_nm IN ('매출액','영업수익')                                  THEN '매출액'
    WHEN account_nm IN ('영업이익')                                           THEN '영업이익'
    WHEN account_nm IN ('법인세차감전순이익','법인세비용차감전순이익',
                        '법인세비용차감전이익','법인세비용차감전 계속사업이익')
                                                                         THEN '법인세차감전순이익'
    WHEN account_nm IN ('당기순이익','당기순이익(손실)','분기순이익','반기순이익')
                                                                         THEN '당기순이익'
    WHEN account_nm IN ('총포괄손익','총포괄이익','총포괄손익(손실)','총포괄이익(손실)')
                                                                         THEN '총포괄손익'
    ELSE NULL
  END AS metric
FROM vw_fin_cfs_long;

-- 필요한 메트릭만 필터
DROP VIEW IF EXISTS vw_fin_cfs_metrics_only;
CREATE VIEW vw_fin_cfs_metrics_only AS
SELECT *
FROM vw_fin_cfs_metrics_base
WHERE metric IN (
  '유동자산','비유동자산','자산총계',
  '유동부채','비유동부채','부채총계',
  '자본금','이익잉여금','자본총계',
  '매출액','영업이익','법인세차감전순이익','당기순이익','총포괄손익'
);
"""

VIEWS_FIN_CFS_PERIOD_MATRIX = """
-- period별(=FY/H1/Q1/Q3) 한 줄에 메트릭들을 컬럼으로 피벗
DROP VIEW IF EXISTS vw_fin_period_matrix;
CREATE VIEW vw_fin_period_matrix AS
SELECT
  stock_code,
  corp_name,
  year,
  period_label,
  period_order,
  quarter,

  MAX(CASE WHEN metric='유동자산'              THEN amount END) AS 유동자산,
  MAX(CASE WHEN metric='비유동자산'            THEN amount END) AS 비유동자산,
  MAX(CASE WHEN metric='자산총계'              THEN amount END) AS 자산총계,
  MAX(CASE WHEN metric='유동부채'              THEN amount END) AS 유동부채,
  MAX(CASE WHEN metric='비유동부채'            THEN amount END) AS 비유동부채,
  MAX(CASE WHEN metric='부채총계'              THEN amount END) AS 부채총계,
  MAX(CASE WHEN metric='자본금'                THEN amount END) AS 자본금,
  MAX(CASE WHEN metric='이익잉여금'            THEN amount END) AS 이익잉여금,
  MAX(CASE WHEN metric='자본총계'              THEN amount END) AS 자본총계,

  MAX(CASE WHEN metric='매출액'                THEN amount END) AS 매출액,
  MAX(CASE WHEN metric='영업이익'              THEN amount END) AS 영업이익,
  MAX(CASE WHEN metric='법인세차감전순이익'    THEN amount END) AS 법인세차감전순이익,
  MAX(CASE WHEN metric='당기순이익'            THEN amount END) AS 당기순이익,
  MAX(CASE WHEN metric='총포괄손익'            THEN amount END) AS 총포괄손익

FROM vw_fin_cfs_metrics_only
GROUP BY stock_code, corp_name, year, period_label, period_order, quarter;

-- 보기 좋은 포맷 버전
DROP VIEW IF EXISTS vw_fin_period_matrix_fmt;
CREATE VIEW vw_fin_period_matrix_fmt AS
SELECT
  stock_code, corp_name, year, period_label, period_order, quarter,
  CASE WHEN 유동자산              IS NOT NULL THEN printf('%,.0f', 유동자산) END AS 유동자산,
  CASE WHEN 비유동자산            IS NOT NULL THEN printf('%,.0f', 비유동자산) END AS 비유동자산,
  CASE WHEN 자산총계              IS NOT NULL THEN printf('%,.0f', 자산총계) END AS 자산총계,
  CASE WHEN 유동부채              IS NOT NULL THEN printf('%,.0f', 유동부채) END AS 유동부채,
  CASE WHEN 비유동부채            IS NOT NULL THEN printf('%,.0f', 비유동부채) END AS 비유동부채,
  CASE WHEN 부채총계              IS NOT NULL THEN printf('%,.0f', 부채총계) END AS 부채총계,
  CASE WHEN 자본금                IS NOT NULL THEN printf('%,.0f', 자본금) END AS 자본금,
  CASE WHEN 이익잉여금            IS NOT NULL THEN printf('%,.0f', 이익잉여금) END AS 이익잉여금,
  CASE WHEN 자본총계              IS NOT NULL THEN printf('%,.0f', 자본총계) END AS 자본총계,
  CASE WHEN 매출액                IS NOT NULL THEN printf('%,.0f', 매출액) END AS 매출액,
  CASE WHEN 영업이익              IS NOT NULL THEN printf('%,.0f', 영업이익) END AS 영업이익,
  CASE WHEN 법인세차감전순이익    IS NOT NULL THEN printf('%,.0f', 법인세차감전순이익) END AS 법인세차감전순이익,
  CASE WHEN 당기순이익            IS NOT NULL THEN printf('%,.0f', 당기순이익) END AS 당기순이익,
  CASE WHEN 총포괄손익            IS NOT NULL THEN printf('%,.0f', 총포괄손익) END AS 총포괄손익
FROM vw_fin_period_matrix;

-- 최근 3개 연도만 보기
DROP VIEW IF EXISTS vw_fin_period_matrix_3y;
CREATE VIEW vw_fin_period_matrix_3y AS
WITH yrank AS (
  SELECT stock_code, year,
         DENSE_RANK() OVER (PARTITION BY stock_code ORDER BY year DESC) AS rk
  FROM (SELECT DISTINCT stock_code, year FROM vw_fin_period_matrix)
)
SELECT m.*
FROM vw_fin_period_matrix m
JOIN yrank y
  ON y.stock_code = m.stock_code AND y.year = m.year
WHERE y.rk <= 3
ORDER BY stock_code, year DESC, period_order;

DROP VIEW IF EXISTS vw_fin_period_matrix_3y_fmt;
CREATE VIEW vw_fin_period_matrix_3y_fmt AS
SELECT * FROM vw_fin_period_matrix_3y; -- 필요 시 위의 fmt 로직과 결합 가능
"""

def _ensure_financials_period_columns(conn):
    """financials 테이블에 period 관련 컬럼이 없으면 추가하고 reprt_code 기반 백필"""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(financials)")
    cols = {row[1] for row in cur.fetchall()}

    add_cols = []
    if "period_label" not in cols:
        add_cols.append(("period_label", "TEXT"))
    if "period_order" not in cols:
        add_cols.append(("period_order", "INTEGER"))
    if "quarter" not in cols:
        add_cols.append(("quarter", "INTEGER"))

    for name, typ in add_cols:
        cur.execute(f"ALTER TABLE financials ADD COLUMN {name} {typ}")

    cur.execute("""
        UPDATE financials
        SET
          period_label = CASE reprt_code
            WHEN '11013' THEN 'Q1'
            WHEN '11012' THEN 'H1'
            WHEN '11014' THEN 'Q3'
            WHEN '11011' THEN 'FY'
            ELSE period_label END,
          period_order = CASE reprt_code
            WHEN '11013' THEN 1
            WHEN '11012' THEN 2
            WHEN '11014' THEN 3
            WHEN '11011' THEN 4
            ELSE period_order END,
          quarter = CASE reprt_code
            WHEN '11013' THEN 1
            WHEN '11012' THEN 2
            WHEN '11014' THEN 3
            WHEN '11011' THEN 4
            ELSE quarter END
        WHERE period_label IS NULL OR period_order IS NULL OR quarter IS NULL;
    """)
    conn.commit()




def init_tables(conn, drop_all=False):
    cur = conn.cursor()

    if drop_all:
        cur.executescript("""
        DROP TABLE IF EXISTS companies;
        DROP TABLE IF EXISTS reports;
        DROP TABLE IF EXISTS financials;
        DROP TABLE IF EXISTS shareholders;
        DROP TABLE IF EXISTS executives;
        DROP TABLE IF EXISTS subsidiaries;
        DROP TABLE IF EXISTS equity_changes;
        DROP TABLE IF EXISTS report_sections;
        DROP TABLE IF EXISTS report_attachments;
        DROP TABLE IF EXISTS report_tables;
        """)

    cur.executescript(DDL)
    conn.commit()

    cur.executescript(INDEXES)
    conn.commit()
    _ensure_financials_period_columns(conn)
    cur.executescript(VIEWS_FIN_CFS_BASE)
    conn.commit()

    cur.executescript(VIEWS_FIN_CFS_PERIOD_MATRIX)
    conn.commit()

def get_conn(db_path: str | None = None, row_factory: bool = False):
    """SQLite 커넥션 생성 헬퍼. 기본 경로는 config.DB_PATH 사용."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    # 외래키 제약 활성화 (필요 시)
    conn.execute("PRAGMA foreign_keys = ON;")
    if row_factory:
        conn.row_factory = sqlite3.Row
    return conn
