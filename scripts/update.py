"""데이터 갱신.

  python3 scripts/update.py prices            # 매일: 종목·지수 월봉 종가(이번 달은 최근 종가)와 컨센서스 PER 의 주가
  python3 scripts/update.py full [TICKER ...] # 매주: Zacks 분기 EPS 로 최근 24개월 TTM 다시 계산 + 연도별 컨센서스
  python3 scripts/update.py holdings          # 매주: SOXX·QQQ·SPY 구성 종목·비중 (새 종목은 START 부터 이력을 받음)
  python3 scripts/update.py backfill [TICKER ...]  # 한 번: START 까지 앞쪽 이력을 채움 (기존 행은 그대로)

데이터: data/stocks/{T}.json (종목), data/holdings/{IDX}.json, data/index/{IDX}.json ([[월, 종가], ...]).
24개월보다 오래된 행은 건드리지 않는다 (META 의 SEC 이력처럼 손으로 보정한 구간을 지키기 위해).
hist_src = "frozen" 인 종목(SK하이닉스·삼성전자, 연간 EPS 를 손으로 넣음)은 주가와 컨센서스만 갱신한다.
"""
import concurrent.futures as cf
import datetime as dt
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import forward_per as fp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
START = dt.date(2012, 1, 1)  # Zacks 분기 실적이 대체로 2012년 무렵부터 있음 (TTM 은 4분기가 쌓인 뒤부터)
INDEXES = {"SOXX": "SOXX", "SOXL": "SOXL", "QQQ": "QQQ", "SPY": "SPY"}
ZUA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120 Safari/537.36"}
REFRESH_MONTHS = 24


def fetch(url, headers=ZUA, tries=3):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(5 * (k + 1))


def load(path, default=None):
    try:
        return json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        return default


