"""
FastAPI 서버 테스트 클라이언트
서버가 실행 중일 때 이 스크립트로 테스트
"""
import requests
import json

BASE_URL = "http://localhost:8000"


def test_root():
    """루트 엔드포인트 테스트"""
    print("=" * 70)
    print("1. 루트 엔드포인트 테스트")
    print("=" * 70)
    
    response = requests.get(f"{BASE_URL}/")
    print(f"Status: {response.status_code}")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))


def test_single_stock():
    """개별 종목 조회 테스트"""
    print("\n" + "=" * 70)
    print("2. 개별 종목 조회 (삼성전자)")
    print("=" * 70)
    
    response = requests.get(f"{BASE_URL}/api/stocks/005930")
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n종목명: {data['stock_name']}")
        print(f"현재가: {data['current_data']['close_price']:,}원")
        print(f"등락률: {data['current_data']['change_rate']:+.2f}%")
        print(f"과거 데이터: {len(data['history_data'])}일치")
    else:
        print(f"Error: {response.json()}")


def test_portfolio_optimization():
    """포트폴리오 최적화 테스트"""
    print("\n" + "=" * 70)
    print("3. 포트폴리오 최적화")
    print("=" * 70)
    
    payload = {
        "stock_codes": ["005930", "000660", "005380"],
        "days": 252
    }
    
    print(f"\n요청: {json.dumps(payload, ensure_ascii=False)}")
    
    response = requests.post(
        f"{BASE_URL}/api/portfolio/optimize",
        json=payload
    )
    
    print(f"\nStatus: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        
        print(f"\n📈 최적 포트폴리오:")
        for name, weight in zip(data['stock_names'], data['weights_percent']):
            bar = "█" * int(weight / 2)
            print(f"  {name:12s}: {weight:6.2f}% {bar}")
        
        print(f"\n포트폴리오 통계:")
        print(f"  기대수익률: {data['expected_return_percent']:.2f}% (연)")
        print(f"  변동성:     {data['volatility_percent']:.2f}% (연)")
        print(f"  샤프 비율:  {data['sharpe_ratio']:.4f}")
    else:
        print(f"Error: {response.json()}")


def test_batch_stocks():
    """여러 종목 일괄 조회 테스트"""
    print("\n" + "=" * 70)
    print("4. 여러 종목 일괄 조회")
    print("=" * 70)
    
    payload = {
        "stock_codes": ["005930", "000660"]
    }
    
    response = requests.post(
        f"{BASE_URL}/api/stocks/batch",
        json=payload
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        
        for stock in data['stocks']:
            if 'error' not in stock:
                print(f"\n✓ {stock['stock_name']}")
                print(f"  현재가: {stock['current_data']['close_price']:,}원")
            else:
                print(f"\n✗ 에러: {stock['error']}")


def test_health():
    """헬스 체크 테스트"""
    print("\n" + "=" * 70)
    print("5. 헬스 체크")
    print("=" * 70)
    
    response = requests.get(f"{BASE_URL}/api/health")
    print(f"Status: {response.status_code}")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))


def main():
    """모든 테스트 실행"""
    print("\n" + "█" * 70)
    print(" " * 20 + "FastAPI 서버 테스트")
    print("█" * 70)
    
    try:
        test_root()
        test_single_stock()
        test_portfolio_optimization()
        test_batch_stocks()
        test_health()
        
        print("\n" + "█" * 70)
        print(" " * 20 + "모든 테스트 완료!")
        print("█" * 70)
        
    except requests.exceptions.ConnectionError:
        print("\n❌ 서버에 연결할 수 없습니다!")
        print("서버를 먼저 실행하세요: python -m backend.main")
    except Exception as e:
        print(f"\n❌ 테스트 중 오류: {e}")


if __name__ == "__main__":
    main()