# mcp_db/ai_agent/rag.py
from __future__ import annotations
from typing import List, Optional
from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# sentence-transformers 있는지 확인
try:
    from sentence_transformers import SentenceTransformer
    _HAS_ST = True
except Exception:
    _HAS_ST = False

from .loaders import Doc

@dataclass
class Chunk:
    doc_id: int
    stock_code: str
    title: str
    text: str

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """긴 텍스트를 겹치게 잘라서 리스트로 리턴"""
    if not text:
        return []
    chunks = []
    i = 0
    n = len(text)
    while i < n:
        j = min(n, i + chunk_size)
        chunks.append(text[i:j])
        if j == n:
            break
        # 겹치게 전진
        i = max(j - overlap, i + 1)
    return chunks

class SimpleRAG:
    """
    - docs: DB/HTML에서 가져온 문서들
    - mode: "tfidf" | "semantic" | "hybrid"
    """
    def __init__(self, docs: List[Doc], chunk_size: int = 1000, overlap: int = 200, mode: str = "semantic"):
        self.mode = mode
        self.docs = docs

        # 1) 문서 → 청크
        self.chunks: List[Chunk] = []
        for idx, d in enumerate(docs):
            for c in chunk_text(d.text, chunk_size=chunk_size, overlap=overlap):
                self.chunks.append(Chunk(idx, d.stock_code, d.title, c))
        print(f"[DEBUG] RAG: 총 {len(self.chunks)}개 chunk 생성됨")

        # 2) TF-IDF 인덱스
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.tfidf_matrix = None
        if self.chunks and mode in ("tfidf", "hybrid"):
            self._build_tfidf_index()

        # 3) semantic 인덱스
        self.semantic_model: Optional[SentenceTransformer] = None
        self.semantic_matrix = None
        if self.chunks and mode in ("semantic", "hybrid") and _HAS_ST:
            self._build_semantic_index()

        # run.py 옛 코드 호환용
        self.matrix = self.tfidf_matrix

    # ─────────────────────────────────────
    # 인덱스 만들기
    # ─────────────────────────────────────
    def _build_tfidf_index(self):
        self.vectorizer = TfidfVectorizer(max_features=50000)
        corpus = [c.text for c in self.chunks]
        self.tfidf_matrix = self.vectorizer.fit_transform(corpus)
        print("[DEBUG] RAG: TF-IDF 인덱스 생성 완료")

    def _build_semantic_index(self):
        print("[DEBUG] RAG: sentence-transformers 사용 가능 → semantic 인덱스 생성 중")
        self.semantic_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        corpus = [c.text for c in self.chunks]
        emb = self.semantic_model.encode(corpus, batch_size=64, show_progress_bar=False)
        self.semantic_matrix = emb  # (n_chunks, dim)
        print("[DEBUG] RAG: semantic 인덱스 생성 완료")

    # ─────────────────────────────────────
    # 개별 검색기
    # ─────────────────────────────────────
    def _retrieve_tfidf(self, query: str, top_k: int = 10) -> List[int]:
        if self.tfidf_matrix is None or self.vectorizer is None:
            return []
        qv = self.vectorizer.transform([query])
        sims = cosine_similarity(qv, self.tfidf_matrix)[0]
        idxs = np.argsort(-sims)[:top_k]
        return idxs.tolist()

    def _retrieve_semantic(self, query: str, top_k: int = 10) -> List[int]:
        if self.semantic_model is None or self.semantic_matrix is None:
            return []
        q_emb = self.semantic_model.encode([query])[0]  # (dim,)
        sims = np.dot(self.semantic_matrix, q_emb) / (
            np.linalg.norm(self.semantic_matrix, axis=1) * np.linalg.norm(q_emb) + 1e-9
        )
        idxs = np.argsort(-sims)[:top_k]
        return idxs.tolist()

    # ─────────────────────────────────────
    # 실제로 run.py에서 호출하는 함수
    # ─────────────────────────────────────
    def retrieve(
        self,
        query: str,
        top_k: int = 6,
        allowed_stocks: Optional[list[str]] = None,
        debug: bool = False,
        retriever: Optional[str] = "tfidf",   # None이면 self.mode 사용
    ) -> List[Chunk]:
        mode = retriever or self.mode  # run.py에서 안 넘기면 초기화 때 정한 모드
        # 1) 우선 후보 인덱스 뽑기
        if mode == "tfidf":
            idxs = self._retrieve_tfidf(query, top_k=top_k * 3)  # 조금 넉넉히
        elif mode == "semantic":
            idxs = self._retrieve_semantic(query, top_k=top_k * 3)
        else:  # hybrid
            tf_ids = self._retrieve_tfidf(query, top_k=top_k * 2)
            se_ids = self._retrieve_semantic(query, top_k=top_k * 2)
            merged = []
            seen = set()
            for i in tf_ids + se_ids:
                if i not in seen:
                    seen.add(i)
                    merged.append(i)
            idxs = merged

        # 2) 종목 필터링 + top_k로 자르기
        results: List[Chunk] = []
        for i in idxs:
            if i >= len(self.chunks):
                continue
            ch = self.chunks[i]
            if allowed_stocks and ch.stock_code not in allowed_stocks:
                continue
            results.append(ch)
            if len(results) >= top_k:
                break

        if debug:
            print(f"[DEBUG] retrieve(): 후보 {len(idxs)}개 중 {len(results)}개 반환 (mode={mode})")
            for c in results:
                print(f"   -> {c.stock_code} | {c.title[:50]}... | len={len(c.text)}")

        return results

    # ─────────────────────────────────────
    def format_context(self, chunks: List[Chunk]) -> str:
        out = []
        for i, c in enumerate(chunks, 1):
            out.append(f"[{i}] ({c.stock_code}) {c.title}\n{c.text}")
        return "\n\n".join(out)


