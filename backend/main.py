from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import ai_agent

app = FastAPI(title="MCP Backend")

# CORS 허용 (개발용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 개발중이니까 일단 전체 허용
    allow_credentials=True,
