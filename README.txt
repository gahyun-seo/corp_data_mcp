📁 MCP_DB 프로젝트 구조 안내
─────────────────────────────────────────────
DART 보고서 데이터를 자동으로 수집하고,
본문 및 첨부 HTML에서 '요약연결재무정보' 표를 추출하여
데이터베이스(SQLite)에 저장하는 파이프라인

- 테스트용 구조에 대해서만 아래에 적어놨습니다!
- 나머지 파일들은 main.py 용 / 이후 수정 예정
- 필요하면 extensions 다운받아주세요 (sqlite 뷰 필요함)

─────────────────────────────────────────────
1️⃣ 최상위 구조 (저장파일/mcp_db/)
─────────────────────────────────────────────
mcp_db/
│
├── __init__.py
├── config.py                 # DART API 키, DB 경로 등 환경설정
├── database.py               # DB 테이블/뷰 생성 및 초기화 로직
├── test.py                   # 테스트 전용 실행 스크립트 (삼성전자/하이닉스)
│
├── collectors/               # DART API 데이터 수집 모듈
│   ├── __init__.py
│   ├── company.py            # 기업 기본정보 수집
│   ├── financials.py         # 재무 데이터 수집 (CFS/OFS)
│   └── reports/
│       ├── __init__.py
│       ├── listing.py        # 최근 보고서 메타/본문 저장
│       ├── attachments.py    # 첨부 파일 인덱싱 (첨부목록 수집)
│
├── extractors/               # 보고서 본문/첨부 HTML 파싱
│   ├── __init__.py
│   ├── summary_fin.py        # [요약연결재무정보] 표 추출 및 DB 저장
│
├── utils/                    # 공통 유틸리티
│   ├── __init__.py
│   ├── logging_utils.py      # 로그 생성 함수 (get_logger)
│   └── conversions.py        # 연도 계산, 문자열 변환 등 헬퍼
│
├── tickers_test.csv          # 테스트용 티커 (삼성전자, SK하이닉스)
└── mcp_agent_test.db         # 테스트용 SQLite DB (자동 생성됨)

─────────────────────────────────────────────
2️⃣ 주요 파일 설명
─────────────────────────────────────────────
📌 config.py
- DART API 객체(dart) 및 DB 경로(DB_PATH) 설정.

📌 database.py
- 모든 테이블, 인덱스, 뷰 정의 포함.
- 실행 시 financials, reports, summary_fin_raw 등 테이블 자동 생성.

📌 collectors/reports/listing.py
- DART에서 사업/반기/분기보고서 목록 조회 후
  reports 테이블에 메타정보 저장.

📌 collectors/reports/attachments.py
- 보고서 첨부파일 목록 조회 (파일명 + URL)
  → report_attachments 테이블에 저장.

📌 collectors/financials.py
- 유동자산, 자본총계, 매출액 등 재무항목 저장 (financials 테이블).

📌 extractors/summary_fin.py
- 보고서 HTML을 BeautifulSoup으로 파싱하여
  "재무에 관한 사항 → 요약재무정보 → 가. 요약연결재무정보"
  섹션의 표를 찾아 summary_fin_raw 테이블에 저장.

📌 test.py
- 테스트 전용 실행 스크립트.
- 전체 수집 파이프라인 실행:
  기업기본정보 → 보고서메타 → 첨부 → 재무 → 요약재무정보 표 추출.
- 실행 명령어:
  python -m mcp_db.test

─────────────────────────────────────────────
3️⃣ 실행 흐름 (요약)
─────────────────────────────────────────────
test.py
  ├─ load_tickers_test()
  ├─ save_company()
  ├─ fetch_and_save_recent()         → reports
  ├─ index_attachments_for_stock()   → report_attachments
  ├─ save_financials()               → financials
  └─ extract_summary_consolidated()  → summary_fin_raw

─────────────────────────────────────────────
4️⃣ 협업자가 이어서 할 작업
─────────────────────────────────────────────
- 현재는 본문에서만 표 추출 성공 (삼성전자형 보고서).
- SK하이닉스처럼 첨부파일 내 표가 있는 경우를 위해:
  → summary_fin.py에서 “본문 실패 시 첨부 HTML fallback” 로직 구현.
- report_attachments 테이블의 URL을 활용하여
  “미리보기 HTML” 파일에서 동일한 방식으로 표 탐색.

─────────────────────────────────────────────
5️⃣ 기타
─────────────────────────────────────────────
- DB: SQLite 사용, 경로는 config.DB_PATH 참조.
- 로그: utils/logging_utils.get_logger 사용.
- requirements: pandas, bs4, lxml 필요.
─────────────────────────────────────────────