# from __future__ import annotations
# from typing import List, Optional, Tuple
# from dataclasses import dataclass

# import numpy as np
# from sklearn.feature_extraction.text import TfidfVectorizer
# from sklearn.metrics.pairwise import cosine_similarity

# # sentence-transformers 있는지 확인
# try:
#     from sentence_transformers import SentenceTransformer
#     _HAS_ST = True
# except Exception:
#     _HAS_ST = False

# from .loaders import Doc

# import re

# @dataclass
# class Chunk:
#     doc_id: int
#     stock_code: str
#     title: str
#     section: str  # ← NEW (section info)
#     text: str

# def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
#     """긴 텍스트를 겹치게 잘라서 리스트로 리턴"""
#     if not text:
#         return []
#     chunks = []
#     i = 0
#     n = len(text)
#     while i < n:
#         j = min(n, i + chunk_size)
#         chunks.append(text[i:j])
#         if j == n:
#             break
#         i = max(j - overlap, i + 1)
#     return chunks

# def split_by_section(text: str) -> List[Tuple[str, str]]:
#     """
#     보고서에서 주요 섹션을 정규식으로 분리.
#     실제 섹션 패턴은 현업 리포트마다 다르니 필요하면 튜닝!
#     """
#     # 섹션 헤더 패턴 예: 'Ⅰ. 회사의 개요', '제1부 사업보고', etc.
#     pattern = r'((?:제\d+[\w ]+|[ⅠⅡⅢⅣⅤⅥ]\.? ?[\w ]+)[\n\r]+)'
#     splits = re.split(pattern, text)
#     out = []
#     section = ""
#     buf = ""
#     for part in splits:
#         if re.match(pattern, part):
#             if buf:
#                 out.append((section or "", buf.strip()))
#                 buf = ""
#             section = part.strip()
#         else:
#             buf += part
#     if buf:
#         out.append((section or "", buf.strip()))
#     return out if out else [("", text)]

# class SimpleRAG:
#     """
#     - docs: DB/HTML에서 가져온 문서들
#     - mode: "tfidf" | "semantic" | "hybrid"
#     """
#     def __init__(self, docs: List[Doc], chunk_size: int = 1000, overlap: int = 200, mode: str = "semantic"):
#         self.mode = mode
#         self.docs = docs

#         # 1) 문서 → 청크 (섹션별 split & chunk)
#         self.chunks: List[Chunk] = []
#         for idx, d in enumerate(docs):
#             sections = split_by_section(d.text)
#             for sec_title, sec_text in sections:
#                 for c in chunk_text(sec_text, chunk_size=chunk_size, overlap=overlap):
#                     self.chunks.append(
#                         Chunk(idx, d.stock_code, d.title, sec_title, c)
#                     )
#         print(f"[DEBUG] RAG: 총 {len(self.chunks)}개 chunk 생성됨")

