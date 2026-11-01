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
