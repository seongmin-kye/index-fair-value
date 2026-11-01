// 적정가 계산 회귀 테스트: 페이지 계산 코드를 node 로 돌려 알려진 오염 사례가 다시 생기지 않는지 확인
// node scripts/test_fv.js [docs/index.html]
const fs = require("fs"), path = require("path");
const PAGE = process.argv[2] || path.join(__dirname, "..", "docs", "index.html");
let js = [...fs.readFileSync(PAGE, "utf8").matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]).join("\n");
js = js.replace(/buildSeg\(\);[\s\S]*$/, "");
const stub = `const document = { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], addEventListener(){}, documentElement: { dataset: {} } };
const window = { addEventListener(){}, matchMedia: () => ({ matches: false, addEventListener(){} }) };
const localStorage = { getItem: () => null, setItem(){} };`;
const tests = `
const fails = [];
const check = (name, ok, info) => { console.log((ok ? "ok   " : "FAIL ") + name + (info != null ? "  [" + info + "]" : "")); if (!ok) fails.push(name); };
const find = (t) => SFV_LIST.concat(FV_M7).find((x) => x.d.t === t);
const maxJump = (hist) => { let m = 0; for (let i = 1; i < hist.length; i++) if (hist[i].pe && hist[i - 1].pe) m = Math.max(m, Math.abs(Math.log(hist[i].pe / hist[i - 1].pe))); return Math.exp(m); };

// B1: 이익 바닥(12개월 뒤 EPS 가 직전 3년 TTM 고점의 절반 미만)인 달은 forward PER 관측에서 빠진다
const mchp = find("MCHP");
check("B1 MCHP 2024-05 (12개월 뒤 EPS 1.30 vs 고점 6.46) fpe 제외", mchp.fpe[monthIdx("2024-05")] == null);
check("B1 MCHP 2022-06 (정상 구간) fpe 유지", mchp.fpe[monthIdx("2022-06")] != null);
const mc = sfvCompute(mchp);
check("B1 MCHP 목표 PER 지금 < 40", mc.now.pe < 40, mc.now.pe.toFixed(1) + " " + mc.now.rule);
check("B1 MCHP 목표 PER 월간 변화 2배 미만", maxJump(mc.hist) < 2, maxJump(mc.hist).toFixed(2));
check("B1 MCHP 이익 바닥 달(2024-05) 적정가 없음", mc.hist.find((h) => h.label === "2024-05").fv == null);
check("B1 이익 바닥 달이 종목 격자 오차에 안 들어감", !(mchp.own.best && mchp.own.best.err > 0.5), mchp.own.best && mchp.own.best.err.toFixed(2));
if (find("TTWO")) check("B1 TTWO 목표 PER 지금 < 50", sfvCompute(find("TTWO")).now.pe < 50);

// B2: 이력이 짧은 종목은 나머지 종목 중앙값 대신 자기 관측 중앙값 (9개월 이상)
const arm = sfvCompute(find("ARM"));
check("B2 ARM 자기 forward PER 중앙값 사용 (50~100배)", arm.now.pe > 50 && arm.now.pe < 100, arm.now.pe.toFixed(1) + " " + arm.now.rule);
check("B2 ARM 규칙 문구에 '이력' 표시", /이력/.test(arm.now.rule), arm.now.rule);
const alab = sfvCompute(find("ALAB"));
const alabObs = Object.entries(find("ALAB").fpe).filter(([i]) => +i >= ASOF_M - 47 && +i <= ASOF_M - 12).map(([, v]) => v);
check("B2 ALAB 자기 관측 중앙값 (직전 3년 관측 9개월 이상)", /이력 짧음/.test(alab.now.rule) && alabObs.length >= 9 && Math.abs(alab.now.pe - median(alabObs)) < 1e-9, alab.now.pe.toFixed(1) + " " + alab.now.rule);
check("B2 CBRS (관측 0) 은 나머지 종목 중앙값", /나머지/.test(sfvCompute(find("CBRS")).now.rule));
check("B2 지수 합산(TG_SUM_NOW)도 ARM 에 자기 중앙값", TG_SUM_NOW.get(find("ARM")) > 50, TG_SUM_NOW.get(find("ARM")).toFixed(1));

// B3: 격자(창 줄이기)와 실제 목표 PER 이 같은 규칙 → TSLA 2025-10 절벽(95→28) 없음
const tsla = m7StockCompute(find("TSLA"));
check("B3 TSLA 목표 PER 월간 변화 2배 미만", maxJump(tsla.hist) < 2, maxJump(tsla.hist).toFixed(2));
check("B3 TSLA 지금 목표 PER 가 M7 중앙값이 아님", !/나머지/.test(tsla.rule), tsla.pe.toFixed(1) + " " + tsla.rule);

// B4: EPS 경로 성장률은 애널리스트 3명 이하(thin) 연도를 기준으로 쓰지 않는다
check("B4 MCHP 2029 EPS > 2028 (thin 2028 을 성장률 기준에서 제외)", mchp.path[2029] > mchp.path[2028], JSON.stringify([mchp.path[2028], mchp.path[2029]]));

// B5: 두 출처 EPS 가 크게 다르면 하나로 통일 (SOXX · M7 데이터에도)
const tslaD = find("TSLA").d;
check("B5 TSLA 2026 EPS 범위 통일 (0.67 vs 1.74 → 하나)", tslaD.fwd[0].eps[0] === tslaD.fwd[0].eps[1], JSON.stringify(tslaD.fwd[0].eps));
check("B5 TSLA EPS 경로가 2028 에 꺾이지 않음", find("TSLA").path[2028] > find("TSLA").path[2027], JSON.stringify(find("TSLA").path));

// W: 시점별 비중
const W1 = weightsAt(monthIdx("2019-06")), W2 = weightsAt(ASOF_M), W3 = weightsAt(monthIdx("2021-11")), W4 = weightsAt(monthIdx("2021-09"));
check("W1 2019-09 이전은 비중 없음", W1 === null);
check("W2 오늘은 Zacks 현재 비중 (합 99~100)", W2 && W2.src === "now" && Math.abs([...W2.w.values()].reduce((a, b) => a + b, 0) + W2.cash - 100) < 1e-6 && W2.w.get(find("ALAB")) > 2);
const sum3 = [...W3.w.values()].reduce((a, b) => a + b, 0) + W3.neutral;
check("W3 2021-11 비중: 굴린 뒤에도 합 = 분기 합, NaN 없음, XLNX 는 중립에", W3.src === "nport" && isFinite(sum3) && Math.abs(sum3 - ([...W4.w.values()].reduce((a, b) => a + b, 0) + W4.neutral)) < 1e-6 && W3.neutral > 3 && !W3.w.has(find("XLNX") || {}), sum3.toFixed(2) + " neutral " + W3.neutral.toFixed(2));
check("W4 2021-09 ALAB 비중 0, NVDA 7~8", !W4.w.get(find("ALAB")) && W4.w.get(find("NVDA")) > 7 && W4.w.get(find("NVDA")) < 8.5);
const W10 = weightsAt(monthIdx("2021-10")), pxM = (t, k) => find(t).byM[monthIdx(k)][3];
const relW = (W10.w.get(find("NVDA")) / W4.w.get(find("NVDA"))) / (W10.w.get(find("AMD")) / W4.w.get(find("AMD")));
const relP = (pxM("NVDA", "2021-10") / pxM("NVDA", "2021-09")) / (pxM("AMD", "2021-10") / pxM("AMD", "2021-09"));
check("W4 2021-10 NVDA·AMD 비중 비가 10월 주가 비만큼 움직임", Math.abs(relW - relP) < 1e-9, relW.toFixed(6) + " vs " + relP.toFixed(6));
const h1909 = FV_HIST.find((h) => h.label === "2019-08"), h2109 = FV_HIST.find((h) => h.label === "2021-09");
check("W5 2019-08 적정가 없음(noW)", h1909.fv2 == null && h1909.noW);
check("W6 2021-09 적정가 있음, own+peer+neutral = 100", h2109.fv2 > 0 && Math.abs(h2109.own + h2109.peer + h2109.neutral - 100) < 1e-6, [h2109.own, h2109.peer, h2109.neutral].map((v) => v.toFixed(1)).join("/"));
check("W6 2021-09 XLNX 중립 ≥ 3%p 포함", h2109.neutral >= 3);
check("W7 오늘 적정가는 현재 비중 (ALAB 기여 있음)", TG_SUM_NOW.has(find("ALAB")) && FV_PTS[0].fv2 > 0);
check("W8 BT 는 최근 5년(ASOF_M-71 ~ ASOF_M-12), 61개월 이하, sumErr 0.05~0.5", BT.T0 === ASOF_M - 11 - 12 * GRID_SPAN && BT.n <= 61 && BT.sumErr > 0.05 && BT.sumErr < 0.5, BT.n + " " + BT.sumErr.toFixed(3));
check("W9 격자 전역 제거", typeof GRID === "undefined" && typeof targetsAt === "undefined");
check("I1 IDX_PER 2021-09 는 15~60", IDX_PER[monthIdx("2021-09")] > 15 && IDX_PER[monthIdx("2021-09")] < 60, IDX_PER[monthIdx("2021-09")]);
check("I1 비교선 시작 2022-08 이후, 그 전 null", FV_HIST.find((h) => h.fvI).label >= "2022-08" && FV_HIST.find((h) => h.label === "2022-06").fvI == null);
check("I2 비교선에 Infinity/NaN 없음", FV_HIST.every((h) => h.fvI == null || isFinite(h.fvI)) && FV_PTS.every((p) => p.fvI == null || isFinite(p.fvI)));
check("I2 계산 가능 비중 절반 미만이면 null", eyAt(monthIdx("2021-09"), { w: new Map([[find("NVDA"), 10]]), neutral: 0, cash: 90, src: "nport" }) === null);
check("I3 BT 비교 달 수 30~45, idxErr 유한", BT.cmpN >= 30 && BT.cmpN <= 45 && isFinite(BT.idxErr) && isFinite(BT.sumErrCmp), BT.cmpN + " " + BT.idxErr.toFixed(3));
check("I4 기본 basis = sum", fvView.basis === "sum");

console.log(fails.length ? "\\n" + fails.length + " failed" : "\\nall passed");
process.exit(fails.length ? 1 : 0);
`;
new Function("require", "process", stub + js + tests)(require, process);
