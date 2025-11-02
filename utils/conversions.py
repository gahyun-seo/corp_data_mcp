import pandas as pd
import numpy as np
from datetime import datetime

def to_num(x):
    if pd.isna(x):
        return None
    if isinstance(x, (int, float, np.number)):
        return float(x)
    s = str(x).strip()
    if s in ("", "-", "--"):
        return None
    try:
        return float(s.replace(",", ""))
    except Exception:
        return None

def coalesce_col(df, candidates, default=None):
    for c in candidates:
        if c in df.columns:
            return df[c]
    return pd.Series([default]*len(df))

def get_latest_business_year():
    return datetime.now().year - 1

def safe_has_cols(df, cols):
    return isinstance(df, pd.DataFrame) and not df.empty and all(c in df.columns for c in cols)

def is_excel_like(name: str) -> bool:
    if not name:
        return False
    name = name.lower()
    return name.endswith(".xlsx") or name.endswith(".xls") or name.endswith(".csv")
