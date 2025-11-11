"""
주식 데이터 수집 서비스
- 우선순위: pykrx → pandas_datareader → yfinance
"""
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class StockData:
    """주식 데이터 모델"""
    stock_code: str          # 종목코드
    stock_name: str          # 종목명
    date: str                # 거래일
    
    # 가격 정보
    open_price: int          # 시가
    high_price: int          # 고가
    low_price: int           # 저가
    close_price: int         # 종가
    
    # 변동 정보
    change_price: int        # 전일대비
    change_rate: float       # 등락률 (%)
    
    # 거래 정보
    volume: int              # 거래량
    trading_value: int       # 거래대금
    
    # 시장 정보
    market_cap: int          # 시가총액
    listed_shares: int       # 상장주식수
    
    # 추가 정보 (있으면)
    per: Optional[float] = None      # PER
    pbr: Optional[float] = None      # PBR
    eps: Optional[int] = None        # EPS
    bps: Optional[int] = None        # BPS
    div_yield: Optional[float] = None  # 배당수익률


class StockDataFetcher:
    """주식 데이터 가져오기 (여러 소스 지원)"""
    
    def __init__(self):
        self._cache = {}  # {(종목코드, 날짜): 데이터}
        self._stock_info_cache = {}  # 종목명 캐시
    
    def _get_stock_name(self, stock_code: str) -> str:
        """종목명 조회"""
        if stock_code in self._stock_info_cache:
            return self._stock_info_cache[stock_code]
        
        try:
            from pykrx import stock
            name = stock.get_market_ticker_name(stock_code)
            self._stock_info_cache[stock_code] = name
            return name
        except Exception as e:
            logger.warning(f"종목명 조회 실패 ({stock_code}): {e}")
            return stock_code
    
    def _fetch_from_pykrx(
        self, 
        stock_code: str, 
        start_date: str, 
        end_date: str
    ) -> Optional[pd.DataFrame]:
        """
        pykrx로 데이터 가져오기
        
        Args:
            stock_code: 종목코드 (예: "005930")
            start_date: 시작일 (YYYYMMDD)
            end_date: 종료일 (YYYYMMDD)
        
        Returns:
            DataFrame 또는 None
        """
        try:
            from pykrx import stock
            
            logger.info(f"pykrx로 {stock_code} 데이터 조회 중...")
            
            # 일별 시세 조회
            df = stock.get_market_ohlcv_by_date(
                start_date, 
                end_date, 
                stock_code
            )
            
            if df.empty:
                return None
            
            # 컬럼명 변경
            df = df.rename(columns={
                '시가': 'open',
                '고가': 'high',
                '저가': 'low',
                '종가': 'close',
                '거래량': 'volume',
                '거래대금': 'trading_value',
                '등락률': 'change_rate'
            })
            
            # 기본 정보 추가
            df['stock_code'] = stock_code
            df['stock_name'] = self._get_stock_name(stock_code)
            
            # 전일대비 계산
            df['change'] = df['close'].diff()
            
            try:
                # 시가총액 정보 가져오기
                cap_df = stock.get_market_cap_by_date(
                    start_date,
                    end_date,
                    stock_code
                )
                
                if not cap_df.empty:
                    cap_df = cap_df.rename(columns={
                        '시가총액': 'market_cap',
                        '거래량': 'volume_cap',
                        '거래대금': 'trading_value_cap',
                        '상장주식수': 'listed_shares'
                    })
                    
                    # 시가총액 정보 병합
                    df = df.join(cap_df[['market_cap', 'listed_shares']], how='left')
            except Exception as e:
                logger.warning(f"시가총액 정보 조회 실패: {e}")
                df['market_cap'] = 0
                df['listed_shares'] = 0
            
            try:
                # 투자지표 가져오기 (PER, PBR, EPS, BPS, DIV)
                fundamental_df = stock.get_market_fundamental_by_date(
                    start_date,
                    end_date,
                    stock_code
                )
                
                if not fundamental_df.empty:
                    fundamental_df = fundamental_df.rename(columns={
                        'PER': 'per',
                        'PBR': 'pbr',
                        'EPS': 'eps',
                        'BPS': 'bps',
                        'DIV': 'div_yield'
                    })
                    
                    # 투자지표 병합
                    df = df.join(fundamental_df[['per', 'pbr', 'eps', 'bps', 'div_yield']], how='left')
            except Exception as e:
                logger.warning(f"투자지표 조회 실패: {e}")
            
            logger.info(f"✅ pykrx 성공: {len(df)}일치 데이터")
            return df
            
        except ImportError:
            logger.error("pykrx가 설치되지 않았습니다: pip install pykrx")
            return None
        except Exception as e:
            logger.warning(f"pykrx 조회 실패: {e}")
            return None
    
    def _fetch_from_datareader(
        self, 
        stock_code: str, 
        start_date: str, 
        end_date: str
    ) -> Optional[pd.DataFrame]:
        """
        pandas_datareader로 데이터 가져오기 (백업)
        
        Args:
            stock_code: 종목코드 (예: "005930.KS")
            start_date: 시작일
            end_date: 종료일
        
        Returns:
            DataFrame 또는 None
        """
        try:
            import pandas_datareader.data as web
            
            logger.info(f"pandas_datareader로 {stock_code} 데이터 조회 중...")
            
            # Yahoo Finance 형식으로 변환 (005930 → 005930.KS)
            ticker = f"{stock_code}.KS" if not stock_code.endswith('.KS') else stock_code
            
            # 날짜 형식 변환 (YYYYMMDD → datetime)
            start_dt = pd.to_datetime(start_date, format='%Y%m%d')
            end_dt = pd.to_datetime(end_date, format='%Y%m%d')
            
            df = web.DataReader(ticker, 'yahoo', start_dt, end_dt)
            
            if df.empty:
                return None
            
            # 컬럼명 통일
            df = df.rename(columns={
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume',
                'Adj Close': 'adj_close'
            })
            
            df['stock_code'] = stock_code
            df['stock_name'] = self._get_stock_name(stock_code)
            df['change'] = df['close'].diff()
            df['change_rate'] = df['close'].pct_change() * 100
            
            logger.info(f"✅ pandas_datareader 성공: {len(df)}일치 데이터")
            return df
            
        except ImportError:
            logger.warning("pandas_datareader가 설치되지 않았습니다: pip install pandas-datareader")
            return None
        except Exception as e:
            logger.warning(f"pandas_datareader 조회 실패: {e}")
            return None
    
    def _fetch_from_yfinance(
        self, 
        stock_code: str, 
        start_date: str, 
        end_date: str
    ) -> Optional[pd.DataFrame]:
        """
        yfinance로 데이터 가져오기 (최종 백업)
        
        Args:
            stock_code: 종목코드
            start_date: 시작일
            end_date: 종료일
        
        Returns:
            DataFrame 또는 None
        """
        try:
            import yfinance as yf
            
            logger.info(f"yfinance로 {stock_code} 데이터 조회 중...")
            
            # Yahoo Finance 형식으로 변환
            ticker = f"{stock_code}.KS" if not stock_code.endswith('.KS') else stock_code
            
            # 날짜 형식 변환
            start_dt = pd.to_datetime(start_date, format='%Y%m%d')
            end_dt = pd.to_datetime(end_date, format='%Y%m%d')
            
            stock = yf.Ticker(ticker)
            df = stock.history(start=start_dt, end=end_dt)
            
            if df.empty:
                return None
            
            # 컬럼명 통일
            df = df.rename(columns={
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            })
            
            df['stock_code'] = stock_code
            df['stock_name'] = self._get_stock_name(stock_code)
            df['change'] = df['close'].diff()
            df['change_rate'] = df['close'].pct_change() * 100
            
            logger.info(f"✅ yfinance 성공: {len(df)}일치 데이터")
            return df
            
        except ImportError:
            logger.warning("yfinance가 설치되지 않았습니다: pip install yfinance")
            return None
        except Exception as e:
            logger.warning(f"yfinance 조회 실패: {e}")
            return None
    
    def get_stock_data(
        self, 
        stock_code: str, 
        start_date: str = None, 
        end_date: str = None,
        days: int = 30
    ) -> pd.DataFrame:
        """
        주식 데이터 조회 (여러 소스 시도)
        
        Args:
            stock_code: 종목코드 (예: "005930")
            start_date: 시작일 (YYYYMMDD, 선택)
            end_date: 종료일 (YYYYMMDD, 선택)
            days: 조회 일수 (start_date 없을 때)
        
        Returns:
            DataFrame (실패 시 빈 DataFrame)
        """
        # 날짜 설정
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        
        if start_date is None:
            start_dt = datetime.now() - timedelta(days=days * 2)  # 주말 고려
            start_date = start_dt.strftime("%Y%m%d")
        
        logger.info(f"📊 {stock_code} 데이터 조회: {start_date} ~ {end_date}")
        
        # 1. pykrx 시도
        df = self._fetch_from_pykrx(stock_code, start_date, end_date)
        if df is not None and not df.empty:
            return df
        
        # 2. pandas_datareader 시도
        logger.info("pykrx 실패, pandas_datareader 시도...")
        df = self._fetch_from_datareader(stock_code, start_date, end_date)
        if df is not None and not df.empty:
            return df
        
        # 3. yfinance 시도
        logger.info("pandas_datareader 실패, yfinance 시도...")
        df = self._fetch_from_yfinance(stock_code, start_date, end_date)
        if df is not None and not df.empty:
            return df
        
        # 모두 실패
        logger.error(f"❌ 모든 데이터 소스에서 {stock_code} 조회 실패")
        return pd.DataFrame()
    
    def get_latest_data(self, stock_code: str) -> Optional[StockData]:
        """
        특정 종목의 최신 데이터 조회
        
        Args:
            stock_code: 종목코드
        
        Returns:
            StockData 객체 또는 None
        """
        df = self.get_stock_data(stock_code, days=5)
        
        if df.empty:
            return None
        
        # 가장 최근 데이터
        latest = df.iloc[-1]
        
        return StockData(
            stock_code=stock_code,
            stock_name=str(latest.get('stock_name', stock_code)),
            date=latest.name.strftime('%Y%m%d') if hasattr(latest.name, 'strftime') else '',
            open_price=int(latest.get('open', 0)),
            high_price=int(latest.get('high', 0)),
            low_price=int(latest.get('low', 0)),
            close_price=int(latest.get('close', 0)),
            change_price=int(latest.get('change', 0)),
            change_rate=float(latest.get('change_rate', 0)),
            volume=int(latest.get('volume', 0)),
            trading_value=int(latest.get('trading_value', 0)),
            market_cap=int(latest.get('market_cap', 0)),
            listed_shares=int(latest.get('listed_shares', 0)),
            per=float(latest.get('per', 0)) if pd.notna(latest.get('per')) else None,
            pbr=float(latest.get('pbr', 0)) if pd.notna(latest.get('pbr')) else None,
            eps=int(latest.get('eps', 0)) if pd.notna(latest.get('eps')) else None,
            bps=int(latest.get('bps', 0)) if pd.notna(latest.get('bps')) else None,
            div_yield=float(latest.get('div_yield', 0)) if pd.notna(latest.get('div_yield')) else None
        )
    
    def get_multiple_stocks_data(
        self, 
        stock_codes: List[str], 
        days: int = 30
    ) -> Dict[str, pd.DataFrame]:
        """
        여러 종목의 데이터 동시 조회
        
        Args:
            stock_codes: 종목코드 리스트
            days: 조회 일수
        
        Returns:
            {종목코드: DataFrame} 딕셔너리
        """
        result = {}
        
        for code in stock_codes:
            df = self.get_stock_data(code, days=days)
            if not df.empty:
                result[code] = df
            else:
                logger.warning(f"⚠ {code} 데이터 없음")
        
        return result


