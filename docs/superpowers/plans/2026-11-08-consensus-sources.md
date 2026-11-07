# 컨센서스 EPS 출처 정비 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FY0·FY1 컨센서스를 Zacks 사이트 + Yahoo(잣대 검사 통과 시)의 애널리스트 수 가중 평균으로, FY+2 이후는 Nasdaq 을 재기준화해 쓰고, 최근 발표 종목은 평일에도 컨센서스를 갱신한다.

**Architecture:** 모든 합치기 규칙은 `scripts/forward_per.py` 의 `build_rows` 한 곳에 둔다. `update.py` 는 결과를 저장하고 `last_report`·`basis` 를 더하며 `recent` 모드를 얻는다. `build.py` 는 `unify` 를 없앤다. 페이지는 바꾸지 않는다.

**Tech Stack:** Python 3.12 표준 라이브러리, unittest. 외부 호출 없는 단위 테스트.

**Spec:** `docs/superpowers/specs/2026-11-08-consensus-sources-design.md`

## Global Constraints

- 잣대 검사 허용 오차 0.011, 겹치는 분기 2개 미만이면 보류(통과).
- `recent` 는 `last_report` 로부터 14일 이내.
- 페이지 JS 와 `docs/index.html` 로직은 수정하지 않는다 (build 로 데이터만 바뀜).
- Zacks 요청은 `update.ZUA` 와 같은 Chrome UA 를 쓴다.

## Review Focus

- Zacks 페이지가 403/구조 변경으로 비면 `fetch_zacks_eps` 가 빈 dict 가 아니라 예외를 내고, compute 는 Yahoo 만으로 계속 간다 (Task 1·2 테스트).
- Yahoo 가 잣대 검사에 실패하고 Zacks 도 없으면 Nasdaq 원값 (Task 2 테스트 `test_fallback_nasdaq_raw`).
- Nasdaq 이 FY0·FY1 에만 있고 FY+2 가 없으면 k 는 계산되지만 적용 대상 연도가 없어 아무 영향 없음 (Task 2 테스트에 포함).
- `last_report` 가 없는 옛 파일은 `recent` 대상에서 제외 (Task 3 테스트).
- 음수 EPS 연도의 가중 평균은 그대로 음수 (per 는 None) — 기존 `per` 규칙 유지.

---

### Task 1: Zacks 사이트 연간 컨센서스·분기 실적 파서

**Files:**
- Modify: `scripts/forward_per.py` (fetch 함수들 옆)
- Modify: `scripts/update.py:zacks_quarters` → 파서를 forward_per 로 옮기고 호출
- Create: `scripts/test_forward_per.py`

**Interfaces:**
- Produces: `parse_zacks_estimates(html_text) -> {(end_year, end_month): (eps, n)}` — "Year ago EPS" 가 있는 표에서 Current Year·Next Year 열.
- Produces: `fetch_zacks_eps(opener, ticker) -> dict` (위 파서; 결과가 비면 `ValueError("Zacks 추정 표 없음")`).
- Produces: `parse_zacks_calendar(text) -> [(date, (y, m), eps)]`, `fetch_zacks_quarters(opener, ticker) -> {(y, m): eps}` (최근 분기 실적, 이력 잣대).
- `update.zacks_quarters(ticker)` 는 `parse_zacks_calendar` 를 써서 지금과 같은 `[(월 index, 발표일, eps)]` 를 돌려준다 (동작 불변).

- [ ] **Step 1: 실패하는 테스트**

```python
ZACKS_EST = ('<table><tr><th>Current Qtr <span>(10/2026)</span></th><th>Next Qtr <span>(1/2027)</span></th>'
             '<th>Current Year <span>(1/2027)</span></th><th>Next Year <span>(1/2028)</span></th></tr>'
             '<tr><td>Zacks Consensus Estimate</td><td>2.49</td><td>2.75</td><td>9.30</td><td>15.75</td></tr>'
             '<tr><td># of Estimates</td><td>13</td><td>12</td><td>17</td><td>15</td></tr>'
             '<tr><td>Year ago EPS</td><td>1.30</td><td>1.62</td><td>4.77</td><td>9.30</td></tr></table>')
SALES_TBL = ZACKS_EST.replace("Year ago EPS", "Year ago Sales").replace("9.30", "407.51B")

def test_parse_zacks_estimates_reads_year_columns(self):
    self.assertEqual(fp.parse_zacks_estimates(SALES_TBL + ZACKS_EST), {(2027, 1): (9.30, 17), (2028, 1): (15.75, 15)})

def test_parse_zacks_estimates_empty_raises(self):
    with self.assertRaises(ValueError):
        fp.parse_zacks_estimates("<html>blocked</html>")

CAL = '"earnings_announcements_earnings_table" : [["11/3/26","9/2026","$1.95","$2.09","+$0.14","+7.18%",""],["8/4/26","6/2026","$1.60","$1.66","",""," "],["5/5/26","3/2026","--","--","","",""]] ,'

def test_parse_zacks_calendar(self):
    self.assertEqual(fp.parse_zacks_calendar(CAL), [(datetime.date(2026, 8, 4), (2026, 6), 1.66), (datetime.date(2026, 11, 3), (2026, 9), 2.09)])
```

