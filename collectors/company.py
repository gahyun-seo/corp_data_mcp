import csv

from ..config import dart, PACKAGE_ROOT
from ..utils.logging_utils import get_logger

log = get_logger("company")

_SECTOR_LOOKUP = None

def _load_sector_lookup():
    global _SECTOR_LOOKUP
    if _SECTOR_LOOKUP is not None:
        return _SECTOR_LOOKUP
    mapping = {}
    csv_path = PACKAGE_ROOT / "kospi200_codes.csv"
    if csv_path.exists():
        try:
            with csv_path.open("r", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    code = (row.get("stock_code") or "").strip()
                    if not code:
                        continue
                    mapping[code.zfill(6)] = row.get("sector") or row.get("industry")
        except Exception as exc:
            log.warning(f"Sector CSV load failed: {exc}")
    _SECTOR_LOOKUP = mapping
    return mapping

def fetch_and_save(conn, stock_code, corp_name):
    cur = conn.cursor()
    try:
        info = dart.company(stock_code)
        if info and isinstance(info, dict):
            ceo_nm       = info.get("ceo_nm","")
            sector_code  = info.get("induty_code") or info.get("bz_md_code")
            if sector_code:
                sector_code = str(sector_code).strip()
            sector_name  = (
                info.get("induty_nm")
                or info.get("industry")
                or info.get("sector_nm")
                or info.get("sector")
            )
            if not sector_name:
                sector_name = _load_sector_lookup().get(stock_code)
            address      = info.get("adres","") or info.get("address","")
            homepage     = info.get("hm_url","") or info.get("homepage","")
            listing_date = info.get("est_dt","") or info.get("listed_dt","")
            registration_no = info.get("bizr_no","") or info.get("jurir_no","")

            cur.execute("""
                INSERT OR REPLACE INTO companies
                (stock_code, corp_name, ceo_nm, sector_code, sector, address, homepage, listing_date, registration_no)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (stock_code, corp_name, ceo_nm, sector_code, sector_name, address, homepage, listing_date, registration_no))
            conn.commit()
            log.info(f"Company saved: {stock_code} {corp_name}")
            return True
        else:
            log.warning(f"Company info empty: {stock_code}")
            return False
    except Exception as e:
        log.error(f"Company error {stock_code}: {e}")
        return False
