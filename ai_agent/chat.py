from __future__ import annotations
import json
import requests
from typing import List, Dict, Optional

# Oollama LLM 챗 인터페이스
# 너무 오래 걸려서 미사용 중

DEFAULT_OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "llama3.1:8b"   # 설치된 다른 모델명으로 바꿔도 됨

class OllamaChat:
    def __init__(self, base_url: str = DEFAULT_OLLAMA_URL, model: str = DEFAULT_MODEL):
        self.base_url = base_url
        self.model = model

    def ask(self, system: str, user: str, context: str, temperature: float = 0.2) -> str:
        """RAG 컨텍스트를 system에 붙여서 응답 생성"""
        messages = [
            {"role": "system", "content": f"{system}\n\n[CONTEXT]\n{context}"},
            {"role": "user", "content": user}
        ]
        payload = {
            "model": self.model,
            "messages": messages,
            "options": {"temperature": temperature},
            "stream": False
        }
        try:
            r = requests.post(self.base_url, json=payload, timeout=120)
            r.raise_for_status()
            data = r.json()
            # ollama chat api: {"message":{"role":"assistant","content":"..."}}
            msg = data.get("message", {}).get("content")
            if msg:
                return msg
            return json.dumps(data, ensure_ascii=False)
        except requests.exceptions.ConnectionError:
            return ("[오류] Ollama 서버에 연결할 수 없습니다. "
                    "터미널에서 `ollama serve &` 실행 후 "
                    f"`ollama run {self.model}` 로 모델 설치/테스트 해보세요.")
        except Exception as e:
            return f"[오류] LLM 호출 실패: {e}"