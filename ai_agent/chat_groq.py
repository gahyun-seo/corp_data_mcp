# mcp_db/ai_agent/chat_groq.py
from __future__ import annotations
import os
import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
# 빠른 응답: "llama-3.1-8b-instant"
# 대형, 코품질: "llama-3.3-70b-versatile"
# GPT-3.5~4.0 급: "openai/gpt-oss-20b"
# 구글 기반 모델: "gemma-7b-it"

class GroqChat:
    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY가 없습니다. .env에 넣어주세요.")

    def ask(
        self,
        system: str,
        user: str,
        context: str,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> str:
        # 1차 방어선: context 너무 길면 잘라
        if len(context) > 4000:
            context = context[:4000]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = [
            {
                "role": "system",
                "content": (
                    f"{system}\n\n"
                    "아래 CONTEXT에서 근거를 찾아. 네가 질문에 맞게 정제해서 답해. 혹시라도 없으면 '자료에 없음'이라고 말한 후 스스로 생각해서 답해.\n"
                    "숫자는 보고서 형식 그대로 써."
                    "\n[CONTEXT]\n" + context
                ),
            },
            {"role": "user", "content": user},
        ]
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.HTTPError:
            try:
                err_detail = resp.json()
            except Exception:
                err_detail = resp.text
            return f"[오류] Groq API 오류 ({resp.status_code