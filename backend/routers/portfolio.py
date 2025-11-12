"""
포트폴리오 최적화 모듈
- 샤프 비율 최대화를 통한 최적 자산배분 계산
"""
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd
from scipy.optimize import minimize
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PortfolioResult:
    """포트폴리오 최적화 결과"""
    stock_codes: List[str]
    stock_names: List[str]
    weights: List[float]  # 자산배분 비율 (합=1.0)
    expected_return: float  # 연 기대수익률
    volatility: float  # 연 변동성
    sharpe_ratio: float  # 샤프 비율
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return asdict(self)


class PortfolioOptimizer:
    """포트폴리오 최적화 엔진"""
    
    def __init__(self, risk_free_rate: float = 0.035):
        """
        Args:
            risk_free_rate: 무위험수익률 (기본값: 연 3.5%, 대한민국 국채 수익률 기준)
        """
        self.risk_free_rate = risk_free_rate
        logger.info(f"PortfolioOptimizer initialized with risk-free rate: {risk_free_rate:.2%}")
    
    def calculate_portfolio_stats(
        self,
        weights: np.ndarray,
        mean_returns: np.ndarray,
        cov_matrix: np.ndarray
    ) -> tuple:
        """
        포트폴리오 통계량 계산
        
        Args:
            weights: 자산별 비중
            mean_returns: 일별 평균 수익률
            cov_matrix: 일별 수익률 공분산 행렬
        
        Returns:
            (연 기대수익률, 연 변동성, 샤프비율)
        """
        # 포트폴리오 기대수익률 = 가중평균 (연환산: 252 거래일)
        portfolio_return = np.sum(weights * mean_returns) * 252
        
        # 포트폴리오 변동성 = √(w^T * Σ * w) (연환산)
        portfolio_variance = np.dot(weights.T, np.dot(cov_matrix * 252, weights))
        portfolio_std = np.sqrt(portfolio_variance)
        
        # 샤프 비율 = (포트폴리오 수익률 - 무위험 수익률) / 포트폴리오 변동성
        sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_std
        
        return portfolio_return, portfolio_std, sharpe_ratio
    
    def negative_sharpe(
        self,
        weights: np.ndarray,
        mean_returns: np.ndarray,
        cov_matrix: np.ndarray
    ) -> float:
        """
        최소화할 목적함수 (샤프비율의 음수)
        scipy.optimize.minimize는 최소화 함수이므로 음수를 반환
        """
        _, _, sharpe = self.calculate_portfolio_stats(weights, mean_returns, cov_matrix)
        return -sharpe
    
    def optimize_portfolio(
        self,
        price_data: Dict[str, pd.DataFrame]
    ) -> PortfolioResult:
        """
        샤프 비율을 최대화하는 포트폴리오 계산
        
        Args:
            price_data: {종목코드: DataFrame} 형태
                       각 DataFrame은 'current_price' 컬럼을 포함해야 함
                       date가 인덱스로 설정되어 있어야 함
        
        Returns:
            최적화된 포트폴리오 결과
        """
        stock_codes = list(price_data.keys())
        n_stocks = len(stock_codes)
        
        logger.info(f"포트폴리오 최적화 시작: {n_stocks}개 종목")
        logger.info(f"종목 코드: {stock_codes}")
        
        # 종목이 1개인 경우: 100% 배분
        if n_stocks == 1:
            code = stock_codes[0]
            df = price_data[code]
            stock_name = df.iloc[0].get('stock_name', code) if 'stock_name' in df.columns else code
            
            logger.info(f"단일 종목 포트폴리오: {stock_name} 100%")
            
            return PortfolioResult(
                stock_codes=[code],
                stock_names=[stock_name],
                weights=[1.0],
                expected_return=0.0,  # 단일 종목은 통계 계산 불필요
                volatility=0.0,
                sharpe_ratio=0.0
            )
        
        # 1. 일별 수익률 계산
        returns_df = pd.DataFrame()
        stock_names = {}
        
        for code, df in price_data.items():
            # 컬럼명 확인 (pykrx는 'close', 기타는 'current_price' 사용 가능)
            price_col = None
            if 'close' in df.columns:
                price_col = 'close'
            elif 'current_price' in df.columns:
                price_col = 'current_price'
            else:
                raise ValueError(f"종목 {code}의 DataFrame에 가격 컬럼('close' 또는 'current_price')이 없습니다.")
            
            # 수익률 = (당일 가격 / 전일 가격) - 1
            returns_df[code] = df[price_col].pct_change()
            
            # 종목명 저장
            if 'stock_name' in df.columns:
                stock_names[code] = df['stock_name'].iloc[0]
            else:
                stock_names[code] = code
        
        # NaN 제거 (첫 행은 수익률 계산 불가)
        returns_df = returns_df.dropna()
        
        if len(returns_df) < 30:
            logger.warning(f"데이터 부족: {len(returns_df)}일치 데이터만 있습니다. 최소 30일 필요.")
        
        logger.info(f"수익률 데이터: {len(returns_df)}일치")
        
        # 2. 평균 수익률과 공분산 행렬 계산
        mean_returns = returns_df.mean().values
        cov_matrix = returns_df.cov().values
        
        logger.info(f"평균 일 수익률: {mean_returns}")
        logger.info(f"공분산 행렬 형태: {cov_matrix.shape}")
        
        # 3. 최적화 제약조건 설정
        constraints = [
            # 모든 비중의 합 = 1 (100%)
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}
        ]
        
        # 각 자산의 비중 범위: 0 ≤ w_i ≤ 1 (공매도 불가, 100% 초과 불가)
        bounds = tuple((0, 1) for _ in range(n_stocks))
        
        # 4. 초기값 설정 (균등배분)
        init_weights = np.array([1/n_stocks] * n_stocks)
        
        logger.info(f"최적화 시작 - 초기 비중: {init_weights}")
        
        # 5. 최적화 실행 (SLSQP: Sequential Least Squares Programming)
        result = minimize(
            fun=self.negative_sharpe,
            x0=init_weights,
            args=(mean_returns, cov_matrix),
            method='SLSQP',
            bounds=bounds,
            constraints=constraints,
            options={'maxiter': 1000, 'ftol': 1e-9}
        )
        
        if not result.success:
            logger.warning(f"최적화 경고: {result.message}")
        
        # 6. 최적 비중 및 통계량 계산
        optimal_weights = result.x
        port_return, port_std, sharpe = self.calculate_portfolio_stats(
            optimal_weights, mean_returns, cov_matrix
        )
        
        logger.info(f"최적화 완료!")
        logger.info(f"최적 비중: {optimal_weights}")
        logger.info(f"기대수익률: {port_return:.2%}")
        logger.info(f"변동성: {port_std:.2%}")
        logger.info(f"샤프 비율: {sharpe:.4f}")
        
        # 7. 결과 정리
        result_data = PortfolioResult(
            stock_codes=stock_codes,
            stock_names=[stock_names[code] for code in stock_codes],
            weights=[round(float(w), 4) for w in optimal_weights],
            expected_return=round(float(port_return), 4),
            volatility=round(float(port_std), 4),
            sharpe_ratio=round(float(sharpe), 4)
        )
        
        return result_data
    
    def calculate_efficient_frontier(
        self,
        price_data: Dict[str, pd.DataFrame],
        n_portfolios: int = 100
    ) -> pd.DataFrame:
        """
        효율적 투자선(Efficient Frontier) 계산
        
        Args:
            price_data: 종목별 가격 데이터
            n_portfolios: 생성할 포트폴리오 개수
        
        Returns:
            수익률, 변동성, 샤프비율을 포함한 DataFrame
        """
        stock_codes = list(price_data.keys())
        n_stocks = len(stock_codes)
        
        if n_stocks < 2:
            raise ValueError("효율적 투자선은 2개 이상의 종목이 필요합니다.")
        
        # 수익률 데이터 준비
        returns_df = pd.DataFrame()
        for code, df in price_data.items():
            returns_df[code] = df['current_price'].pct_change()
        returns_df = returns_df.dropna()
        
        mean_returns = returns_df.mean().values
        cov_matrix = returns_df.cov().values
        
        # 랜덤 포트폴리오 생성
        results = []
        
        for _ in range(n_portfolios):
            # 랜덤 비중 생성 (합=1)
            weights = np.random.random(n_stocks)
            weights /= np.sum(weights)
            
            port_return, port_std, sharpe = self.calculate_portfolio_stats(
                weights, mean_returns, cov_matrix
            )
            
            results.append({
                'return': port_return,
                'volatility': port_std,
                'sharpe': sharpe
            })
        
        return pd.DataFrame(results)


# 전역 인스턴스
portfolio_optimizer = PortfolioOptimizer()