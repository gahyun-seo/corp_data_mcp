# backend/stocks.py
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import httpx
import pandas as pd
from dotenv import load_dotenv
import asyncio

load_dotenv()

@dataclass
class StockData:
    """주식 데이터 모델"""
    stock_code: str
    stock_name: str
    current_price: float
    change: float
    change_rate: float
    open_price: float
    high_price: float
    low_price: float
    volume: int
    trading_value: int
    market_cap: int
    shares: int
    date: str

class KRXApiService:
    """KRX Open API 서비스"""
    
    def __init__(self):
        self.api_key = os.getenv("KRX_API_KEY")
        if not self.api_key:
            raise ValueError("KRX_API_KEY not found in .env file")
            
        self.base_url = "https://data-dbg.krx.co.kr/svc/apis"
        self.headers = {
            "AUTH_KEY": self.api_key,
            "Content-Type": "application/json"
        }
    
    async def get_daily_stock_data(self, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """특정 날짜의 전체 유가증권 일별매매정보 조회"""
        if not date:
            date = datetime.now().strftime("%Y%m%d")
        
        endpoint = f"{self.base_url}/sto/stk_bydd_trd"
        payload = {"basDd": date}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    endpoint,
                    headers=self.headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                return data.get("OutBlock_1", [])
            except Exception as e:
                print(f"Error fetching data for {date}: {e}")
                return []
    
    async def get_stock_by_code(
        self,
        stock_code: str,
        date: Optional[str] = None
    ) -> Optional[StockData]:
        """특정 종목코드의 주식 데이터 조회"""
        all_stocks = await self.get_daily_stock_data(date)
        
        for stock in all_stocks:
            if stock_code in stock.get("ISU_CD", ""):
                return self._parse_stock_data(stock)
        return None
    
    async def get_stock_history(
        self,
        stock_code: str,
        days: int = 365
    ) -> pd.DataFrame:
        """특정 종목의 1년치 데이터 조회"""
        end_date = datetime.now()
        results = []
        
        # 병렬 처리로 효율적인 데이터 수집
        tasks = []
        for i in range(days):
            date = (end_date - timedelta(days=i)).strftime("%Y%m%d")
            tasks.append(self.get_stock_by_code(stock_code, date))
            
            # 30개씩 묶어서 처리 (API 부하 관리)
            if len(tasks) >= 30 or i == days - 1:
                batch_results = await asyncio.gather(*tasks)
                results.extend([r for r in batch_results if r is not None])
                tasks = []
                await asyncio.sleep(0.5)  # API 제한 방지
        
        if results:
            df = pd.DataFrame([vars(r) for r in results])
            df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
            df.set_index('date', inplace=True)
            df.sort_index(inplace=True)
            return df
        
        return pd.DataFrame()
    
    async def get_multiple_stocks_current(
        self,
        stock_codes: List[str],
        date: Optional[str] = None
    ) -> Dict[str, StockData]:
        """여러 종목의 현재 데이터 조회"""
        all_stocks = await self.get_daily_stock_data(date)
        results = {}
        
        for stock in all_stocks:
            isu_cd = stock.get("ISU_CD", "")
            for code in stock_codes:
                if code in isu_cd:
                    parsed = self._parse_stock_data(stock)
                    if parsed:
                        results[code] = parsed
                    break
        
        return results
    
    async def get_multiple_stocks_history(
        self,
        stock_codes: List[str],
        days: int = 365
    ) -> Dict[str, pd.DataFrame]:
        """여러 종목의 1년치 데이터 동시 조회"""
        tasks = {}
        for code in stock_codes:
            tasks[code] = self.get_stock_history(code, days)
        
        results = await asyncio.gather(*tasks.values())
        return dict(zip(tasks.keys(), results))
    
    def _parse_stock_data(self, data: Dict) -> Optional[StockData]:
        """API 응답 데이터를 StockData 객체로 파싱"""
        try:
            def to_float(value):
                if value == "-" or value is None:
                    return 0.0
                return float(str(value).replace(",", ""))
            
            def to_int(value):
                if value == "-" or value is None:
                    return 0
                return int(str(value).replace(",", ""))
            
            isu_cd = data.get("ISU_CD", "")
            stock_code = isu_cd[3:9] if len(isu_cd) > 9 else ""
            
            return StockData(
                stock_code=stock_code,
                stock_name=data.get("ISU_NM", ""),
                current_price=to_float(data.get("TDD_CLSPRC", 0)),
                change=to_float(data.get("CMPPREVDD_PRC", 0)),
                change_rate=to_float(data.get("FLUC_RT", 0)),
                open_price=to_float(data.get("TDD_OPNPRC", 0)),
                high_price=to_float(data.get("TDD_HGPRC", 0)),
                low_price=to_float(data.get("TDD_LWPRC", 0)),
                volume=to_int(data.get("ACC_TRDVOL", 0)),
                trading_value=to_int(data.get("ACC_TRDVAL", 0)),
                market_cap=to_int(data.get("MKTCAP", 0)),
                shares=to_int(data.get("LIST_SHRS", 0)),
                date=data.get("BAS_DD", "")
            )
        except Exception as e:
            print(f"Error parsing stock data: {e}")
            return None

class StockService:
    """대시보드용 주식 데이터 서비스"""
    
    def __init__(self):
        self.krx_service = KRXApiService()
        self.cache = {}  # 간단한 메모리 캐시
        self.cache_duration = timedelta(minutes=5)
    
    async def add_stock_to_dashboard(
        self, 
        stock_code: str
    ) -> Dict[str, Any]:
        """대시보드에 주식 추가 - 1년치 데이터 반환"""
        
        # 캐시 확인
        cache_key = f"{stock_code}_{datetime.now().strftime('%Y%m%d')}"
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if datetime.now() - timestamp < self.cache_duration:
                return cached_data
        
        # 현재 데이터
        current_data = await self.krx_service.get_stock_by_code(stock_code)
        if not current_data:
            return {"error": f"Stock {stock_code} not found"}
        
        # 1년치 과거 데이터
        history_df = await self.krx_service.get_stock_history(stock_code, days=365)
        
        result = {
            "stock_code": stock_code,
            "stock_name": current_data.stock_name,
            "current_data": vars(current_data),
            "history_data": history_df.to_dict(orient='records') if not history_df.empty else [],
            "timestamp": datetime.now().isoformat()
        }
        
        # 캐시 저장
        self.cache[cache_key] = (result, datetime.now())
        
        return result
    
    async def add_multiple_stocks(
        self,
        stock_codes: List[str]
    ) -> List[Dict[str, Any]]:
        """여러 종목 동시 추가"""
        tasks = [self.add_stock_to_dashboard(code) for code in stock_codes]
        results = await asyncio.gather(*tasks)
        return results
    
    async def get_dashboard_stocks(
        self,
        stock_codes: List[str]
    ) -> Dict[str, Any]:
        """대시보드 전체 데이터 조회"""
        
        # 현재 데이터
        current_data = await self.krx_service.get_multiple_stocks_current(stock_codes)
        
        # 1년치 데이터 (필요시)
        history_data = await self.krx_service.get_multiple_stocks_history(stock_codes)
        
        results = {}
        for code in stock_codes:
            if code in current_data:
                results[code] = {
                    "current": vars(current_data[code]),
                    "history": history_data[code].to_dict(orient='records') if code in history_data and not history_data[code].empty else []
                }
        
        return {
            "stocks": results,
            "timestamp": datetime.now().isoformat()
        }

# FastAPI에서 사용할 서비스 인스턴스
stock_service = StockService()