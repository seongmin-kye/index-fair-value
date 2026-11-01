// 페이지 계산 코드를 그대로 돌려 지수 하나(QQQ·SPY · SOXX 10년)의 rolling 적정가(종목별 기준 합산 · 지수 PER 비교선) · 백테스트 · 연말 적정가를 뽑는다
// node scripts/run_idx.js PAGE DATA_JSON INDEX_HIST_JSON OUT_JSON [SPAN]   (DATA_JSON·INDEX_HIST_JSON 을 - 로 주면 페이지의 SOXX 그대로, SPAN = 백테스트 기간(년))
const fs = require("fs");
const [PAGE, DATA_F, HIST_F, OUT_F, SPAN] = process.argv.slice(2);
let js = [...fs.readFileSync(PAGE, "utf8").matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]).join("\n");
const rep = (re, s) => { if (!re.test(js)) throw new Error("no match " + re); js = js.replace(re, () => s); };
if (DATA_F !== "-") {
  rep(/^const DATA = .*$/m, `const DATA = ${fs.readFileSync(DATA_F, "utf8")};`);
  rep(/^const SOXX_W_HIST = .*$/m, `const SOXX_W_HIST = {};`);  // QQQ·SPY 는 고정 비중
}
if (HIST_F !== "-") {
  const hist = JSON.parse(fs.readFileSync(HIST_F, "utf8"));
  rep(/^const SOXX_HIST = .*$/m, `const SOXX_HIST = ${JSON.stringify(hist)};`);
  rep(/^let SOXX_PRICE = .*$/m, `let SOXX_PRICE = ${hist[hist.length - 1][1]};`);
}
if (SPAN) rep(/^const GRID_SPAN = \d+;/m, `const GRID_SPAN = ${+SPAN};`);
js = js.replace(/buildSeg\(\);[\s\S]*$/, "");  // 렌더 시작 전까지만
const stub = `const document = { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], addEventListener(){}, documentElement: { dataset: {} } };
const window = { addEventListener(){}, matchMedia: () => ({ matches: false, addEventListener(){} }) };
const localStorage = { getItem: () => null, setItem(){} };`;
const out = `
const r1 = (v, k = 2) => (v == null || !isFinite(v) ? null : +v.toFixed(k));
const ws = [...W_NOW.w].filter(([, w]) => w > 0), wOf = (f) => ws.filter(([s]) => f(s)).reduce((a, [, w]) => a + w, 0);
const res = {
  price: SOXX_PRICE, wsum: r1(wOf(() => true), 1), asof: ymd(ASOF), x5: FV_X5,
  stocks: ws.length, cash: r1(W_NOW.cash, 1),
  cover: r1(wOf((s) => s.path && s.eN && s.px), 1),
  covHist: r1(wOf((s) => Object.keys(s.fpe).length >= 24), 1),
  bt: BT,
  hist: FV_HIST.map((h) => [h.x, h.px, r1(h.fvI), r1(h.fv2), r1(h.own), r1(h.peer), r1(h.neutral), h.n]),
  pts: FV_PTS.map((p) => [p.y, r1(p.fvI), r1(p.fv2)]),
};
require("fs").writeFileSync(${JSON.stringify(OUT_F)}, JSON.stringify(res));
console.log(${JSON.stringify(OUT_F)}, res.stocks + " stocks", BT.n + " months", "RMSE " + (BT.sumErr * 100).toFixed(1) + "%", "today " + res.pts[0][2]);
`;
new Function("require", stub + js + out)(require);