def save(path, obj):
    tmp = path + ".tmp"
    json.dump(obj, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def stock_path(t):
    return os.path.join(DATA, "stocks", f"{t}.json")


# ---------- 주가 ----------

def monthly(ticker, rng):
    """([(YYYY-MM, 종가)], 마지막 거래일, 현재가, 통화). 이번 달 값은 최근 종가."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1mo&range={rng}"
    r = json.loads(fetch(url, {"User-Agent": "Mozilla/5.0"}))["chart"]["result"][0]
    meta = r["meta"]
    local = lambda ts: dt.datetime.fromtimestamp(ts + meta.get("gmtoffset", 0), dt.timezone.utc).date()  # 거래소 현지 날짜
    last = local(meta["regularMarketTime"])
    rows = {}
    for t, c in zip(r.get("timestamp", []), r["indicators"]["quote"][0]["close"]):
        if c is not None:
            rows[local(t).strftime("%Y-%m")] = round(c, 2)
    rows[last.strftime("%Y-%m")] = round(meta["regularMarketPrice"], 2)
    return sorted(rows.items()), last, meta["regularMarketPrice"], meta.get("currency")


def apply_prices(st, months, last):
    """series 의 최근 달 종가를 바꾸고 새 달을 붙인다. TTM 은 그 달 행이 없으면 직전 행 값을 이어 쓴다."""
    s = st["series"]
    if not s:
        return
    by = {r[0][:7]: r for r in s}
    for ym, close in months:
        if ym < s[0][0][:7]:
            continue
        r = by.get(ym)
        ttm = r[2] if r else next((x[2] for x in reversed(s) if x[0][:7] < ym), None)
        date = last.isoformat() if ym == last.strftime("%Y-%m") else f"{ym}-01"
        row = [date, round(close / ttm, 2) if ttm and ttm > 0 else None, ttm, close]
        if r:
            r[:] = row
        else:
            s.append(row)
            by[ym] = row
    s.sort(key=lambda r: r[0])


def reprice_fwd(st, price):
    st["fwd_price"] = price
    for c in st.get("fwd") or []:
        e = c.get("eps")
        c["per"] = sorted(price / x for x in e) if e and e[0] > 0 else None


def update_prices_one(t):
    st = load(stock_path(t))
    try:
        months, last, px, cur = monthly(st["price_ticker"], "3mo")
        apply_prices(st, months, last)
        if st.get("fwd_ticker") != st["price_ticker"]:  # 컨센서스 통화가 다른 상장(ADR ↔ 본주)인 경우
            _, _, px, _ = monthly(st["fwd_ticker"], "5d")
        reprice_fwd(st, px)
        save(stock_path(t), st)
        return None
    except Exception as e:
        return f"{t}: {e}"


def update_index(k):
    path = os.path.join(DATA, "index", f"{k}.json")
    h = load(path, [])
    full = not h or h[0][0][:7] > START.strftime("%Y-%m")
    months, last, _, _ = monthly(INDEXES[k], "15y" if full else "3mo")
    by = {r[0][:7]: r for r in h}
    for ym, c in months:
        if ym < START.strftime("%Y-%m"):
            continue
        row = [last.isoformat() if ym == last.strftime("%Y-%m") else f"{ym}-01", c]
        if ym in by:
            by[ym][:] = row
        else:
            h.append(row)
    h.sort(key=lambda r: r[0])
    save(path, h)


# ---------- 실적 · 컨센서스 ----------

def zacks_quarters(ticker):
    """[(분기 끝 월 index, 발표일, EPS)] — Zacks earnings-calendar 의 reported EPS (분할 보정)."""
    s = fetch(f"https://www.zacks.com/stock/research/{ticker}/earnings-calendar")
    m = re.search(r'"earnings_announcements_earnings_table"\s*:\s*(\[\s*\[.*?\]\s*\])\s*[,}]', s, re.S)
    if not m:
        return []
    out = []
    for r in json.loads(m.group(1)):
        reported = r[3].replace("$", "").replace(",", "").strip()
        if reported in ("--", ""):
            continue
        mo, yr = r[1].split("/")
        mm, dd, yy = r[0].split("/")
        out.append((int(yr) * 12 + int(mo), dt.date(2000 + int(yy), int(mm), int(dd)), float(reported)))
    return sorted(out)


def ttm_points(qs):
    """[(발표일, TTM EPS)] — 빠진 분기 없이 연속 4분기일 때만."""
    out = []
    for i in range(3, len(qs)):
        w = qs[i - 3:i + 1]
        if all(w[k + 1][0] - w[k][0] == 3 for k in range(3)):
            out.append((w[-1][1], sum(q[2] for q in w)))
    return out


def month_end(day):
    return (day.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)


def rebuild_series(st, ttm, months, last):
    """최근 REFRESH_MONTHS 개월(새 종목이면 전체)의 TTM 을 Zacks 실적으로 다시 계산."""
    s = st["series"]
    cut = (dt.date.today().replace(day=1) - dt.timedelta(days=31 * REFRESH_MONTHS)).strftime("%Y-%m") if s else "0000"
    keep = [r for r in s if r[0][:7] < cut]
    rows = []
    for ym, close in months:
        if ym < cut or ym < START.strftime("%Y-%m"):
            continue
        day = dt.date(int(ym[:4]), int(ym[5:]), 1)
        known = [(rd, v) for rd, v in ttm if rd <= min(month_end(day), dt.date.today())]
        if not known or (day - known[-1][0]).days > 400:
            old = next((r for r in s if r[0][:7] == ym), None)  # 실적이 없으면 원래 행 유지
            if old:
                rows.append(old)
            continue
        v = round(known[-1][1], 4)
        date = last.isoformat() if ym == last.strftime("%Y-%m") else f"{ym}-01"
        rows.append([date, round(close / v, 2) if v > 0 else None, v, close])
    st["series"] = keep + rows


def consensus(st):
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    res = fp.compute(st["fwd_ticker"], 5, None, op)
    st["fwd"] = [{"per": c.get("per"), "est": c["est"], "actual": bool(c.get("actual")), "fy": c["fy"], "eps": c.get("eps"),
                  "thin": (not c["est"]) and bool(c["n"]) and max(c["n"]) <= 3} for c in res["rows"]]
    st["fwd_price"], st["fwd_cur"] = res["price"], res["currency"]


def update_full_one(t, name=None):
    st = load(stock_path(t)) or {"t": t, "name": name or t, "fwd": [], "fwd_ticker": t.replace(".", "-"), "series": [],
                                 "price_ticker": t.replace(".", "-"), "eps_unit": "Zacks 조정 EPS", "hist_src": "zacks"}
    errs = []
    if st.get("hist_src") == "zacks":
        try:
            months, last, _, cur = monthly(st["price_ticker"], "11y" if not st["series"] else "3y")
            st["price_currency"] = cur
            rebuild_series(st, ttm_points(zacks_quarters(t)), months, last)
        except Exception as e:
            errs.append(f"hist {e}")
    try:
        consensus(st)
    except (Exception, SystemExit) as e:  # forward_per 는 컨센서스가 없으면 SystemExit
        errs.append(f"fwd {e}")
    if st["series"] or st["fwd"]:
        save(stock_path(t), st)
    time.sleep(1.0)
    return f"{t}: " + "; ".join(errs) if errs else None


def backfill_one(t):
    """series 첫 달보다 앞선 달을 START 까지 Zacks TTM · Yahoo 종가로 채운다. 기존 행은 건드리지 않는다."""
    st = load(stock_path(t))
    if st.get("hist_src") != "zacks" or not st["series"]:
        return None
    first = st["series"][0][0][:7]
    if first <= START.strftime("%Y-%m"):
        return None
    try:
        months, _, _, _ = monthly(st["price_ticker"], "15y")
        ttm = ttm_points(zacks_quarters(t))
    except Exception as e:
        return f"{t}: {e}"
    rows = []
    for ym, close in months:
        if ym >= first or ym < START.strftime("%Y-%m"):
            continue
        day = dt.date(int(ym[:4]), int(ym[5:]), 1)
        known = [(rd, v) for rd, v in ttm if rd <= month_end(day)]
        if not known or (day - known[-1][0]).days > 400:
            continue
        v = round(known[-1][1], 4)
        rows.append([f"{ym}-01", round(close / v, 2) if v > 0 else None, v, close])
    if rows:
        st["series"] = rows + st["series"]
        save(stock_path(t), st)
    time.sleep(1.0)
    return None


# ---------- 구성 종목 ----------

def holdings(k):
    s = fetch(f"https://www.zacks.com/funds/etf/{k}/holding")
    m = re.search(r"etf_holdings\.formatted_data = (\[.*?\]\s*\])\s*;", s, re.S)
    out = []
    for r in json.loads(m.group(1)):
        tk = re.search(r'rel="([^"]+)"', r[1])
        name = re.sub(r"<[^>]+>", "", re.search(r'title="([^"]+)"', r[0]).group(1) if "title=" in r[0] else r[0])
        w = float(r[3].replace(",", "")) if r[3] not in ("", "NA") else 0
        out.append([tk.group(1) if tk else None, name, w])
    return out


def all_tickers():
    return sorted(f[:-5] for f in os.listdir(os.path.join(DATA, "stocks")) if f.endswith(".json"))


def run(fn, items, workers):
    errs = []
    with cf.ThreadPoolExecutor(workers) as ex:
        for i, e in enumerate(ex.map(fn, items), 1):
            if e:
                errs.append(e)
            if i % 50 == 0:
                print(f"  {i}/{len(items)}", flush=True)
    return errs


def main():
    mode, args = sys.argv[1], sys.argv[2:]
    if mode == "prices":
        for k in INDEXES:
            update_index(k)
        errs = run(update_prices_one, args or all_tickers(), 8)
    elif mode == "full":
        errs = run(update_full_one, args or all_tickers(), 6)
    elif mode == "backfill":
        for k in INDEXES:
            update_index(k)
        errs = run(backfill_one, args or all_tickers(), 6)
    elif mode == "holdings":
        errs, new = [], {}
        for k in ("SOXX", "QQQ", "SPY"):
            try:
                h = holdings(k)
            except Exception as e:
                errs.append(f"holdings {k}: {e}")
                continue
            if sum(w for _, _, w in h) < 90:  # 페이지 구조가 바뀌어 덜 읽힌 경우 기존 유지
                errs.append(f"holdings {k}: 비중 합 {sum(w for _, _, w in h):.1f}% — 건너뜀")
                continue
            json.dump(h, open(os.path.join(DATA, "holdings", f"{k}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
            for t, name, w in h:
                if t and w > 0 and t != "USD" and not os.path.exists(stock_path(t)):
                    new[t] = name
        print("새 종목", sorted(new))
        errs += run(lambda t: update_full_one(t, new[t]), sorted(new), 6)
    else:
        raise SystemExit(__doc__)
    print(f"{mode}: 실패 {len(errs)}")
    for e in errs:
        print("  " + e)


if __name__ == "__main__":
    main()