- [ ] **Step 2: 실행해 실패 확인** — `python3 -m unittest scripts.test_forward_per` → AttributeError
- [ ] **Step 3: 구현** — `parse_zacks_estimates`: `<table>` 블록 중 "Year ago EPS" 포함한 것에서 th 의 `(m/yyyy)` 와 "Zacks Consensus Estimate"·"# of Estimates" 행을 읽는다. 열 순서는 th 순서. `fetch_zacks_eps` 는 Chrome UA 로 받아 파서 호출. `parse_zacks_calendar` 는 `update.zacks_quarters` 의 정규식·변환을 옮긴 것 ("--" 행 제외, 날짜 오름차순). `update.zacks_quarters` 는 그것을 호출해 `(y*12+m, date, eps)` 로 바꾼다.
- [ ] **Step 4: 통과 확인** — 새 테스트 + `python3 -m unittest scripts.test_update` 모두 OK
- [ ] **Step 5: Commit** — `feat: Zacks 사이트 연간 컨센서스·분기 실적 파서`

### Task 2: 합치기 규칙 (잣대 검사 · 가중 평균 · Nasdaq 재기준화)

**Files:**
- Modify: `scripts/forward_per.py:build_rows`, `compute`
- Modify: `scripts/test_forward_per.py`

**Interfaces:**
- Produces: `basis_ok(src_q, ref_q, tol=0.011) -> bool | None` — 겹치는 분기 <2 이면 None.
- `build_rows(sources, quarters, years, growth_override)` 의 `sources` 는 `{"Zacks": {...}, "Yahoo": {...}, "Nasdaq": {...}}` 중 있는 것. 행 필드: `eps=(w, w)`, `n=[...]`, `src={출처: 원값}`, Nasdaq 재기준화 행은 `rebase=k`.
- `compute()` 반환에 `"src_basis": {"Yahoo": True|False|None}` 추가 (`"basis"` 는 성장률 기준 연도로 이미 쓰여 이름을 바꿈). Yahoo 가 False 면 `sources` 에서 빼고 진행. update.py 는 이것을 `st["basis"]` 에 저장.

- [ ] **Step 1: 실패하는 테스트**

```python
def test_basis_ok(self):
    ref = {(2026, 3): 1.0, (2026, 6): 1.2, (2026, 9): 1.5}
    self.assertTrue(fp.basis_ok({(2026, 6): 1.21, (2026, 9): 1.5}, ref))
    self.assertFalse(fp.basis_ok({(2026, 6): 1.0, (2026, 9): 1.5}, ref))
    self.assertIsNone(fp.basis_ok({(2026, 9): 1.5}, ref))

def _rows(self, sources, quarters=None):
    with mock.patch.object(fp.datetime, "date", _FakeDate):  # today = 2026-11-08
        return fp.build_rows(sources, quarters or {}, 4, None)[0]

def test_level_years_weighted_by_analysts(self):
    rows = self._rows({"Zacks": {(2026, 12): (7.61, 21), (2027, 12): (15.46, 21)},
                       "Yahoo": {(2026, 12): (8.09, 43), (2027, 12): (17.64, 49)},
                       "Nasdaq": {(2026, 12): (6.57, 18), (2027, 12): (14.27, 19), (2028, 12): (20.64, 3)}})
    r0, r1, r2 = rows[0], rows[1], rows[2]
    w0 = (7.61 * 21 + 8.09 * 43) / 64
    self.assertAlmostEqual(r0["eps"][0], w0, places=4); self.assertEqual(r0["eps"][0], r0["eps"][1])
    self.assertEqual(r0["src"], {"Zacks": 7.61, "Yahoo": 8.09}); self.assertEqual(sorted(r0["n"]), [21, 43])
    w1 = (15.46 * 21 + 17.64 * 49) / 70
    self.assertAlmostEqual(r2["eps"][0], 20.64 * w1 / 14.27, places=4)   # FY+2 = Nasdaq × k
    self.assertAlmostEqual(r2["rebase"], w1 / 14.27, places=6); self.assertEqual(r2["src"], {"Nasdaq": 20.64}); self.assertEqual(r2["n"], [3])

def test_fallback_nasdaq_raw(self):
    rows = self._rows({"Nasdaq": {(2026, 12): (6.57, 18), (2027, 12): (14.27, 19), (2028, 12): (20.64, 3)}})
    self.assertEqual(rows[0]["eps"], (6.57, 6.57)); self.assertEqual(rows[2]["eps"], (20.64, 20.64)); self.assertNotIn("rebase", rows[2])

def test_nasdaq_without_overlap_keeps_raw(self):
    rows = self._rows({"Yahoo": {(2026, 12): (8.0, 40)}, "Nasdaq": {(2027, 12): (14.0, 10)}})
    self.assertEqual(rows[0]["eps"], (8.0, 8.0)); self.assertEqual(rows[1]["eps"], (14.0, 14.0))

def test_growth_uses_rebased_path(self):
    rows = self._rows({"Yahoo": {(2026, 12): (8.0, 40), (2027, 12): (16.0, 40)},
                       "Nasdaq": {(2026, 12): (6.0, 10), (2027, 12): (12.0, 10), (2028, 12): (15.0, 10)}})
    self.assertAlmostEqual(rows[2]["eps"][0], 20.0, places=6)        # 15 × (16/12)
    self.assertAlmostEqual(rows[3]["eps"][0], 25.0, places=6)        # 추정: 20 × (20/16)
```

