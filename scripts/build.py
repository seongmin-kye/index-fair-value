"""data/ → docs/index.html.

페이지의 데이터 줄(DATA · M7_DATA · EXTRA · SOXX_HIST · SOXL_HIST · SOXX_PRICE · IDX_ALT)과 기준일 문구만 바꾸고,
QQQ·SPY(5·10년)와 SOXX 10년 백테스트는 같은 페이지 계산 코드를 node 로 돌린 결과를 IDX_ALT 로 넣는다.
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
    return {**{k: v for k, v in unify(d).items() if k != "hist_src"}, "name": d.get("name") or name, "w": w,
            "avg": round(sum(valid) / len(valid), 1) if len(valid) >= 12 else None,
            "n_valid": len(valid), "n_neg": sum(1 for p in pers if p is None),
            "n_over": sum(1 for p in pers if p is not None and p > CAP),
            "last": s[-1][1] if s else None, "last_date": s[-1][0] if s else None}


def unify(d):
    """두 출처(Zacks 조정 · Yahoo GAAP/주식보상 처리 차이) 추정이 1.5배 넘게 다르면 과거 이력(Zacks 조정 TTM)에 가까운 출처 하나만 쓴다.

    출처별 값(src)이 있으면 고른 출처가 없는 연도(보통 Zacks 만 있는 +2·+3년)와 그 위에 성장률로 이어 붙인 추정 연도는 비운다 —
    다른 잣대의 EPS 를 섞으면 경로가 꺾인다(TSLA: Yahoo 2027 2.16 → Zacks 2028 1.39). 페이지가 성장률로 다시 채운다.
    src 가 없는(옛) 데이터는 최소·최대 중 가까운 쪽만 고른다."""
    ttm = next((x[2] for x in reversed(d["series"]) if x[2]), None)
    c0 = next((c for c in d["fwd"] if c.get("eps") and c["eps"][0] > 0), None)
    if not (ttm and ttm > 0 and c0 and c0["eps"][1] / c0["eps"][0] > 1.5):
        return d
    src = c0.get("src")
    if src and len(src) >= 2:
        name = min(src, key=lambda k: abs(math.log(src[k] / ttm)) if src[k] > 0 else math.inf)
        dropped = False
        for c in d["fwd"]:
            if c.get("est"):
                keep = not dropped
            else:
                keep = bool(c.get("src")) and name in c["src"]
                if keep:
                    c["eps"], c["per"] = [c["src"][name]] * 2, [d["fwd_price"] / c["src"][name]] * 2 if c["src"][name] > 0 else None
                elif c.get("eps"):
                    dropped = True
            if not keep:
                c["eps"] = c["per"] = None
            c["src_used"] = name
    else:
        k = min((0, 1), key=lambda j: abs(math.log(c0["eps"][j] / ttm)))
        for c in d["fwd"]:
            if c.get("eps"):
                c["eps"], c["per"] = [c["eps"][k]] * 2, [d["fwd_price"] / c["eps"][k]] * 2 if c["eps"][k] > 0 else None
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


def nport():
    """분기말 → N-PORT 행 [티커, 이름, 비중%, 주식수, 평가액, id] (날짜 오름차순)."""
    d = os.path.join(DATA, "holdings", "SOXX", "nport")
    return {f[:-5]: load("holdings", "SOXX", "nport", f) for f in sorted(os.listdir(d)) if f.endswith(".json")}


def soxx_universe():
    """DATA 종목: Zacks 현재 구성(비중순, w) 다음에 N-PORT 에만 나온 과거 종목(알파벳순, w=0). 종목 파일 없는 티커는 뺀다."""
    cur = [(t, n, w) for t, n, w in load("holdings", "SOXX.json") if t and w > 0]
    seen = {t for t, _, _ in cur}
    past = {}
    for rows in nport().values():
        for r in rows:
            if r[0] and r[0] not in seen:
                past.setdefault(r[0], r[1])
    ents = [soxx_entry(t, n, w) for t, n, w in cur] + [soxx_entry(t, past[t], 0) for t in sorted(past)]
    return [e for e in ents if e]


def w_hist(universe):
    """분기말 → {티커: 비중%, _neutral: %}. DATA 에 없는 행(티커 없음 · 종목 파일 없음)의 비중은 _neutral 에 합산."""
    have = {e["t"] for e in universe}
    out = {}
    for q, rows in nport().items():
        o = {}
        neutral = 0.0
        for r in rows:
            if r[0] in have:
                o[r[0]] = round(o.get(r[0], 0) + r[2], 4)
            else:
                neutral += r[2]
        o["_neutral"] = round(neutral, 4)
        out[q] = o
    return out


def main():
    s = open(PAGE, encoding="utf-8").read()
    soxx = soxx_universe()
    m7 = [soxx_entry(t, t, 0) for t in M7]
    extra = [soxx_entry(t, t, 0) for t in EXTRA]
    hist = {k: load("index", f"{k}.json") for k in ("SOXX", "SOXL", "QQQ", "SPY")}
    asof = hist["SOXX"][-1][0]  # 미국 종가 날짜 (한국 종목은 하루 앞설 수 있음)
    js = lambda v: json.dumps(v, ensure_ascii=False)

    s = line(s, "DATA", js(soxx) + ";")
    s = line(s, "SOXX_W_HIST", js(w_hist(soxx)) + ";  // {분기말: {티커: 비중%, _neutral: %}} build.py 가 채움")
    s = line(s, "M7_DATA", js([{k: v for k, v in e.items() if k not in ("avg", "n_valid", "n_neg", "n_over", "last", "last_date")} for e in m7]) + ";")
    s = line(s, "EXTRA", js([{k: v for k, v in e.items() if k not in ("avg", "n_valid", "n_neg", "n_over", "last", "last_date")} for e in extra]) + ";")
    s = line(s, "SOXX_HIST", js(hist["SOXX"]) + ";  // [월, 월말 종가] 분할 보정")
    s = line(s, "SOXL_HIST", js(hist["SOXL"]) + ";")
    s = line(s, "SOXX_PRICE", f"{hist['SOXX'][-1][1]};  // {hist['SOXX'][-1][0]} 종가")
    built = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    s = line(s, "BUILT", json.dumps(built) + ";  // 빌드 시각 (UTC ISO), build.py 가 채움")
    s = re.sub(r'(<p class="sub">)\d{4}-\d{2}-\d{2} 기준', rf"\g<1>{asof} 기준", s, count=1)
    open(PAGE, "w", encoding="utf-8").write(s)

    # QQQ · SPY · SOXX@10: 방금 쓴 페이지의 계산 코드로
    known = {e["t"]: e for e in soxx + m7}
    alt = {}
    with tempfile.TemporaryDirectory() as tmp:
        for k in ("SOXX", "QQQ", "SPY"):
            df, hf = (os.path.join(tmp, f"{x}_{k}.json") for x in ("data", "hist"))
            if k != "SOXX":  # SOXX 는 페이지 데이터 그대로 (5년은 브라우저가 직접 계산)
                json.dump(index_data(k, known), open(df, "w"))
                json.dump(hist[k], open(hf, "w"))
            for span in ((10,) if k == "SOXX" else (5, 10)):
                key, of = k + ("@10" if span == 10 else ""), os.path.join(tmp, f"res_{k}_{span}.json")
                args = ["-", "-"] if k == "SOXX" else [df, hf]
                subprocess.run(["node", os.path.join(ROOT, "scripts", "run_idx.js"), PAGE, *args, of, str(span)], check=True)
                alt[key] = json.load(open(of))
    s = open(PAGE, encoding="utf-8").read()
    s2 = re.sub(r"const IDX_ALT = /\*IDX_ALT\*/.*?;\n", lambda m: "const IDX_ALT = /*IDX_ALT*/" + json.dumps(alt, separators=(",", ":")) + ";\n", s, count=1)
    assert s2 != s or "/*IDX_ALT*/" in s
    open(PAGE, "w", encoding="utf-8").write(s2)
    json.dump({"built": built, "asof": asof}, open(os.path.join(ROOT, "docs", "version.json"), "w"))
    print("built", PAGE, asof, f"{len(s2) / 1e6:.2f} MB", dt.datetime.now().isoformat(timespec="seconds"))


if __name__ == "__main__":
    main()
