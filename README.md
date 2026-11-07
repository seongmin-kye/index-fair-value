# SOXX · QQQ · SPY 적정가

구성 종목의 목표 PER × 조정(non-GAAP) EPS 로 구한 지수 적정가. 페이지: `docs/index.html` (GitHub Pages).

- 목표 PER: 종목마다 직전 n년 forward PER(그때 주가 ÷ 12개월 뒤 실제 EPS 를 정상화한 값)의 백분위(띠 평균). n·백분위는 종목마다 자기 rolling 백테스트(RMSE 최소)로 고름. 관측 9개월부터 계산하고 27개월 미만이면 백분위를 중앙값 쪽으로 당김. 메모리(MU·SK하이닉스)는 MU 이익 고점 PER 평균. 100배 초과 달은 제외
- 곱하는 EPS 는 정상화 EPS = max(12개월 뒤 EPS, 앞 24개월~뒤 12개월 TTM 평균) — 이익 바닥에서 배수가 부풀고 적정가가 꺼지는 것을 막음(MCHP·INTC). 두 출처 컨센서스가 1.5배 넘게 다르면 TTM 에 가까운 출처만(`build.unify`)
- SOXX 지수 적정가(종목별 기준 합산): 매달 그 달 실제 구성·비중(SEC N-PORT 분기 공시, 2019-09~, 분기 사이는 주가로 굴림)대로 종목별 적정가 ÷ 주가를 합산, 오늘은 지금 구성(Zacks). 자기 기준이 없는 종목은 그 달 나머지 종목 목표 PER 중앙값(빌린 기준, 8종목 이상), 주가·EPS 가 없는 종목·현금·선물·상장 폐지 종목(XLNX·MXIM·IPHI·CCMP)은 중립(적정가 = 주가). 2019-09 이전은 계산하지 않음. 종목별 적정가 섹션은 지금 구성 종목 + 삼성전자만 보이고, 자기 기준이 없으면 계산 안 함
- 지수 PER 비교선: 1 ÷ Σ(비중 × 정상화 EPS ÷ 주가)(계산 가능 비중 50% 이상)를 지수 forward PER 로, 12개월 이상 지난 달의 중앙값(24개월 이상)을 목표로. 고르는 파라미터 없음
- QQQ·SPY: 같은 코드, 다만 비중은 아직 모든 달에 지금 Zacks 비중
- 규칙을 바꿀 때: `node scripts/audit_fv.js [docs/index.html] [QQQ·SPY 데이터 json]` 로 전 종목 이상 징후(자기 기준 없음 · 극단값 · 목표 PER 점프 · 격자 오차 · 적자)를 확인한 뒤 반영
- 회귀 테스트: `node scripts/test_fv.js` (MCHP·INTC 이익 바닥 · ARM 짧은 이력 · TSLA 출처 혼용 · 목표 PER 점프 없음 · 시점별 비중 · 지수 PER 비교선 등), `python3 scripts/test_update.py`
- 갱신: GitHub Actions — 평일 주가, 토요일 구성 종목·SEC N-PORT 구성(`nport`, repo secret `SEC_UA` = SEC 요청용 User-Agent)·Zacks 분기 EPS·연도별 컨센서스. 컨센서스는 2026-11 부터 매달 `data/consensus/{YYYY-MM}.json` 에 스냅샷(나중에 그 시점 컨센서스 기준 백테스트용)
- 데이터: Yahoo Finance(주가), Zacks(분기 EPS · ETF 구성), SEC EDGAR N-PORT(SOXX 과거 구성), Nasdaq/Yahoo/WiseReport(컨센서스). 투자 조언 아님

```
python3 scripts/update.py prices | full [TICKER ...] | recent | holdings | nport | splits [TICKER ...]   # recent: 발표 14일 이내 종목 컨센서스 · splits: 액면분할 복구
python3 scripts/build.py
```
