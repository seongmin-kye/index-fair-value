# SOXX · QQQ · SPY 적정가

구성 종목의 목표 PER × 조정(non-GAAP) EPS 로 구한 지수 적정가. 페이지: `docs/index.html` (GitHub Pages).

- 목표 PER: 종목마다 직전 n년 forward PER(그때 주가 ÷ 12개월 뒤 실제 EPS)의 백분위. n·백분위는 지수별 rolling 백테스트(RMSE 최소)로 고름
- 갱신: GitHub Actions — 평일 주가, 토요일 구성 종목·Zacks 분기 EPS·연도별 컨센서스
- 데이터: Yahoo Finance(주가), Zacks(분기 EPS · ETF 구성), Nasdaq/Yahoo/WiseReport(컨센서스). 투자 조언 아님

```
python3 scripts/update.py prices | full [TICKER ...] | holdings
python3 scripts/build.py
```
