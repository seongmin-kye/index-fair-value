// 페이지 계산 코드를 그대로 돌려 지수 하나(QQQ·SPY)의 rolling 적정가 · 격자 · 연말 적정가를 뽑는다
// node scripts/run_idx.js PAGE DATA_JSON INDEX_HIST_JSON OUT_JSON
const fs = require("fs");
const [PAGE, DATA_F, HIST_F, OUT_F] = process.argv.slice(2);
let js = [...fs.readFileSync(PAGE, "utf8").matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]).join("\n");
const hist = JSON.parse(fs.readFileSync(HIST_F, "utf8")), price = hist[hist.length - 1][1];
const rep = (re, s) => { if (!re.test(js)) throw new Error("no match " + re); js = js.replace(re, () => s); };
rep(/^const DATA = .*$/m, `const DATA = ${fs.readFileSync(DATA_F, "utf8")};`);
rep(/^const SOXX_HIST = .*$/m, `const SOXX_HIST = ${JSON.stringify(hist)};`);
rep(/^let SOXX_PRICE = .*$/m, `let SOXX_PRICE = ${price};`);
js = js.replace(/buildSeg\(\);[\s\S]*$/, "");  // 렌더 시작 전까지만
const stub = `const document = { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], addEventListener(){}, documentElement: { dataset: {} } };
const window = { addEventListener(){}, matchMedia: () => ({ matches: false, addEventListener(){} }) };
const localStorage = { getItem: () => null, setItem(){} };`;
const out = `
const r1 = (v, k = 2) => (v == null || !isFinite(v) ? null : +v.toFixed(k));
const res = {
  price: SOXX_PRICE, wsum: r1(DATA.reduce((a, d) => a + d.w, 0), 1), asof: ymd(ASOF), n: FV_N, p: FV_P, err: GRID.best.err, sumErr: SUM_ERR, x5: FV_X5,
  stocks: FV.length, cash: r1(CASH_W, 1),
  cover: r1(FV.filter((s) => s.path && s.eN && s.px).reduce((a, s) => a + s.w, 0), 1),
  covHist: r1(FV.filter((s) => Object.keys(s.fpe).length >= 24).reduce((a, s) => a + s.w, 0), 1),
  Ts: [GRID.Ts[0], GRID.Ts[GRID.Ts.length - 1], GRID.Ts.length], cells: GRID.cells.map((c) => [c.n, c.p, r1(c.err, 4), r1(c.rho, 3)]),
  hist: FV_HIST.map((h) => [h.x, h.px, r1(h.fvI), r1(h.fv2), h.short]),
  pts: FV_PTS.map((p) => [p.y, r1(p.fvI), r1(p.fv2)]),
};
require("fs").writeFileSync(${JSON.stringify(OUT_F)}, JSON.stringify(res));
console.log(${JSON.stringify(OUT_F)}, FV.length + " stocks", FV_N + "y " + statLabel(FV_P), "RMSE " + (GRID.best.err * 100).toFixed(1) + "%", "today " + res.pts[0][1]);
`;
new Function("require", stub + js + out)(require);