`_FakeDate`: `datetime.date` 를 상속해 `today()` 가 `date(2026, 11, 8)` 를 돌려주는 클래스.

- [ ] **Step 2: 실행해 실패 확인**
- [ ] **Step 3: 구현** — `build_rows`: 수준 출처 = `sources` 중 "Nasdaq" 외 전부. 연도별로 수준 출처가 있으면 n 가중 평균(n 이 None 인 출처는 가중치 1), 없고 Nasdaq 만 있으면 Nasdaq×k. k 는 수준 출처와 Nasdaq 이 함께 있는 마지막 연도에서 계산, 없으면 1. 수준 출처가 전혀 없으면 k=1 로 Nasdaq 원값(`rebase` 키 없음). `compute`: fetchers = Zacks·Yahoo·Nasdaq (한국 종목은 FnGuide·Yahoo), quarters = Zacks·Yahoo; `basis["Yahoo"] = basis_ok(quarters["Yahoo"], quarters["Zacks"])` 가 False 면 `sources.pop("Yahoo")`. Zacks 분기가 없으면 검사 보류.
- [ ] **Step 4: 통과 확인** — `python3 -m unittest scripts.test_forward_per`; 실 조회 `python3 scripts/forward_per.py AMD INTC ASML --json | head -c 1500` 에서 AMD FY2026 ≈ 7.9, ASML basis Yahoo False 확인
- [ ] **Step 5: Commit** — `feat: 컨센서스 출처 합치기 — 잣대 검사 · 애널리스트 수 가중 · Nasdaq 재기준화`

### Task 3: update.py — last_report · basis 저장, recent 모드, unify 제거, 워크플로

**Files:**
- Modify: `scripts/update.py` (`consensus`, `update_full_one`, 새 `update_recent_one`, `is_recent`, `main`, docstring)
- Modify: `scripts/build.py` (`unify` 삭제, 호출부는 `d` 그대로)
- Modify: `.github/workflows/update.yml`
- Modify: `scripts/test_update.py`, `README.md`

**Interfaces:**
- Produces: `is_recent(st, today, days=14) -> bool` — `st.get("last_report")` ISO 문자열 기준.
- Produces: `update_recent_one(t) -> str | None` — `is_recent` 면 `consensus(st)` + `reprice_fwd` + save.
- `consensus(st)` 가 `st["basis"] = res["basis"]` 저장; `update_full_one` 이 `st["last_report"] = max(발표일).isoformat()` 저장 (분기가 없으면 키 제거).
- `main`: `recent` 모드 = `run(update_recent_one, args or all_tickers(), 6)`.

- [ ] **Step 1: 실패하는 테스트**

```python
def test_is_recent(self):
    self.assertTrue(update.is_recent({"last_report": "2026-10-29"}, dt.date(2026, 11, 8)))
    self.assertFalse(update.is_recent({"last_report": "2026-10-24"}, dt.date(2026, 11, 8)))
    self.assertFalse(update.is_recent({}, dt.date(2026, 11, 8)))
```

- [ ] **Step 2: 실패 확인** → **Step 3: 구현** (위 인터페이스대로; 워크플로에 `if: github.event.schedule == '30 22 * * 1-5'` 단계 `python3 scripts/update.py recent` 를 주가 단계 뒤에 추가; README 모드 목록에 `recent` 추가; `build.py` 에서 `unify` 와 `math` import 제거)
- [ ] **Step 4: 통과 확인** — `python3 -m unittest scripts.test_update scripts.test_forward_per`
- [ ] **Step 5: Commit** — `feat: recent 모드 · last_report/basis 저장 · unify 제거`

### Task 4: 데이터 재수집 · 빌드 · 검증 · 배포

- [ ] **Step 1:** `rm data/consensus/2026-11.json` 뒤 `python3 scripts/update.py full` (전 종목; 실패 목록 확인, Zacks 403 이 대량이면 중단하고 보고)
- [ ] **Step 2:** `python3 scripts/update.py prices` → `python3 scripts/build.py` → `node scripts/test_fv.js` 통과
- [ ] **Step 3:** 검증 — AMD·INTC·ASML·NVDA 의 fwd 확인(AMD 2026 ≈ 7.9, ASML basis Yahoo false), SOXX 오늘 적정가 변화(예상 +4~5%), `basis.Yahoo == false` 종목 수 출력
- [ ] **Step 4:** Commit `data: 컨센서스 새 출처로 전체 갱신 · 2026-11 스냅샷 재생성`, `git push origin HEAD:main`, Pages 배포 확인
