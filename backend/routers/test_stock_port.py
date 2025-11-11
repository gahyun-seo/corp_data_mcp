"""
stocks.py + portfolio.py 통합 테스트
"""
import sys
from pathlib import Path

# 프로젝트 루트 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.routers.stocks import stock_service
from backend.routers.portfolio import portfolio_optimizer


def test_portfolio_optimization():
    """포트폴리오 최적화 통합 테스트"""
    print("=" * 70)
    print("포트폴리오 최적화 통합 테스트")
    print("=" * 70)
    
    # 1. 단일 종목 테스트
    print("\n[1] 단일 종목 (삼성전자)")
    print("-" * 70)
    
    codes = ["005930"]
    price_data = stock_service.get_portfolio_data(codes, days=60)
    
    if price_data:
        result = portfolio_optimizer.optimize_portfolio(price_data)
        
        print(f"\n종목: {result.stock_names[0]}")
        print(f"비중: {result.weights[0]*100:.2f}%")
        print("(단일 종목은 자동으로 100% 배분)")
    
    # 2. 2개 종목 테스트
    print("\n" + "=" * 70)
    print("[2] 2개 종목 (삼성전자 + SK하이닉스)")
    print("-" * 70)
    
    codes = ["005930", "000660"]
    price_data = stock_service.get_portfolio_data(codes, days=60)
    
    if len(price_data) >= 2:
        print(f"\n데이터 수집 완료:")
        for code, df in price_data.items():
            stock_name = df.iloc[-1]['stock_name']
            print(f"  - {stock_name}: {len(df)}일치")
        
        print(f"\n🔄 포트폴리오 최적화 실행 중...")
        result = portfolio_optimizer.optimize_portfolio(price_data)
        
        print(f"\n📈 최적 포트폴리오:")
        print("=" * 70)
        for name, weight in zip(result.stock_names, result.weights):
            bar = "█" * int(weight * 50)
            print(f"  {name:12s}: {weight*100:6.2f}% {bar}")
        
        print(f"\n포트폴리오 통계:")
        print(f"  기대수익률: {result.expected_return*100:>7.2f}% (연)")
        print(f"  변동성:     {result.volatility*100:>7.2f}% (연)")
        print(f"  샤프 비율:  {result.sharpe_ratio:>7.4f}")
        
        print(f"\n💡 해석:")
        if result.sharpe_ratio > 1.0:
            print("  - 샤프 비율 1.0 초과: 우수한 위험 대비 수익")
        elif result.sharpe_ratio > 0.5:
            print("  - 샤프 비율 0.5~1.0: 양호한 위험 대비 수익")
        else:
            print("  - 샤프 비율 0.5 미만: 위험 대비 수익이 낮음")
    
    # 3. 3개 종목 테스트
    print("\n" + "=" * 70)
    print("[3] 3개 종목 (삼성전자 + SK하이닉스 + 현대차)")
    print("-" * 70)
    
    codes = ["005930", "000660", "005380"]
    price_data = stock_service.get_portfolio_data(codes, days=60)
    
    if len(price_data) >= 2:
        print(f"\n데이터 수집 완료:")
        for code, df in price_data.items():
            stock_name = df.iloc[-1]['stock_name']
            print(f"  - {stock_name}: {len(df)}일치")
        
        print(f"\n🔄 포트폴리오 최적화 실행 중...")
        result = portfolio_optimizer.optimize_portfolio(price_data)
        
        print(f"\n📈 최적 포트폴리오:")
        print("=" * 70)
        
        # 비중 순으로 정렬
        sorted_pairs = sorted(
            zip(result.stock_names, result.weights),
            key=lambda x: x[1],
            reverse=True
        )
        
        for i, (name, weight) in enumerate(sorted_pairs, 1):
            bar = "█" * int(weight * 50)
            print(f"  {i}. {name:12s}: {weight*100:6.2f}% {bar}")
        
        print(f"\n포트폴리오 통계:")
        print(f"  기대수익률: {result.expected_return*100:>7.2f}% (연)")
        print(f"  변동성:     {result.volatility*100:>7.2f}% (연)")
        print(f"  샤프 비율:  {result.sharpe_ratio:>7.4f}")
        
        # JSON 형태로도 출력
        print(f"\n📋 API 응답 형태:")
        import json
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


def main():
    """통합 테스트 실행"""
    print("\n" + "█" * 70)
    print(" " * 15 + "STOCKS + PORTFOLIO 통합 테스트")
    print("█" * 70)
    
    try:
        test_portfolio_optimization()
        
        print("\n" + "█" * 70)
        print(" " * 20 + "통합 테스트 완료!")
        print("█" * 70)
        
        print("\n✅ 시스템 준비 완료:")
        print("  - stocks.py: 주가 데이터 수집 ✓")
        print("  - portfolio.py: 포트폴리오 최적화 ✓")
        print("  - 다음 단계: FastAPI 백엔드 구축")
        
    except Exception as e:
        print(f"\n❌ 테스트 중 오류: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()