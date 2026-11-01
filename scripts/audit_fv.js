// 규칙을 바꿀 때 전 종목 점검: 페이지 계산 코드를 node 로 돌려 종목별 목표 PER·적정가의 이상 징후를 모아 보여준다.
// node scripts/audit_fv.js [docs/index.html] [DATA_JSON|-]   (DATA_JSON = QQQ·SPY 구성 종목 데이터, build.index_data 결과)
// 점검 항목: (1) 자기 기준을 못 정한 종목 (2년 이상 이력인데도) (2) 적정가/주가 극단값 (3) 인접 달 목표 PER 1.5배 초과 변화
//           (4) 종목 격자 RMSE 0.5 초과 (5) 곱할 EPS ≤ 0 (6) 직전 3년 창 관측 부족  — 각 항목의 종목 수와 목록. exit 1 = 1·3 에 걸린 종목 있음
const fs = require("fs"), path = require("path");
const PAGE = process.argv[2] || path.join(__dirname, "..", "docs", "index.html"), DATA_F = process.argv[3] || "-";
let js = [...fs.readFileSync(PAGE, "utf8").matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]).join("\n");
if (DATA_F !== "-") js = js.replace(/^const DATA = .*$/m, () => `const DATA = ${fs.readFileSync(DATA_F, "utf8")};`).replace(/^const SOXX_W_HIST = .*$/m, "const SOXX_W_HIST = {};");  // QQQ·SPY 는 고정 비중 (run_idx.js 와 같음)
js = js.replace(/buildSeg\(\);[\s\S]*$/, "");
const stub = `const document = { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], addEventListener(){}, documentElement: { dataset: {} } };
const window = { addEventListener(){}, matchMedia: () => ({ matches: false, addEventListener(){} }) };
const localStorage = { getItem: () => null, setItem(){} };`;
const audit = `
const out = { noRule: [], extreme: [], jump: [], badGrid: [], noEps: [], thinWin: [], peerIdx: [] };
const all = [...new Set(FV.concat(FV_X, FV_M7))];  // 과거 구성 종목(지금 비중 0)도 지수 합산에 들어가므로 같이 점검
for (const s of all) {
  const t = s.d.t, m7 = FV_M7.includes(s), c = m7 ? m7StockCompute(s) : sfvCompute(s), now = m7 ? { pe: c.pe, rule: c.rule } : c.now;
  const months = s.d.series.length, mem = MEMORY.has(t);
  if (!mem && !now.pe && months >= 36) out.noRule.push(t + "(" + months + "개월)");
  const fv = c.pts[0].fv, r = fv && s.px ? fv / s.px : null;
  if (r != null && (r > 2.5 || r < 0.33)) out.extreme.push(t + "(" + r.toFixed(2) + ", PER " + now.pe.toFixed(1) + ")");
  const h = c.hist.filter((x) => x.pe);
  if (!mem) for (let i = 1; i < h.length; i++) { if (h[i].x - h[i - 1].x !== 1) continue; const q = h[i].pe / h[i - 1].pe; if (q > 1.5 || q < 1 / 1.5) { out.jump.push(t + "(" + h[i - 1].label + " " + h[i - 1].pe.toFixed(1) + "→" + h[i].pe.toFixed(1) + ")"); break; } }
  if (!mem && s.own.best && s.own.best.err > 0.5) out.badGrid.push(t + "(" + (s.own.best.err * 100).toFixed(0) + "%)");
  if (!(c.pts[0].eps > 0) && s.eN != null) out.noEps.push(t);
  const obs = Object.keys(s.fpe).filter((i) => +i >= ASOF_M - 47 && +i <= ASOF_M - 12).length;
  if (!mem && months >= 60 && obs < 27) out.thinWin.push(t + "(" + obs + ")");
  if (!m7 && FV.includes(s) && !mem && !(now.pe > 0) && SUM_NOW.kind.get(s) === "peer") out.peerIdx.push(t + "(지수 " + TG_SUM_NOW.get(s).toFixed(1) + ")");
}
const label = { noRule: "자기 기준 없음 (이력 3년 이상)", extreme: "적정가/주가 >2.5 또는 <0.33", jump: "인접 달 목표 PER 1.5배 초과 변화 (메모리 제외)", badGrid: "종목 격자 RMSE > 50%", noEps: "곱할 EPS ≤ 0 (적자)", thinWin: "직전 3년 창 관측 < 27 (이력 5년 이상)", peerIdx: "지수에선 나머지 종목 중앙값으로 들어감" };
console.log("종목 " + all.length + " · 오늘 " + FV_PTS[0].fv2.toFixed(0) + " (" + pct(FV_PTS[0].fv2 / SOXX_PRICE - 1) + ") · 종목별 합산 RMSE " + (BT.sumErr * 100).toFixed(1) + "%" + (FV_PTS[0].fvI ? " · 지수 PER 비교선 " + FV_PTS[0].fvI.toFixed(0) : ""));
for (const k of Object.keys(out)) console.log("  " + label[k].padEnd(28) + out[k].length + (out[k].length ? "  " + out[k].slice(0, 25).join(" ") + (out[k].length > 25 ? " …" : "") : ""));
process.exit(out.noRule.length || out.jump.length ? 1 : 0);
`;
new Function("require", "process", stub + js + audit)(require, process);