class StockService:
    """주식 데이터 서비스 (대시보드용)"""
    
    def __init__(self):
        self.fetcher = StockDataFetcher()
    
    def add_stock_to_dashboard(self, stock_code: str) -> Dict:
        """
        대시보드에 종목 추가
        
        Args:
            stock_code: 종목코드
        
        Returns:
            종목 정보 딕셔너리
        """
        # 최신 데이터
        latest = self.fetcher.get_latest_data(stock_code)
        
        if not latest:
            return {"error": f"종목 {stock_code}를 찾을 수 없습니다"}
        
        # 과거 30일 데이터
        history_df = self.fetcher.get_stock_data(stock_code, days=30)
        
        return {
            "stock_code": stock_code,
            "stock_name": latest.stock_name,
            "current_data": {
                "date": latest.date,
                "close_price": latest.close_price,
                "change_price": latest.change_price,
                "change_rate": latest.change_rate,
                "volume": latest.volume,
                "market_cap": latest.market_cap,
                "per": latest.per,
                "pbr": latest.pbr,
                "eps": latest.eps,
                "bps": latest.bps,
                "div_yield": latest.div_yield
            },
            "history_data": history_df.to_dict('records') if not history_df.empty else []
        }
    
    def get_portfolio_data(self, stock_codes: List[str], days: int = 252) -> Dict[str, pd.DataFrame]:
        """
        포트폴리오용 데이터 조회 (1년치)
        
        Args:
            stock_codes: 종목코드 리스트
            days: 조회 일수 (기본 252일 = 약 1년)
        
        Returns:
            {종목코드: DataFrame} 딕셔너리
        """
        return self.fetcher.get_multiple_stocks_data(stock_codes, days=days)


# 전역 인스턴스
stock_service = StockService()