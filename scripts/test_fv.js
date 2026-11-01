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

// B1: 이익 바닥 달은 정상화 EPS(max(12개월 뒤 EPS, 앞뒤 3년 TTM 평균))로 재서 배수가 부풀지 않고, 적정가도 꺼지지 않는다
const mchp = find("MCHP");
check("B1 MCHP 2024-05 (12개월 뒤 EPS 1.30 vs 3년 평균 ~4.5) forward PER 30배 미만", mchp.fpe[monthIdx("2024-05")] != null && mchp.fpe[monthIdx("2024-05")] < 30, mchp.fpe[monthIdx("2024-05")] && mchp.fpe[monthIdx("2024-05")].toFixed(1));
check("B1 MCHP 2022-06 (정상 구간) forward PER 그대로", Math.abs(mchp.fpe[monthIdx("2022-06")] - mchp.byM[monthIdx("2022-06")][3] / epsAt(mchp, monthIdx("2022-06") + 12)) < 1e-9);
const mc = sfvCompute(mchp);
check("B1 MCHP 목표 PER 지금 < 40", mc.now.pe < 40, mc.now.pe.toFixed(1) + " " + mc.now.rule);
check("B1 MCHP 목표 PER 월간 변화 2배 미만", maxJump(mc.hist) < 2, maxJump(mc.hist).toFixed(2));
const m2405 = mc.hist.find((h) => h.label === "2024-05");
check("B1 MCHP 이익 바닥 달(2024-05) 적정가가 주가의 절반 이상", m2405.fv > 0.5 * m2405.px, m2405.fv && m2405.fv.toFixed(0) + " vs " + m2405.px);
check("B1 MCHP 종목 격자 오차 < 0.5", mchp.own.best && mchp.own.best.err < 0.5, mchp.own.best && mchp.own.best.err.toFixed(2));
if (find("TTWO")) check("B1 TTWO 목표 PER 지금 < 50", sfvCompute(find("TTWO")).now.pe < 50);
// B1b: 이력이 긴 종목은 이익 바닥을 지나도 자기 기준이 끊기지 않는다 (INTC 2022~25 적자·바닥)
const intc = sfvCompute(find("INTC"));
check("B1b INTC 자기 기준으로 적정가 계산", intc.now.pe > 0 && /^자기/.test(intc.now.rule) && intc.pts[0].fv > 0, (intc.now.pe || 0).toFixed(1) + " " + intc.now.rule + " fv " + (intc.pts[0].fv || 0).toFixed(0));
const longHist = SFV_LIST.filter((s) => !MEMORY.has(s.d.t) && s.d.series.length >= 120);
const gaps = longHist.filter((s) => Object.keys(s.fpe).filter((i) => +i >= ASOF_M - 47 && +i <= ASOF_M - 12).length < 27).map((s) => s.d.t);
check("B1b 10년 이력 종목은 직전 3년 창에 관측 27개월 이상", gaps.length === 0, gaps.join(","));

// B2: 이력이 짧은 종목은 나머지 종목 중앙값 대신 자기 관측 중앙값 (9개월 이상)
const arm = sfvCompute(find("ARM"));
check("B2 ARM 자기 forward PER 중앙값 사용 (50~100배)", arm.now.pe > 50 && arm.now.pe < 100, arm.now.pe.toFixed(1) + " " + arm.now.rule);
check("B2 ARM 규칙 문구에 이력 24개월 미만 표시", /이력 24개월 미만/.test(arm.now.rule), arm.now.rule);
const alab = sfvCompute(find("ALAB"));
const alabObs = Object.entries(find("ALAB").fpe).filter(([i]) => +i >= ASOF_M - 47 && +i <= ASOF_M - 12).map(([, v]) => v);
check("B2 ALAB 격자 없음 → 자기 직전 3년 중앙값 (관측 9개월 이상)", /격자 없음/.test(alab.now.rule) && alabObs.length >= 9 && Math.abs(alab.now.pe - median(alabObs)) < 1e-9, alab.now.pe.toFixed(1) + " " + alab.now.rule);
// B7: 창 규칙이 하나 — 관측 9개월부터 계산, 27개월 미만이면 백분위를 중앙값 쪽으로 당김 (창 줄이기 없음)
const amd = find("AMD"), rAmd = peAt(amd, ASOF_M, 5, 0.9);
check("B7 관측 27개월 이상이면 백분위(띠 평균) 그대로", rAmd && rAmd.n >= 27 && Math.abs(rAmd.pe - bandQuantile(Object.entries(amd.fpe).filter(([i]) => +i >= ASOF_M - 71 && +i <= ASOF_M - 12).map(([, v]) => v), 0.9)) < 1e-9);
const fake = { fpe: Object.fromEntries(Array.from({ length: 9 }, (_, k) => [ASOF_M - 12 - k, 10 + k])) };
check("B7 관측 9개월이면 어떤 백분위든 중앙값(띠)", Math.abs(peAt(fake, ASOF_M, 3, 0.9).pe - peAt(fake, ASOF_M, 3, 0.2).pe) < 1e-9 && Math.abs(peAt(fake, ASOF_M, 3, 0.9).pe - 14) < 1e-9, peAt(fake, ASOF_M, 3, 0.9).pe);
check("B7 관측 8개월이면 null", peAt({ fpe: Object.fromEntries(Array.from({ length: 8 }, (_, k) => [ASOF_M - 12 - k, 10 + k])) }, ASOF_M, 3, 0.5) == null);
check("B2 CBRS (관측 0) 은 계산 안 함", sfvCompute(find("CBRS")).now.pe == null && /계산 안 함/.test(sfvCompute(find("CBRS")).now.rule));
// B6: 종목별 목표 PER 이 달 사이에 1.5배 넘게 튀지 않는다 (나머지 종목 중앙값 ↔ 자기 기준 전환이 없어야 함). 메모리는 규칙 전환이 있어 제외
for (const s of SFV_LIST.concat(FV_M7)) {
  if (MEMORY.has(s.d.t)) continue;
  const c = FV_M7.includes(s) ? m7StockCompute(s) : sfvCompute(s), h = c.hist.filter((x) => x.pe);
  let bad = null;
  for (let i = 1; i < h.length; i++) { if (h[i].x - h[i - 1].x !== 1) continue; const r = h[i].pe / h[i - 1].pe; if (r > 1.5 || r < 1 / 1.5) bad = h[i - 1].label + " " + h[i - 1].pe.toFixed(1) + "→" + h[i].pe.toFixed(1); }  // 계산 안 한 달을 사이에 둔 비교는 제외 (바닥 전후는 다른 국면)
  if (bad || s.d.t === "ARM" || s.d.t === "CRDO") check("B6 " + s.d.t + " 목표 PER 월간 변화 1.5배 미만", !bad, bad);
}
check("B2 지수 기준(targetsAt)도 ARM 에 자기 중앙값", TG_NOW.get(find("ARM")) > 50, TG_NOW.get(find("ARM")).toFixed(1));

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

console.log(fails.length ? "\\n" + fails.length + " failed" : "\\nall passed");
process.exit(fails.length ? 1 : 0);
`;
new Function("require", "process", stub + js + tests)(require, process);
