# SOXX · QQQ · SPY 적정가

구성 종목의 목표 PER × 조정(non-GAAP) EPS 로 구한 지수 적정가. 페이지: `docs/index.html` (GitHub Pages).

- 목표 PER: 종목마다 직전 n년 forward PER(그때 주가 ÷ 12개월 뒤 실제 EPS)의 백분위. n·백분위는 지수별 rolling 백테스트(RMSE 최소)로 고름
- 곱하는 EPS 는 정상화 EPS = max(12개월 뒤 EPS, 앞뒤 3년 TTM 평균) — 이익 바닥에서 배수가 부풀고 적정가가 꺼지는 것을 막음(MCHP·INTC). 100배 초과 달은 제외. 창이 안 차는 종목은 직전 3년 관측(9개월 이상)에 같은 백분위, 그것도 없으면 종목별로는 계산 안 함(지수 합산은 나머지 종목 중앙값). 두 출처 컨센서스가 1.5배 넘게 다르면 TTM 에 가까운 출처만(`build.unify`)
- 규칙을 바꿀 때: `node scripts/audit_fv.js [docs/index.html] [QQQ·SPY 데이터 json]` 로 전 종목 이상 징후(자기 기준 없음 · 극단값 · 목표 PER 점프 · 격자 오차 · 적자)를 확인한 뒤 반영
- 회귀 테스트: `node scripts/test_fv.js` (MCHP·INTC 이익 바닥 · ARM 짧은 이력 · TSLA 출처 혼용 · 목표 PER 점프 없음 등)
- 갱신: GitHub Actions — 평일 주가, 토요일 구성 종목·Zacks 분기 EPS·연도별 컨센서스
- 데이터: Yahoo Finance(주가), Zacks(분기 EPS · ETF 구성), Nasdaq/Yahoo/WiseReport(컨센서스). 투자 조언 아님

```
python3 scripts/update.py prices | full [TICKER ...] | holdings
python3 scripts/build.py
```