#         self.vectorizer: Optional[TfidfVectorizer] = None
#         self.tfidf_matrix = None
#         if self.chunks and mode in ("tfidf", "hybrid"):
#             self._build_tfidf_index()

#         self.semantic_model: Optional[SentenceTransformer] = None
#         self.semantic_matrix = None
#         if self.chunks and mode in ("semantic", "hybrid") and _HAS_ST:
#             self._build_semantic_index()

#         self.matrix = self.tfidf_matrix

#     def _build_tfidf_index(self):
#         self.vectorizer = TfidfVectorizer(max_features=50000)
#         corpus = [c.text for c in self.chunks]
#         self.tfidf_matrix = self.vectorizer.fit_transform(corpus)
#         print("[DEBUG] RAG: TF-IDF 인덱스 생성 완료")

#     def _build_semantic_index(self):
#         print("[DEBUG] RAG: sentence-transformers 사용 가능 → semantic 인덱스 생성 중")
#         self.semantic_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
#         corpus = [c.text for c in self.chunks]
#         emb = self.semantic_model.encode(corpus, batch_size=64, show_progress_bar=False)
#         self.semantic_matrix = emb  # (n_chunks, dim)
#         print("[DEBUG] RAG: semantic 인덱스 생성 완료")

#     def _retrieve_tfidf(self, query: str, top_k: int = 10) -> List[int]:
#         if self.tfidf_matrix is None or self.vectorizer is None:
#             return []
#         qv = self.vectorizer.transform([query])
#         sims = cosine_similarity(qv, self.tfidf_matrix)[0]
#         idxs = np.argsort(-sims)[:top_k]
#         return idxs.tolist()

#     def _retrieve_semantic(self, query: str, top_k: int = 10) -> List[int]:
#         if self.semantic_model is None or self.semantic_matrix is None:
#             return []
#         q_emb = self.semantic_model.encode([query])[0]  # (dim,)
#         sims = np.dot(self.semantic_matrix, q_emb) / (
#             np.linalg.norm(self.semantic_matrix, axis=1) * np.linalg.norm(q_emb) + 1e-9
#         )
#         idxs = np.argsort(-sims)[:top_k]
#         return idxs.tolist()

#     def retrieve(
#         self,
#         query: str,
#         top_k: int = 6,
#         allowed_stocks: Optional[list[str]] = None,
#         allowed_sections: Optional[list[str]] = None,  # ← 추가!
#         debug: bool = False,
#         retriever: Optional[str] = "tfidf",
#     ) -> List[Chunk]:
#         mode = retriever or self.mode  # run.py에서 안 넘기면 초기화 때 정한 모드
#         if mode == "tfidf":
#             idxs = self._retrieve_tfidf(query, top_k=top_k * 3)
#         elif mode == "semantic":
#             idxs = self._retrieve_semantic(query, top_k=top_k * 3)
#         else:
#             tf_ids = self._retrieve_tfidf(query, top_k=top_k * 2)
#             se_ids = self._retrieve_semantic(query, top_k=top_k * 2)
#             merged = []
#             seen = set()
#             for i in tf_ids + se_ids:
#                 if i not in seen:
#                     seen.add(i)
#                     merged.append(i)
#             idxs = merged

#         results: List[Chunk] = []
#         for i in idxs:
#             if i >= len(self.chunks):
#                 continue
#             ch = self.chunks[i]
#             if allowed_stocks and ch.stock_code not in allowed_stocks:
#                 continue
#             if allowed_sections:
#                 lower_section = (ch.section or "").lower()
#                 if not any(sec.lower() in lower_section for sec in allowed_sections):
#                     continue
#             results.append(ch)
#             if len(results) >= top_k:
#                 break

#         if debug:
#             print(f"[DEBUG] retrieve(): 후보 {len(idxs)}개 중 {len(results)}개 반환 (mode={mode})")
#             for c in results:
#                 print(f"   -> {c.stock_code} | {c.title[:50]}... | section={c.section[:16]} | len={len(c.text)}")
#         return results

#     def format_context(self, chunks: List[Chunk]) -> str:
#         out = []
#         for i, c in enumerate(chunks, 1):
#             out.append(
#                 f"[{i}] ({c.stock_code}) {c.title} - {c.section}\n{c.text[:700]} ...\n(출처: {c.title}, {c.section})"
#             )
#         return "\n\n".join(out)