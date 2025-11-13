"""
주식 대시보드 FastAPI 백엔드
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
import logging
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from .routers import ai_agent, finance
from .routers.stocks import stock_service
from .routers.portfolio import portfolio_optimizer


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI 앱 생성
app = FastAPI(
    title="Stock Dashboard API",
    description="주식 데이터 조회 및 포트폴리오 최적화 API",
    version="1.0.0"
)

# CORS 설정 (프론트엔드에서 접근 가능하도록)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 구체적인 도메인으로 변경
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ai_agent.router)
app.include_router(finance.router)


# ============================================================================
# Request/Response 모델
# ============================================================================

class StockAddRequest(BaseModel):
    """주식 추가 요청"""
    stock_codes: List[str]
    
    class Config:
        schema_extra = {
            "example": {
                "stock_codes": ["005930", "000660"]
            }
        }


class PortfolioOptimizeRequest(BaseModel):
    """포트폴리오 최적화 요청"""
    stock_codes: List[str]
    days: Optional[int] = 252  # 기본 1년
    
    class Config:
        schema_extra = {
            "example": {
                "stock_codes": ["005930", "000660", "005380"],
                "days": 252
            }
        }


# ============================================================================
# API 엔드포인트
# ============================================================================

@app.get("/")
def read_root():
    """API 루트"""
    return {
        "message": "Stock Dashboard API",
        "version": "1.0.0",
        "endpoints": {
            "docs": "/docs",
            "stock_info": "/api/stocks/{stock_code}",
            "portfolio_optimize": "/api/portfolio/optimize"
        }
    }
@app.get("/api/stocks/lookup")
def lookup_stocks(q: str, limit: int = 10):
    """
    종목명/코드 검색 (부분일치). 예: /api/stocks/lookup?q=삼성
    """
    try:
        items = stock_service.search_stocks(q, limit=limit)
        return JSONResponse(content=jsonable_encoder({"results": items}))
    except Exception as e:
        logger.error(f"lookup 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stocks/{stock_code}")
def get_stock_info(stock_code: str):
    """
    개별 종목 정보 조회
    
    Args:
        stock_code: 종목코드 (예: 005930)
    
    Returns:
        종목 정보 (현재가, 과거 데이터 등)
    """
    try:
        logger.info(f"종목 조회: {stock_code}")
        
        result = stock_service.add_stock_to_dashboard(stock_code)
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"종목 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/portfolio/optimize")
def optimize_portfolio(request: PortfolioOptimizeRequest):
    """
    포트폴리오 최적화 (샤프 비율 최대화)
    
    Args:
        request: 종목코드 리스트 및 조회 일수
    
    Returns:
        최적 자산배분 비율, 기대수익률, 변동성, 샤프 비율
    """
    try:
        stock_codes = request.stock_codes
        days = request.days
        
        logger.info(f"포트폴리오 최적화: {stock_codes}, {days}일")
        
        if not stock_codes:
            raise HTTPException(status_code=400, detail="종목코드가 필요합니다")
        
        if len(stock_codes) > 10:
            raise HTTPException(status_code=400, detail="최대 10개 종목까지 가능합니다")
        
        # 1. 주가 데이터 수집
        logger.info("주가 데이터 수집 중...")
        price_data = stock_service.get_portfolio_data(stock_codes, days=days)
        
        if not price_data:
            raise HTTPException(
                status_code=404, 
                detail="주가 데이터를 가져올 수 없습니다"
            )
        
        # 데이터가 없는 종목 체크
        missing = set(stock_codes) - set(price_data.keys())
        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"다음 종목의 데이터를 찾을 수 없습니다: {list(missing)}"
            )
        
        # 2. 포트폴리오 최적화
        logger.info("포트폴리오 최적화 실행 중...")
        result = portfolio_optimizer.optimize_portfolio(price_data)
        
        # 3. 결과 반환
        response = result.to_dict()
        
        # 퍼센트로 변환 (프론트엔드에서 사용하기 쉽게)
        response["weights_percent"] = [w * 100 for w in result.weights]
        response["expected_return_percent"] = result.expected_return * 100
        response["volatility_percent"] = result.volatility * 100
        
        logger.info(f"최적화 완료: 샤프비율 {result.sharpe_ratio:.4f}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"포트폴리오 최적화 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stocks/batch")
def get_multiple_stocks(request: StockAddRequest):
    """
    여러 종목 정보 일괄 조회
    
    Args:
        request: 종목코드 리스트
    
    Returns:
        각 종목의 정보 리스트
    """
    try:
        stock_codes = request.stock_codes
        
        logger.info(f"일괄 조회: {stock_codes}")
        
        results = []
        for code in stock_codes:
            result = stock_service.add_stock_to_dashboard(code)
            results.append(result)
        
        return {"stocks": results}
        
    except Exception as e:
        logger.error(f"일괄 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ticker-samples")
def ticker_samples(limit: int = 40):
    """
    KOSPI200 샘플 종목들에 대해
    - 종목명
    - 종가
    - 전일대비
    - 등락률
    - 기준일
    을 반환해서 finance_search 티커에 쓰기 위함
    """
    import pandas as pd
    from pathlib import Path
    import random

    csv_path = Path(__file__).resolve().parents[2] / "kospi200_codes.csv"
    if not csv_path.exists():
        raise HTTPException(status_code=500, detail=f"{csv_path} not found")

    df = pd.read_csv(csv_path, dtype=str)
    if df.empty:
        return {"items": []}

    # 너무 많으면 limit만큼 랜덤 샘플
    codes = df["stock_code"].tolist()
    random.shuffle(codes)
    codes = codes[:limit]

    items = []
    for code in codes:
        latest = stock_service.fetcher.get_latest_data(code)
        if not latest:
            continue
        items.append({
            "stock_code": latest.stock_code,
            "stock_name": latest.stock_name,
            "close_price": latest.close_price,
            "change_price": latest.change_price,
            "change_rate": latest.change_rate,
            "as_of": latest.date,  # "YYYYMMDD"
        })

    return {"items": items}


@app.get("/api/health")
def health_check():
    """헬스 체크"""
    return {
        "status": "healthy",
        "services": {
            "stocks": "ok",
            "portfolio": "ok"
        }
    }
    



# ============================================================================
# 서버 실행
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "="*70)
    print("🚀 Stock Dashboard API Server")
    print("="*70)
    print("서버 주소: http://localhost:8000")
    print("API 문서: http://localhost:8000/docs")
    print("="*70 + "\n")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        log_level="info"
    )