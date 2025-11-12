import os
from pathlib import Path
from dotenv import load_dotenv
import OpenDartReader

load_dotenv()

API_KEY = os.getenv("DART_API_KEY")
PACKAGE_ROOT = Path(__file__).resolve().parent
DB_PATH = str(PACKAGE_ROOT / "mcp_agent.db")

if not API_KEY:
    raise RuntimeError("DART_API_KEY not found in .env")

# 전역 DART 인스턴스
dart = OpenDartReader(API_KEY)

# 보고서 코드
REPRTS = [("11011","사업"),("11012","반기"),("11013","1Q"),("11014","3Q")]

# 최대주주(현황) 섹션명 후보
SH_SECTION_ALIASES = ["최대주주", "최대주주등", "최대주주 등의 현황", "최대주주등의 소유상황"]
