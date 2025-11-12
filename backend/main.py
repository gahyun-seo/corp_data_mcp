from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import ai_agent
from .routers import finance

app = FastAPI(title="MCP Backend")

# CORS 허용 (개발용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 개발중이니까 일단 전체 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 다른 기능들 라우터도 추가 가능
app.include_router(ai_agent.router)
app.include_router(finance.router)
# app.include_router(users.router)
# app.include_router(data.router)

@app.get("/")
def root():
    return {"msg": "Backend running"}