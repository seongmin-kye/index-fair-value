"""data/ → docs/index.html.

페이지의 데이터 줄(DATA · M7_DATA · EXTRA · SOXX_HIST · SOXL_HIST · SOXX_PRICE · IDX_ALT)과 기준일 문구만 바꾸고,
QQQ·SPY 는 같은 페이지 계산 코드를 node 로 돌린 결과를 IDX_ALT 로 넣는다.
"""
import datetime as dt
import json
import math
import os
import re
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
PAGE = os.path.join(ROOT, "docs", "index.html")
CAP = 100
M7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA"]  # NVDA 는 SOXX 데이터에 있음
EXTRA = ["005930"]


def load(*p):
    return json.load(open(os.path.join(DATA, *p), encoding="utf-8"))


def stock(t):
    p = os.path.join(DATA, "stocks", f"{t}.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def soxx_entry(t, name, w):
    d = stock(t)
    if not d:
        return None
    pers = [r[1] for r in d["series"]]
    valid = [p for p in pers if p is not None and p <= CAP]
    s = d["series"]
    return {**{k: v for k, v in d.items() if k != "hist_src"}, "name": d.get("name") or name, "w": w,
            "avg": round(sum(valid) / len(valid), 1) if len(valid) >= 12 else None,
            "n_valid": len(valid), "n_neg": sum(1 for p in pers if p is None),
            "n_over": sum(1 for p in pers if p is not None and p > CAP),
            "last": s[-1][1] if s else None, "last_date": s[-1][0] if s else None}


def unify(d):
    """두 출처(Zacks 조정 · Yahoo GAAP/현지통화) 추정이 크게 다르면 과거 이력(Zacks 조정 EPS)에 가까운 쪽 하나로."""
    ttm = next((x[2] for x in reversed(d["series"]) if x[2]), None)
    c0 = next((c for c in d["fwd"] if c.get("eps") and c["eps"][0] > 0), None)
    if ttm and ttm > 0 and c0 and c0["eps"][1] / c0["eps"][0] > 1.5:
        k = min((0, 1), key=lambda j: abs(math.log(c0["eps"][j] / ttm)))
        for c in d["fwd"]:
            if c.get("eps"):
                c["eps"] = [c["eps"][k]] * 2
    return d


def index_data(k, known):
    out = []
    for t, name, w in load("holdings", f"{k}.json"):
        if not t or w <= 0:
            continue
        if t in known:
            out.append({**known[t], "w": w})
            continue
        d = stock(t)
        if d:
            d.pop("hist_src", None)
            out.append({**unify(d), "w": w, "name": d.get("name") or name})
    return out


def line(s, name, value):
    pat = re.compile(rf"^(const|let) {name} = .*$", re.M)
    assert pat.search(s), name
    return pat.sub(lambda m: f"{m.group(1)} {name} = {value}", s, count=1)


def main():
    s = open(PAGE, encoding="utf-8").read()
    soxx = [e for e in (soxx_entry(t, n, w) for t, n, w in load("holdings", "SOXX.json") if t and w > 0) if e]
    m7 = [soxx_entry(t, t, 0) for t in M7]
    extra = [soxx_entry(t, t, 0) for t in EXTRA]
    hist = {k: load("index", f"{k}.json") for k in ("SOXX", "SOXL", "QQQ", "SPY")}
    asof = hist["SOXX"][-1][0]  # 미국 종가 날짜 (한국 종목은 하루 앞설 수 있음)
    js = lambda v: json.dumps(v, ensure_ascii=False)

    s = line(s, "DATA", js(soxx) + ";")
    s = line(s, "M7_DATA", js([{k: v for k, v in e.items() if k not in ("avg", "n_valid", "n_neg", "n_over", "last", "last_date")} for e in m7]) + ";")
    s = line(s, "EXTRA", js([{k: v for k, v in e.items() if k not in ("avg", "n_valid", "n_neg", "n_over", "last", "last_date")} for e in extra]) + ";")
    s = line(s, "SOXX_HIST", js(hist["SOXX"]) + ";  // [월, 월말 종가] 분할 보정")
    s = line(s, "SOXL_HIST", js(hist["SOXL"]) + ";")
    s = line(s, "SOXX_PRICE", f"{hist['SOXX'][-1][1]};  // {hist['SOXX'][-1][0]} 종가")
    built = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    s = line(s, "BUILT", json.dumps(built) + ";  // 빌드 시각 (UTC ISO), build.py 가 채움")
    s = re.sub(r'(<p class="sub">)\d{4}-\d{2}-\d{2} 기준', rf"\g<1>{asof} 기준", s, count=1)
    open(PAGE, "w", encoding="utf-8").write(s)

    # QQQ · SPY: 방금 쓴 페이지의 계산 코드로
    known = {e["t"]: e for e in soxx + m7}
    alt = {}
    with tempfile.TemporaryDirectory() as tmp:
        for k in ("QQQ", "SPY"):
            df, hf, of = (os.path.join(tmp, f"{x}_{k}.json") for x in ("data", "hist", "res"))
            json.dump(index_data(k, known), open(df, "w"))
            json.dump(hist[k], open(hf, "w"))
            subprocess.run(["node", os.path.join(ROOT, "scripts", "run_idx.js"), PAGE, df, hf, of], check=True)
            alt[k] = json.load(open(of))
    s = open(PAGE, encoding="utf-8").read()
    s2 = re.sub(r"const IDX_ALT = /\*IDX_ALT\*/.*?;\n", lambda m: "const IDX_ALT = /*IDX_ALT*/" + json.dumps(alt, separators=(",", ":")) + ";\n", s, count=1)
    assert s2 != s or "/*IDX_ALT*/" in s
    open(PAGE, "w", encoding="utf-8").write(s2)
    json.dump({"built": built, "asof": asof}, open(os.path.join(ROOT, "docs", "version.json"), "w"))
    print("built", PAGE, asof, f"{len(s2) / 1e6:.2f} MB", dt.datetime.now().isoformat(timespec="seconds"))


if __name__ == "__main__":
    main()
