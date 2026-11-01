# 시점별 구성 종목으로 SOXX 적정가 · 백테스트 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SOXX 의 과거 적정가·백테스트가 매달 그 시점의 실제 구성 종목·비중(SEC N-PORT)을 쓰고, 오늘 적정가는 지금 구성을 쓰며, 지수 전체 n·p 격자 모드를 지수 PER 비교선으로 바꾼다.

**Architecture:** `scripts/update.py` 에 `nport` 모드(EDGAR → `data/holdings/SOXX/nport/*.json`, ID→티커는 `data/holdings/ids.json`)와 컨센서스 월별 스냅샷을 더한다. `scripts/build.py` 가 분기별 비중을 `SOXX_W_HIST` 한 줄로 페이지에 넣고, 페이지 JS 의 `weightsAt(T)` 가 분기 비중을 주가로 굴려 월별 비중을 만든다. 지수 적정가 합산(`rawRatio`)은 그 달 비중을 받는다. 지수 기준 격자(`GRID`·`targetsAt`)는 지우고 지수 PER 중앙값 비교선을 넣는다. QQQ·SPY 는 `SOXX_W_HIST` 가 비어 있으면 지금처럼 고정 비중으로 돈다.

**Tech Stack:** Python 3.12 표준 라이브러리(urllib, xml.etree, json), 페이지 JS(바닐라, 단일 `docs/index.html`), node 22+ (`scripts/run_idx.js`, `scripts/test_fv.js`), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-02-time-varying-holdings-design.md`

## Global Constraints

- 작업 트리에 이미 커밋 안 된 변경(README.md, `data/stocks/*.json` 다수)이 있다. **`git add -A` 금지.** 각 태스크가 만든 파일만 경로로 지정해 커밋한다.
- SEC 요청 `User-Agent`: 환경변수 `SEC_UA` 가 있으면 그 값, 없으면 `index-fair-value (https://github.com/seongmin-kye/index-fair-value)`.
- N-PORT 시리즈: `S000004354`, 트러스트 CIK `1100663`. 공시 목록 URL: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=S000004354&type=NPORT-P&count=100&output=atom`. XML: `https://www.sec.gov/Archives/edgar/data/1100663/{accession 에서 '-' 제거}/primary_doc.xml`.
- N-PORT 행 중 `assetCat == "EC"` 만 주식. ID 는 `cusip` 이 9자리이고 `000000000` 이 아니면 CUSIP, 아니면 `<isin value="…">`.
- 어떤 달이든 그 달에 SOXX 에 없던 종목이 적정가에 들어가면 안 된다. 2019-09 이전 달은 적정가 null (지금 비중으로 돌아가지 않는다).
- 페이지 JS 는 `scripts/run_idx.js` 와 `scripts/test_fv.js` 가 node 에서 그대로 돌린다 (DOM 없음, `buildSeg();` 이전까지). 새 계산 코드는 전부 `buildSeg();` 앞에 둔다.
- 각 태스크 끝에 `python3 scripts/build.py && node scripts/test_fv.js` 가 통과해야 한다 (Task 1~3 은 `node scripts/test_fv.js` 만).
- 커밋 메시지 끝에 `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Review Focus

- 같은 종목이 한 분기 XML 에 두 행(LRCX 분할 뒤 CUSIP 두 개)이면 비중을 **합쳐야** 한다. 따로 두면 비중이 이중 계산된다. → Task 1 테스트 `test_parse_merges_same_ticker`.
- 2019-09 이전 달은 `weightsAt` 이 null 이고 적정가도 null 이어야 한다. 조용히 지금 비중으로 떨어지면 원래 문제가 되돌아온다. → Task 5 `W1`, Task 6 `W5`.
- 어떤 분기에 종목 주가가 없을 때(상장 폐지 중립 종목, 막 상장한 종목) 비중 굴리기가 NaN 을 내거나 합이 깨지면 안 된다. 그 종목은 분기 비중 그대로, 나머지는 정상 굴림. → Task 5 `W3`.
- 마지막 N-PORT 분기 이후의 달과 오늘은 Zacks 현재 비중(합 99.9%)을 써야 한다. 오늘 적정가가 2026-06 공시 비중으로 계산되면 안 된다. → Task 5 `W2`, Task 6 `W6`.
- 지수 PER 비교선: 계산 가능한 종목 비중이 절반 미만이거나 이익수익률 ≤ 0 이면 null 이어야 한다. Infinity 가 차트에 들어가면 로그 축이 깨진다. → Task 7 `I2`.

---

### Task 1: `update.py nport` — N-PORT 받기 · 파싱 · ID→티커

**Files:**
- Modify: `scripts/update.py` (`# ---------- 구성 종목 ----------` 아래, `main()`)
- Create: `scripts/test_update.py`
- Create: `data/holdings/ids.json` (처음엔 `{}`)

**Interfaces:**
- Produces: `data/holdings/SOXX/nport/{YYYY-MM-DD}.json` = `[[ticker|null, name, pct, shares, valUSD, id], …]` (EC 만, 같은 ticker 는 한 행으로 합산 — pct·shares·valUSD 합, name·id 는 첫 행), pct 는 소수 4자리.
- Produces: `data/holdings/ids.json` = `{ id: ticker }`.
- Produces (python 함수, 모두 `update.py` 모듈 수준):
  - `sec_ua() -> dict` : `{"User-Agent": …}` (Global Constraints 규칙)
  - `nport_filings() -> list[tuple[str, str]]` : `[(accession, filing_date)]` Atom 에서. 최신 먼저.
  - `nport_parse(xml_text: str) -> tuple[str, list[tuple[str, str, float, float, float]]]` : `(repPdDate, [(name, id, pct, shares, valUSD)])` EC 만, 합치지 않음.
  - `resolve_ids(rows, ids: dict, zacks_names: dict[str, str]) -> list[list]` : 저장 형식의 행. `ids` 에 없는 id 는 OpenFIGI(`POST https://api.openfigi.com/v3/mapping`, 본문 `[{"idType":"ID_CUSIP"|"ID_ISIN","idValue":id,"exchCode":"US"}]`, 한 번에 최대 10개, 429 면 60초 쉬고 재시도)로 채워 `ids` 에 넣는다. OpenFIGI 가 돌려준 티커가 `zacks_names`(Zacks 현재 구성: `{ticker: name}`)의 어떤 종목과 **같은 회사명(대소문자·구두점 무시, 앞 단어 2개 일치)** 이면 Zacks 티커를 쓴다. 못 찾으면 ticker `None`, 표준출력에 `미매핑 {name} {id}`.
  - `update_nport() -> list[str]` : 오류 문자열 목록. 없는 분기만 받아 저장(파일 있으면 건너뜀), `ids.json` 저장, 새 티커(파일 없음, ticker 가 있음)는 `update_full_one(t, name)` 로 받는다.

- [ ] **Step 1: 실패하는 테스트 작성** — `scripts/test_update.py` (unittest). XML 픽스처는 문자열로 파일 안에: 종목 3행(NVDA CUSIP `67066G104`, LRCX 두 행 CUSIP `512807108`·`512807306` 각 pct 2.0·2.5, ASML `cusip` 이 `N/A` 이고 ISIN `USN070592100`), 비주식 2행(`assetCat` STIV·DE).

```python
class NportTest(unittest.TestCase):
    def test_parse_keeps_only_equities_and_picks_id(self):
        date, rows = update.nport_parse(FIXTURE)
        self.assertEqual(date, "2024-12-31")
        self.assertEqual([r[1] for r in rows], ["67066G104", "512807108", "512807306", "USN070592100"])
    def test_parse_merges_same_ticker(self):
        ids = {"67066G104": "NVDA", "512807108": "LRCX", "512807306": "LRCX", "USN070592100": "ASML"}
        out = update.resolve_ids(update.nport_parse(FIXTURE)[1], ids, {})
        lrcx = [r for r in out if r[0] == "LRCX"]
        self.assertEqual(len(lrcx), 1); self.assertAlmostEqual(lrcx[0][2], 4.5)
    def test_resolve_prefers_zacks_ticker_on_same_name(self):
        # OpenFIGI 를 흉내: update.openfigi 를 monkeypatch 해 "TSMWI" 를 돌려주게 하고, zacks_names 에 "TSM": "TAIWAN SEMICONDUCTOR MFG" 가 있으면 TSM
    def test_resolve_unmapped_is_none(self):
        # openfigi 가 {} 를 돌려주면 ticker None, ids 에 안 들어감
    def test_sec_ua_default(self):
        self.assertIn("github.com/seongmin-kye/index-fair-value", update.sec_ua()["User-Agent"])
```

- [ ] **Step 2: 실패 확인** — `python3 scripts/test_update.py` → `AttributeError: … nport_parse`
- [ ] **Step 3: 구현** — `sec_ua`, `nport_filings`, `nport_parse`(xml.etree, 네임스페이스 무시: 태그 끝 이름으로 찾는다), `openfigi(ids: list[str]) -> dict[str, str]`(테스트가 monkeypatch 할 수 있게 별도 함수), `resolve_ids`, `update_nport`. `main()` 에 `elif mode == "nport": errs = update_nport()`. 파일 상단 docstring 에 `nport` 줄 추가.
- [ ] **Step 4: 통과 확인** — `python3 scripts/test_update.py` → `OK`
- [ ] **Step 5: 커밋**

```bash
git add scripts/update.py scripts/test_update.py data/holdings/ids.json
git commit -m "feat: update.py nport — SEC N-PORT 분기 구성 받기"
```

---

### Task 2: 실제 데이터 받기 — 28개 분기, 수동 매핑, 과거 종목 파일

**Files:**
- Modify: `data/holdings/ids.json`
- Create: `data/holdings/SOXX/nport/*.json` (28개)
- Create: `data/stocks/{ACLS,AZTA,CRUS,LSCC,MKSI,OLED,ONTO,QRVO,RMBS,SLAB,SMTC,SYNA,WOLF}.json`

- [ ] **Step 1: 수동 매핑 먼저** — `ids.json` 에 넣는다 (OpenFIGI 가 못 찾는 상장 폐지·개명 종목): `"983919101": "XLNX"`, `"57772K101": "MXIM"`, `"45772F107": "IPHI"`, `"12709P103": "CCMP"`, `"12571T100": "CCMP"`, `"114340102": "AZTA"`, `"225447101": "WOLF"`.
- [ ] **Step 2: 받기** — `python3 scripts/update.py nport` (몇 분: SEC 28건 + OpenFIGI + 새 종목 13개 Zacks). 출력에서 `미매핑` 줄이 있으면 `ids.json` 에 손으로 넣고 그 분기 파일을 지운 뒤 다시 실행.
- [ ] **Step 3: 검증**

```bash
ls data/holdings/SOXX/nport | wc -l            # 28
python3 -c "
import json,glob
for f in sorted(glob.glob('data/holdings/SOXX/nport/*.json')):
    r=json.load(open(f)); s=sum(x[2] for x in r); n=[x for x in r if x[0] is None]
    assert 95<=s<=101.5, (f,s); assert not n, (f,n)
print('ok')"
python3 -c "import json;r=json.load(open('data/holdings/SOXX/nport/2021-09-30.json'));print([x[:3] for x in r if x[0] in ('XLNX','NVDA','LRCX')])"
ls data/stocks/ACLS.json data/stocks/WOLF.json data/stocks/AZTA.json
```

기대: 28, `ok`, XLNX·NVDA·LRCX 세 행, 종목 파일 존재. XLNX 는 ticker 가 있지만 종목 파일이 없는 게 맞다 (중립).

- [ ] **Step 4: 커밋**

```bash
git add data/holdings/ids.json data/holdings/SOXX/nport data/stocks/ACLS.json data/stocks/AZTA.json data/stocks/CRUS.json data/stocks/LSCC.json data/stocks/MKSI.json data/stocks/OLED.json data/stocks/ONTO.json data/stocks/QRVO.json data/stocks/RMBS.json data/stocks/SLAB.json data/stocks/SMTC.json data/stocks/SYNA.json data/stocks/WOLF.json
git commit -m "data: SOXX N-PORT 2019-09 ~ 2026-06 구성 · 과거 구성 종목 13개"
```

---

### Task 3: 컨센서스 월별 스냅샷 · 워크플로

**Files:**
- Modify: `scripts/update.py` (`main()` 의 `full` 분기, 새 함수), `scripts/test_update.py`
- Modify: `.github/workflows/update.yml` (`구성 종목 · 실적 · 컨센서스` 단계)

**Interfaces:**
- Produces: `data/consensus/{YYYY-MM}.json` = `{ ticker: { "ntm": float|null, "fy": [[fy_year, fy_month, eps_avg], …] } }`. 한 달에 하나: 파일이 있으면 쓰지 않는다.
- `ntm_eps(fwd: list, asof: date) -> float|None` : 페이지 `ntmEps` 와 같은 규칙 — asof 부터 12개월 구간과 각 회계연도(`fy` = [년, 결산월], 결산월 말일 끝 1년) 의 겹치는 비율로 `(eps[0]+eps[1])/2` 를 가중합, 겹침 합이 0.98 미만이거나 겹치는 연도에 eps 가 없으면 None.
- `consensus_snapshot(tickers: list[str], today: date) -> str|None` : 쓴 파일 경로 또는 None(이미 있음).

- [ ] **Step 1: 실패하는 테스트** — `test_update.py` 에 추가:

```python
def test_ntm_eps_weights_fiscal_years(self):
    fwd = [{"fy": [2026, 12], "eps": [10, 10]}, {"fy": [2027, 12], "eps": [20, 20]}]
    self.assertAlmostEqual(update.ntm_eps(fwd, dt.date(2026, 7, 1)), 10 * (184/365) + 20 * (181/365), places=1)
def test_ntm_eps_none_when_gap(self):
    self.assertIsNone(update.ntm_eps([{"fy": [2026, 12], "eps": [10, 10]}], dt.date(2026, 7, 1)))
def test_snapshot_once_per_month(self):
    # tmp DATA 디렉터리로 monkeypatch; 두 번 호출하면 두 번째는 None
```

- [ ] **Step 2: 실패 확인** — `python3 scripts/test_update.py`
- [ ] **Step 3: 구현** — `ntm_eps`, `consensus_snapshot`. `main()` 의 `full` 분기 끝에 `consensus_snapshot(args or all_tickers(), dt.date.today())`.
- [ ] **Step 4: 통과 확인** — `python3 scripts/test_update.py` → `OK`
- [ ] **Step 5: 워크플로** — `update.yml` 의 `구성 종목 · 실적 · 컨센서스` 단계 `run:` 에 `python3 scripts/update.py holdings` 다음 줄로 `python3 scripts/update.py nport || true` 추가. 커밋 단계의 `git add -A data docs` 는 그대로 (Actions 에서는 작업 트리가 깨끗함).
- [ ] **Step 6: 커밋**

```bash
git add scripts/update.py scripts/test_update.py .github/workflows/update.yml
git commit -m "feat: 컨센서스 월별 스냅샷 · 토요일 nport 갱신"
```

---

### Task 4: `build.py` — 종목 집합 확장 · `SOXX_W_HIST` 주입 · `run_idx.js` 통과

**Files:**
- Modify: `scripts/build.py` (`main()`, 새 함수 `w_hist`)
- Modify: `docs/index.html` (`const DATA = …` 바로 아래에 `const SOXX_W_HIST = {};` 한 줄 추가 — build 가 치환할 자리)
- Modify: `scripts/run_idx.js`

**Interfaces:**
- Produces (페이지 전역): `SOXX_W_HIST = { "YYYY-MM-DD": { "TICKER": pct, …, "_neutral": pct } }`. ticker 가 `DATA` 에 있는 행만 티커 키, 나머지(ticker null 또는 종목 파일 없음)는 `_neutral` 에 합산. 키는 분기말 날짜 오름차순.
- `DATA` = Zacks 현재 구성(비중 `w`) ∪ N-PORT 에 나온 티커 중 종목 파일 있는 것(`w: 0`). 순서: 현재 구성 먼저(비중순 그대로), 그다음 과거 종목 알파벳순.
- `run_idx.js PAGE DATA_JSON HIST_JSON OUT_JSON [SPAN]`: `DATA_JSON` 이 `-` 가 아니면 `const SOXX_W_HIST = {};` 로도 치환한다 (QQQ·SPY 는 고정 비중).
- `build.py`: `w_hist() -> dict` 위 형식. `main()` 에서 `s = line(s, "SOXX_W_HIST", js(w_hist()) + ";")`.

- [ ] **Step 1: 페이지에 자리 만들기** — `docs/index.html` 의 `const DATA = …;` 줄 바로 다음 줄에 `const SOXX_W_HIST = {};  // {분기말: {티커: 비중%, _neutral: %}} build.py 가 채움` 추가.
- [ ] **Step 2: `build.py`** — `soxx` 리스트를 위 `DATA` 규칙으로 만든다(`soxx_entry(t, name, 0)` 로 과거 종목). `w_hist()` 구현. `run_idx.js` 치환 추가.
- [ ] **Step 3: 빌드·검증**

```bash
python3 scripts/build.py && node scripts/test_fv.js
node -e "
const s=require('fs').readFileSync('docs/index.html','utf8');
const w=JSON.parse(s.match(/^const SOXX_W_HIST = (.*);/m)[1]); const d=JSON.parse(s.match(/^const DATA = (.*);/m)[1]);
console.log(Object.keys(w).length, Object.keys(w)[0], Object.keys(w).at(-1), 'XLNX neutral?', w['2021-09-30'].XLNX===undefined, w['2021-09-30']._neutral.toFixed(2), 'DATA', d.length, d.filter(x=>x.w===0).length)"
```

기대: `all passed`; `28 2019-09-30 2026-06-30 XLNX neutral? true 3.xx DATA 44 13` (DATA 수는 현재 구성 수 + 13).

- [ ] **Step 4: 커밋**

```bash
git add scripts/build.py scripts/run_idx.js docs/index.html docs/version.json
git commit -m "build: SOXX_W_HIST 주입 · 과거 구성 종목을 DATA 에 포함"
```

---

### Task 5: 페이지 `weightsAt(T)` — 분기 비중을 주가로 굴린 월별 비중

**Files:**
- Modify: `docs/index.html` (`mkFV`/`FV` 정의 뒤, `buildFpe` 앞)
- Modify: `scripts/test_fv.js`

**Interfaces:**
- `weightsAt(T: number) -> { w: Map<s, number>, neutral: number, cash: number, src: "nport"|"now" } | null`
  - `SOXX_W_HIST` 가 비어 있으면(QQQ·SPY): 모든 T 에 `{ w: FV 의 d.w, neutral: 0, cash: 100 − Σw, src: "now" }`.
  - 분기 목록 `WQ = Object.keys(SOXX_W_HIST).map(k => ({ k, m: monthIdx(k.slice(0,7)), w: SOXX_W_HIST[k] }))` 오름차순. T < WQ[0].m → `null`. T > WQ.at(-1).m → `"now"` (위와 같이 d.w). 그 외 Q = m ≤ T 인 마지막 분기.
  - 굴리기: 종목 i 의 `f = P_i(T) / P_i(Q.m)` (둘 다 `s.byM[·][3]` 가 있을 때만, 없으면 1). `w'_i = Q.w[t] × f`, `_neutral` 은 f = 1. 전체(종목 + neutral) 합이 Q 의 합과 같도록 한 번 정규화. `cash = 100 − Q 의 합`.
  - 결과는 T 별로 메모이즈 (`W_CACHE`).
- `FV` 의 `s.w` 는 더 이상 쓰지 않는다 (남겨 두되 합산에는 안 씀).

- [ ] **Step 1: 실패하는 테스트** — `test_fv.js` 에 (B5 뒤):

```js
// W: 시점별 비중
const W1 = weightsAt(monthIdx("2019-06")), W2 = weightsAt(ASOF_M), W3 = weightsAt(monthIdx("2021-11")), W4 = weightsAt(monthIdx("2021-09"));
check("W1 2019-09 이전은 비중 없음", W1 === null);
check("W2 오늘은 Zacks 현재 비중 (합 99~100)", W2 && W2.src === "now" && Math.abs([...W2.w.values()].reduce((a, b) => a + b, 0) + W2.cash - 100) < 1e-6 && W2.w.get(find("ALAB")) > 2);
const sum3 = [...W3.w.values()].reduce((a, b) => a + b, 0) + W3.neutral;
check("W3 2021-11 비중: 굴린 뒤에도 합 = 분기 합, NaN 없음, XLNX 는 중립에", W3.src === "nport" && isFinite(sum3) && Math.abs(sum3 - ([...W4.w.values()].reduce((a, b) => a + b, 0) + W4.neutral)) < 1e-6 && W3.neutral > 3 && !W3.w.has(find("XLNX") || {}), sum3.toFixed(2) + " neutral " + W3.neutral.toFixed(2));
check("W4 2021-09 ALAB 비중 0, NVDA 7~8", !W4.w.get(find("ALAB")) && W4.w.get(find("NVDA")) > 7 && W4.w.get(find("NVDA")) < 8.5);
check("W4 2021-10 NVDA 비중이 10월 주가만큼 움직임", Math.abs(weightsAt(monthIdx("2021-10")).w.get(find("NVDA")) / W4.w.get(find("NVDA")) - find("NVDA").byM[monthIdx("2021-10")][3] / find("NVDA").byM[monthIdx("2021-09")][3] * (sum3 / sum3)) < 0.05);
```

(마지막 검사는 정규화 때문에 정확히 같지 않으므로 5% 허용.)

- [ ] **Step 2: 실패 확인** — `node scripts/test_fv.js` → `weightsAt is not defined`
- [ ] **Step 3: 구현** — `weightsAt` 와 `W_CACHE`. `find("XLNX")` 는 undefined 일 수 있으니 테스트의 `|| {}` 그대로.
- [ ] **Step 4: 통과 확인** — `python3 scripts/build.py && node scripts/test_fv.js` → `all passed`
- [ ] **Step 5: 커밋**

```bash
git add docs/index.html scripts/test_fv.js docs/version.json
git commit -m "feat: weightsAt(T) — N-PORT 분기 비중을 주가로 굴린 월별 비중"
```

---

### Task 6: 종목별 합산을 그 달 비중으로 · 지수 기준 격자 제거

**Files:**
- Modify: `docs/index.html` — `rawRatio`, `histRatio`, `nowRatio` 그대로, `targetsAt`·`targetInfo`·`fillTargets`·`GRID`·`FV_N`·`FV_P`·`GRID_N`·`GRID_P`·`TG_NOW`·`TG_MED`·`TG_BY_T`·`fvBacktest` 의 격자 표 부분·`SUM_ERR` IIFE·`sfvTarget`·`sumTg`·`FV_HIST`/`FV_PTS` 계산·`applyBasis`·`fvContrib`·`IDX_SET`/`useIndex`·HTML 의 `bt-thead`/`bt-tbody` 표·`fv-leg-short`
- Modify: `scripts/run_idx.js` (출력 형식), `scripts/test_fv.js`

**Interfaces:**
- `memoryRule(s, T) -> {pe, rule} | null` : `MEMORY.has(s.d.t)` 이고 `MU_PEAKS` 중 `q.i + 18 <= T` 가 있으면 `{ pe: mean(그 per 들), rule: "메모리: MU 이익 고점 PER 평균" }`.
- `peerAt(T, W) -> number|null` : `W.w.get(x) > 0` 이고 `!MEMORY.has(x.d.t)` 인 x 의 `ownRule(x, T).pe` 중앙값, 8개 이상일 때. `W` 가 null 이면 null. (T, W.src) 로 메모이즈.
- `sumTargets(T, W) -> { tg: Map<s, number|null>, kind: Map<s, "memory"|"own"|"peer"|null> }` : `W.w.get(s) > 0` 인 s 만. 순서 memoryRule → ownRule → peerAt.
- `sfvTarget(s, T)` (종목별 섹션용, 그대로 이름 유지) : `memoryRule(s, T) || ownRule(s, T) || { pe: sfvPeer(T), rule: "자기 기준을 정할 수 없음: 나머지 종목 목표 PER 중앙값" }`. `sfvPeer` 모집단은 `SFV_LIST`(Task 9 에서 현재 구성으로 좁힘).
- `rawRatio(tg: Map, ratioOf, W) -> number` : `W` null 이면 NaN. `W.cash/100 + W.neutral/100 + Σ W.w.get(s)/100 × (ratioOf(s, tg.get(s)) ?? 1)`.
- `mix(T, W, tg, kind, ratioOf) -> { own, peer, neutral, n }` : 비중 > 0 인 종목마다 ratio null → neutral, kind memory/own → own, peer → peer; `neutral += W.neutral + W.cash`; `n` = 비중 > 0 인 종목 수.
- `FV_HIST[i] = { x, label, px, fv2, own, peer, neutral, n, noW: boolean, real }` (`fvI` 는 Task 7). `fv2` 는 `W` 없거나 `rawRatio` 가 NaN 이면 null.
- `FV_X5` = `fv2` 가 처음 있는 달 (이름 유지; "5년 보기 시작").
- `W_NOW = weightsAt(ASOF_M)`, `SUM_NOW = sumTargets(ASOF_M, W_NOW)`, `TG_SUM_NOW = SUM_NOW.tg`.
- `FV_PTS[i]` : `fv2`, `cagr2` 는 지금처럼, `W_NOW` 로.
- `BT = { T0, T1, n, sumErr, rho }` (span 은 `GRID_SPAN`): 달 `T ∈ [ASOF_M − 11 − 12·GRID_SPAN, ASOF_M − 12]` 중 `fv2 > 0` 인 것. `sumErr` = RMSE(log(px/fv2)), `rho` = spearman(−log(fv2/px), log(px[T+12]/px[T])) (px[T+12] 있는 달).
- `applyBasis()` : 이 태스크에서는 `h.fv = h.fv2` 만 (`fvI` 는 Task 7).
- `run_idx.js` 출력: `{ price, wsum, asof, x5, stocks, cash, cover, covHist, bt: BT, hist: [[x, px, null, fv2, own, peer, neutral, n]], pts: [[y, null, fv2]] }`. `IDX_SET[k] = { price, x5, bt, hist, pts, r }`, `useIndex` 는 `SOXX_PRICE·FV_X5·BT·FV_HIST·FV_PTS` 만 바꿈.
- 지운 것: `targetsAt`, `targetInfo`, `fillTargets`, `GRID`, `FV_N`, `FV_P`, `GRID_N`, `GRID_P`, `TG_NOW`, `TG_MED`, `TG_BY_T`, `SUM_ERR`, `short`/`show-short`/`fv-leg-short`, `bt-thead`/`bt-tbody` 표. `sfvCompute` 의 `TG_BY_T` 순회는 `for (let k = SFV_X0; k < ASOF_M; k++)` (`const SFV_X0 = FV_X5` 를 `useIndex` 호출 전에 잡아 둠).

- [ ] **Step 1: 실패하는 테스트** — `test_fv.js`: B2 의 `TG_NOW` 줄을 `check("B2 지수 합산(TG_SUM_NOW)도 ARM 에 자기 중앙값", TG_SUM_NOW.get(find("ARM")) > 50, …)` 로 바꾸고 추가:

```js
const h1909 = FV_HIST.find((h) => h.label === "2019-08"), h2109 = FV_HIST.find((h) => h.label === "2021-09"), hNow = FV_HIST.at(-1);
check("W5 2019-08 적정가 없음(noW)", h1909.fv2 == null && h1909.noW);
check("W6 2021-09 적정가 있음, own+peer+neutral = 100", h2109.fv2 > 0 && Math.abs(h2109.own + h2109.peer + h2109.neutral - 100) < 1e-6, [h2109.own, h2109.peer, h2109.neutral].map((v) => v.toFixed(1)).join("/"));
check("W6 2021-09 XLNX 중립 ≥ 3%p 포함", h2109.neutral >= 3);
check("W7 오늘 적정가는 현재 비중 (ALAB 기여 있음)", TG_SUM_NOW.has(find("ALAB")) && FV_PTS[0].fv2 > 0);
check("W8 BT 는 2020-10 ~ 2025-10, 61개월 이하, sumErr 0.05~0.5", BT.T0 === monthIdx("2020-10") && BT.n <= 61 && BT.sumErr > 0.05 && BT.sumErr < 0.5, BT.n + " " + BT.sumErr.toFixed(3));
check("W9 격자 전역 제거", typeof GRID === "undefined" && typeof targetsAt === "undefined");
```

- [ ] **Step 2: 실패 확인** — `node scripts/test_fv.js`
- [ ] **Step 3: 구현** — Interfaces 대로. `fvBacktest()` 는 격자 표 대신 `bt-note` 한 문장만: `` `종목별 합산 적정가와 실제가 차이의 제곱평균(RMSE, 로그 기준 ≈ %) ${(BT.sumErr*100).toFixed(1)}%, ${mlabel(BT.T0)} ~ ${mlabel(BT.T1)} ${BT.n}개월. 괴리와 다음 12개월 ${fvView.idx} 수익의 순위상관 ${BT.rho.toFixed(2)}.` `` (Task 7·8 이 문장을 늘린다). HTML 의 `<table class="fv-table bt-table">…</table>` 블록(fair 섹션 것만)과 `fv-short-leg` span 삭제. `fv-sub` 의 두 분기 중 지수 기준 분기는 임시로 종목별 문구와 같게.
- [ ] **Step 4: 통과 확인** — `python3 scripts/build.py && node scripts/test_fv.js` → `all passed`. 빌드 로그의 `console.log` (run_idx.js) 가 `… stocks`, `RMSE …%` 를 찍도록 `run_idx.js` 마지막 줄도 새 필드로 고친다.
- [ ] **Step 5: 커밋**

```bash
git add docs/index.html scripts/run_idx.js scripts/test_fv.js docs/version.json
git commit -m "feat: 지수 적정가를 그 달 구성·비중으로 합산, 지수 기준 격자 제거"
```

---

### Task 7: 지수 PER 비교선

**Files:**
- Modify: `docs/index.html` (Task 6 의 `FV_HIST`/`FV_PTS` 계산 뒤), `scripts/run_idx.js`, `scripts/test_fv.js`

**Interfaces:**
- `eyAt(T, W) -> number|null` : `W.w.get(s) > 0` 이고 `histRatio(T)(s, 1)` 이 null 이 아닌 s(= 주가·12개월 뒤 EPS 있고 이익 바닥 아님) 에 대해 `Σ w·E(T+12)/P(T) ÷ Σ w`. 그런 s 의 비중 합이 50 미만이거나 결과 ≤ 0 이면 null.
- `IDX_PER: { [T]: number }` = `1 / eyAt(T, weightsAt(T))` (null 제외), `T < ASOF_M`.
- `idxTarget(T) -> number|null` : `IDX_PER[i]` (i ≤ T − 12) 가 24개 이상이면 그 중앙값.
- `FV_HIST[i].fvI` = `px × idxTarget(T) / IDX_PER[T]` (둘 다 있을 때), 아니면 null.
- `eyNow(y, W) -> number|null` : `y == null` 이면 `s.eN`, 아니면 `s.path[y+1]`; 이익 바닥 규칙은 `nowRatio` 와 같게; 50% 규칙 동일.
- `FV_PTS[i].fvI = SOXX_PRICE × idxTarget(ASOF_M) / (1 / eyNow(y, W_NOW))`, `cagrI` 는 `cagr2` 와 같은 식.
- `BT` 에 추가: `cmpN`(fvI 와 fv2 가 모두 있는 백테스트 달 수), `sumErrCmp`, `idxErr`, `cmpT0`.
- `applyBasis()` : `basis === "index"` 면 `h.fv = h.fvI`, 아니면 `h.fv2`; `FV_PTS` 도. 기본 `fvView.basis = "sum"`; localStorage `"index"` 면 index.
- `run_idx.js` hist/pts 의 null 자리에 fvI.

- [ ] **Step 1: 실패하는 테스트**

```js
check("I1 IDX_PER 2021-09 는 15~60", IDX_PER[monthIdx("2021-09")] > 15 && IDX_PER[monthIdx("2021-09")] < 60, IDX_PER[monthIdx("2021-09")]);
check("I1 비교선 시작 2022-08 이후, 그 전 null", FV_HIST.find((h) => h.fvI).label >= "2022-08" && FV_HIST.find((h) => h.label === "2022-06").fvI == null);
check("I2 비교선에 Infinity/NaN 없음", FV_HIST.every((h) => h.fvI == null || isFinite(h.fvI)) && FV_PTS.every((p) => p.fvI == null || isFinite(p.fvI)));
check("I2 계산 가능 비중 절반 미만이면 null", eyAt(monthIdx("2021-09"), { w: new Map([[find("NVDA"), 10]]), neutral: 0, cash: 90, src: "nport" }) === null);
check("I3 BT 비교 달 수 30~45, idxErr 유한", BT.cmpN >= 30 && BT.cmpN <= 45 && isFinite(BT.idxErr) && isFinite(BT.sumErrCmp), BT.cmpN + " " + BT.idxErr.toFixed(3));
check("I4 기본 basis = sum", fvView.basis === "sum");
```

- [ ] **Step 2: 실패 확인** — `node scripts/test_fv.js`
- [ ] **Step 3: 구현** — Interfaces 대로. `bt-note` 문장에 덧붙임: `` ` 비교선(지수 forward PER 의 과거 중앙값)이 있는 ${mlabel(BT.cmpT0)} 부터 ${BT.cmpN}개월에서는 종목별 합산 ${(BT.sumErrCmp*100).toFixed(1)}% · 지수 PER ${(BT.idxErr*100).toFixed(1)}%.` ``. `fv-b-index` 버튼 문구 `지수 PER`, `fv-sub` 의 index 분기 문구: `` `목표 PER = 지수 forward PER(비중 가중 이익수익률의 역수)의 ${mlabel(BT.cmpT0)} 이전 포함 과거 중앙값 · 비교용` ``. `alt()`·`row("참고: …")` 는 `fvI`/`fv2` 로 그대로.
- [ ] **Step 4: 통과 확인** — `python3 scripts/build.py && node scripts/test_fv.js` → `all passed`
- [ ] **Step 5: 커밋**

```bash
git add docs/index.html scripts/run_idx.js scripts/test_fv.js docs/version.json
git commit -m "feat: 지수 forward PER 중앙값 비교선"
```

---

### Task 8: 단순 예측 EPS 기준 RMSE 한 문장 (설계 8a)

**Files:**
- Modify: `docs/index.html` (`histRatio` 옆, `BT` 계산), `scripts/run_idx.js`, `scripts/test_fv.js`

**Interfaces:**
- `FWD(s, T) -> number|null` : `e0 = epsAt(s, T)`; `g` = `i ∈ [T−47, T−12]` 에서 `epsAt(s, i+12)/epsAt(s, i) − 1` (둘 다 > 0) 의 중앙값, 관측 12개 미만이면 null; `e0 × (1 + clamp(g, −0.5, 0.5))`, `e0 ≤ 0` 이면 null.
- `histRatioFwd(T)` : `histRatio` 와 같되 `e = FWD(s, T)`. 이익 바닥 제외는 그대로 `isTrough(s, T)`.
- `BT.fwdErr` : 백테스트 달(`BT` 의 달들)에서 `fvF = px × rawRatio(sumTargets(T, W).tg, okRatio(histRatioFwd(T)), W)` 가 > 0 인 달의 RMSE(log(px/fvF)).

- [ ] **Step 1: 실패하는 테스트**

```js
check("F1 FWD NVDA 2021-09 = TTM × (1+g), 0.5배 상한", (() => { const s = find("NVDA"), T = monthIdx("2021-09"), v = FWD(s, T); return v > 0 && v <= epsAt(s, T) * 1.5 && v >= epsAt(s, T) * 0.5; })());
check("F2 fwdErr > sumErr (실제값보다 못함) 이고 유한", isFinite(BT.fwdErr) && BT.fwdErr > BT.sumErr, (BT.fwdErr * 100).toFixed(1));
```

- [ ] **Step 2: 실패 확인** — `node scripts/test_fv.js`
- [ ] **Step 3: 구현** — Interfaces 대로. `bt-note` 끝에: `` ` 과거 적정가는 12개월 뒤 실제 EPS 기준입니다. T 시점에 알 수 있던 단순 예측(TTM × 직전 3년 실현 성장률 중앙값)으로 바꾸면 ${(BT.fwdErr*100).toFixed(1)}% — 컨센서스 기준의 오차는 그 사이입니다.` ``. `run_idx.js` 는 `bt` 를 통째로 넘기므로 추가 작업 없음을 확인.
- [ ] **Step 4: 통과 확인** — `python3 scripts/build.py && node scripts/test_fv.js` → `all passed`
- [ ] **Step 5: 커밋**

```bash
git add docs/index.html scripts/test_fv.js docs/version.json
git commit -m "feat: 백테스트 설명에 단순 예측 EPS 기준 RMSE"
```

---

### Task 9: 화면 문구 · 노출 범위 · README

**Files:**
- Modify: `docs/index.html` (fair 섹션 HTML 설명 `<li>`, `fvRender`, `fvChart` 툴팁, `SFV_LIST`, 원자료 표, `fv-s-10` 라벨, `fv-alt-note`), `README.md`, `scripts/test_fv.js`

**Interfaces:**
- `SFV_LIST = FV.filter((s) => s.d.w > 0).concat(FV_X)`. 원자료 표(`buildSeg`/`select` 의 `DATA` 순회)는 `DATA.filter((d) => d.w > 0)`.
- `fvRender`: `$("fv-s-10").textContent = IX === "SOXX" ? "2019-09~" : "10년"`. 요약 줄(`fv-sub`) 끝에 `` ` · 지금 구성 ${hNow.n}종목: 자기 기준 ${own}% · 빌린 기준 ${peer}% · 중립 ${neutral}%` `` (`FV_PTS[0]` 에 `mix(ASOF_M, W_NOW, …)` 결과를 `own/peer/neutral/n` 으로 붙여 둠).
- 툴팁(`fvChart` onMove): `best.noW` 면 `구성 데이터 없음 (2019-09 이전)`; `best.fv2` 가 있으면 `` `구성 ${best.n}종목 · 자기 ${own}% · 빌린 ${peer}% · 중립 ${neutral}%` ``. `short` 관련 줄 삭제.
- `fv-alt-note` 의 QQQ·SPY 문구에 ` 비중은 지금 비중을 과거에도 씁니다 (SOXX 만 시점별 구성).` 추가, `지수 기준 격자` 표현 삭제.

- [ ] **Step 1: 실패하는 테스트**

```js
check("U1 종목 칩은 현재 구성 + 삼성전자만", SFV_LIST.every((s) => s.d.w > 0 || s.d.t === "005930") && !SFV_LIST.some((s) => s.d.t === "QRVO"));
check("U2 FV 에는 과거 종목 포함", FV.some((s) => s.d.t === "QRVO"));
check("U3 오늘 자기/빌린/중립 합 100", Math.abs(FV_PTS[0].own + FV_PTS[0].peer + FV_PTS[0].neutral - 100) < 1e-6);
```

- [ ] **Step 2: 실패 확인** — `node scripts/test_fv.js`
- [ ] **Step 3: 구현 (JS)** — Interfaces 대로.
- [ ] **Step 4: 설명 문구 (HTML `<li>`)** — fair 섹션 `설명 보기`:
  - "모든 시점이 같은 기준" 항목: "비중대로 합칩니다" → "**그 달 SOXX 에 실제로 있던 종목과 비중**(SEC N-PORT 분기 공시, 분기 사이는 주가로 굴림)대로 합칩니다. 오늘은 지금 구성(Zacks, 매주)".
  - "백테스트 기간" 항목: 격자 설명 삭제, "10년 은 SOXX 의 경우 구성 데이터가 있는 2019-09 부터" 로.
  - "목표 PER" 항목: 격자(n × P, RMSE 최소 칸) 설명을 "종목마다 자기 격자에서 고른 기준" 으로 줄이고, 뒤의 "상위 칸들의 차이…" 문장 삭제. "왜 중앙값이 아니라 높은 백분위인가" 항목 삭제.
  - 새 항목: "**지수 PER 비교선**: 그 달 구성의 비중 가중 이익수익률(Σ 비중 × EPS ÷ 주가)의 역수가 지수 forward PER. 목표는 그때까지 알 수 있던 지수 PER 의 중앙값(최소 2년). 파라미터가 거의 없어 종목별 합산과 나란히 보는 기준선입니다. 2022-08 부터."
  - 새 항목: "**자기 기준 · 빌린 기준 · 중립**: 자기 이력으로 n·P 를 정한 종목 비중, 이력이 모자라 나머지 종목 중앙값을 쓴 비중, 계산 불가(현금·선물·상장 폐지 XLNX·MXIM·IPHI·CCMP·적자·이익 바닥) 비중."
  - "한계" 항목: "비중은 과거에도 지금 비중" 삭제. 대신: "과거 비중은 분기말 공시를 주가로 굴린 근사라 분기 중 편입·퇴출은 다음 분기말에 반영. 2019-09 이전은 구성 데이터가 없어 계산하지 않음. 상장 폐지 4종목은 중립(2020~21년 합쳐 최대 약 7%). QQQ·SPY 는 아직 지금 비중. 과거 적정가는 12개월 뒤 실제 EPS 기준이고 그 시점 컨센서스는 2026-11 부터 매달 기록 중."
  - 종목별 섹션 설명의 "SOXX 지수 적정가는 지수에 맞춘 공통 기준(위 격자)을 그대로 씁니다. 공통 기준은 … 42배)." 두 문장 삭제.
- [ ] **Step 5: README** — 첫 글머리를 "목표 PER: 종목마다 직전 n년 forward PER 의 백분위, n·백분위는 종목별 rolling 백테스트(RMSE 최소). 지수 적정가는 그 달 실제 구성·비중(SEC N-PORT, 2019-09~)으로 합산, 오늘은 지금 구성" 으로. 갱신 줄에 "토요일 … N-PORT 구성 · 컨센서스 스냅샷". 명령 블록에 `nport` 추가. (README 의 기존 미커밋 변경이 있으니 `git diff README.md` 를 먼저 보고 그 변경을 보존한 채 편집한다.)
- [ ] **Step 6: 통과 확인** — `python3 scripts/build.py && node scripts/test_fv.js && python3 scripts/test_update.py` → 모두 통과. `docs/index.html` 을 브라우저로 열어(`open docs/index.html`) SOXX 차트가 2019-09 부터 적정가 선, 툴팁에 구성 종목 수, 요약 줄에 자기/빌린/중립, QQQ·SPY 전환이 되는지 본다.
- [ ] **Step 7: 커밋**

```bash
git add docs/index.html README.md scripts/test_fv.js docs/version.json
git commit -m "docs: 시점별 구성 설명 · 과거 종목은 계산에만 · README"
```

---

## 자기 검토 메모

- 스펙 1(N-PORT 데이터) → Task 1·2. 스펙 2(월별 비중) → Task 5. 스펙 3(종목 집합·합산·own/peer/neutral) → Task 4·6. 스펙 4(지수 PER 비교선, 격자 제거, QQQ·SPY 도 같은 모드) → Task 6·7. 스펙 5(10년 = 2019-09~) → Task 6(비중 없는 달 null)·Task 9(라벨). 스펙 6·6b(화면 문구·노출) → Task 9. 스펙 7(빌드) → Task 4. 스펙 8a → Task 8. 스펙 8b → Task 3. 워크플로 → Task 3.
- 이름 일치: `weightsAt`(5) → `rawRatio(tg, ratioOf, W)`·`sumTargets`·`mix`·`BT`(6) → `eyAt`·`IDX_PER`·`idxTarget`(7) → `FWD`·`histRatioFwd`·`BT.fwdErr`(8) → `FV_PTS[0].own/peer/neutral/n`(9). `run_idx.js` 출력 `bt` 는 6 에서 정의하고 7·8 이 필드만 더한다.
