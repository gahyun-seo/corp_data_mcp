from __future__ import annotations
import re
from io import StringIO
from typing import List, Dict, Optional

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

def jsonable(v):
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, (pd.Timestamp, )):
        return v.isoformat()
    return v

SEC_HDR = re.compile(r'^(?:[Ⅰ-Ⅻ]+\.\s|제?\d+장|제?\d+절|^\d+\.\s)')

def extract_sections_from_html(html: str) -> List[Dict[str, Optional[str]]]:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    out: List[Dict[str, Optional[str]]] = []

    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        title = tag.get_text(strip=True)
        if title:
            anchor = tag.get("id") or tag.get("name")
            out.append({"section_title": title, "section_url": f"#{anchor}" if anchor else None})

    for p in soup.find_all(["p", "div", "span"]):
        txt = p.get_text(strip=True)
        if txt and SEC_HDR.search(txt):
            out.append({"section_title": txt, "section_url": None})

    seen, uniq = set(), []
    for s in out:
        t = s["section_title"]
        if t not in seen:
            seen.add(t)
            uniq.append(s)
    return uniq

def iter_html_tables(html: str):
    try:
        for df in pd.read_html(StringIO(html), flavor="bs4"):
            yield df
        return
    except Exception:
        pass
    try:
        for df in pd.read_html(StringIO(html)):
            yield df
    except Exception:
        return