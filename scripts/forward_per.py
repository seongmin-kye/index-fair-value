#!/usr/bin/env python3
"""연도별 forward PER 계산 (forward-per-method.md 방식).

연도 +n 의 PER = 현재 주가 ÷ 해당 회계연도 조정 EPS 컨센서스.
회계연도는 12개월 중 더 많은 달이 속한 달력연도에 붙인다.
컨센서스가 없는 연도는 마지막 컨센서스 연도의 성장률을 이어 붙여 괄호로 표시한다.

사용법:
    python3 forward_per.py NVDA
    python3 forward_per.py AAPL MSFT --years 5 --growth 0.10
"""

import argparse
import datetime
import http.cookiejar
import json
import re
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0"}
MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def get_json(opener, url, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with opener.open(req, timeout=15) as r:
        return json.loads(r.read())


def calendar_year(fy_end_year, fy_end_month):
    """회계연도 끝(연, 월) → 더 많은 달이 속한 달력연도. 6:6 이면 끝나는 해."""
    return fy_end_year if fy_end_month >= 6 else fy_end_year - 1


def fetch_price(opener, ticker):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(ticker)}?interval=1m&range=1d")
    meta = get_json(opener, url)["chart"]["result"][0]["meta"]
    ts = datetime.datetime.fromtimestamp(meta["regularMarketTime"])
    return meta["regularMarketPrice"], ts, meta.get("currency", "")


def yahoo_quote_summary(opener, ticker, modules):
    if not hasattr(opener, "crumb"):
        try:
            opener.open(urllib.request.Request("https://fc.yahoo.com", headers=UA), timeout=15)
        except Exception:
            pass  # 404 여도 쿠키는 설정된다
        req = urllib.request.Request(
            "https://query1.finance.yahoo.com/v1/test/getcrumb", headers=UA)
        opener.crumb = opener.open(req, timeout=15).read().decode()
    url = (f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/"
           f"{urllib.parse.quote(ticker)}?modules={modules}"
           f"&crumb={urllib.parse.quote(opener.crumb)}")
    return get_json(opener, url)["quoteSummary"]["result"][0]


def fetch_yahoo_quarters(opener, ticker):
    """최근 4개 분기 조정 EPS 실적. {(qtr_end_year, qtr_end_month): eps}"""
    hist = yahoo_quote_summary(opener, ticker, "earningsHistory")["earningsHistory"]["history"]
    out = {}
    for h in hist:
        eps = h["epsActual"].get("raw")
        if eps is not None:
            end = datetime.date.fromisoformat(h["quarter"]["fmt"])
            out[(end.year, end.month)] = eps
    return out


def fetch_nasdaq_quarters(opener, ticker):
    """최근 4개 분기 조정 EPS 실적 (Zacks). {(qtr_end_year, qtr_end_month): eps}"""
    url = f"https://api.nasdaq.com/api/company/{urllib.parse.quote(ticker)}/earnings-surprise"
    data = get_json(opener, url, {"Accept": "application/json"})
    rows = (((data or {}).get("data") or {}).get("earningsSurpriseTable") or {}).get("rows") or []
    out = {}
    for r in rows:
        mon, year = r["fiscalQtrEnd"].split()
        out[(int(year), MONTHS[mon[:3]])] = float(r["eps"])
    return out


def fiscal_year_actual(quarters, fy_end):
    """회계연도 끝(연, 월) 이전 12개월의 분기 4개가 모두 있으면 합계, 아니면 None."""
    fy_idx = fy_end[0] * 12 + fy_end[1]
    qs = [eps for (y, m), eps in quarters.items() if 0 <= fy_idx - (y * 12 + m) < 12]
    return sum(qs) if len(qs) == 4 else None


def fetch_yahoo_eps(opener, ticker):
    """FY+0, FY+1. {(end_year, end_month): (eps, n)}"""
    trend = yahoo_quote_summary(opener, ticker, "earningsTrend")["earningsTrend"]["trend"]
    out = {}
    for t in trend:
        if t.get("period") not in ("0y", "+1y"):
            continue
        eps = t["earningsEstimate"]["avg"].get("raw")
        if eps is None:
            continue
        end = datetime.date.fromisoformat(t["endDate"])
        n = t["earningsEstimate"]["numberOfAnalysts"].get("raw")
        out[(end.year, end.month)] = (eps, n)
    return out


def fetch_nasdaq_eps(opener, ticker):
    """FY+0 ~ FY+3 (Zacks). {(end_year, end_month): (eps, n)}"""
    url = f"https://api.nasdaq.com/api/analyst/{urllib.parse.quote(ticker)}/earnings-forecast"
    data = get_json(opener, url, {"Accept": "application/json"})
    rows = (((data or {}).get("data") or {}).get("yearlyForecast") or {}).get("rows") or []
    out = {}
    for r in rows:
        mon, year = r["fiscalEnd"].split()
        eps = float(str(r["consensusEPSForecast"]).replace("$", "").replace(",", ""))
        out[(int(year), MONTHS[mon[:3]])] = (eps, int(r["noOfEstimates"]))
    return out


def fetch_wisereport_eps(opener, ticker):
    """한국 종목 FY+0 ~ FY+2 (Naver WiseReport, FnGuide 컨센서스). 애널리스트 수는 없다."""
    code = ticker.split(".")[0]
    page = f"https://navercomp.wisereport.co.kr/v2/company/c1010001.aspx?cmp_cd={code}"
    with opener.open(urllib.request.Request(page, headers=UA), timeout=15) as r:
        enc = re.search(r"encparam: *'([^']+)'", r.read().decode("utf-8")).group(1)
    url = (f"https://navercomp.wisereport.co.kr/v2/company/ajax/cF1001.aspx"
           f"?cmp_cd={code}&fin_typ=0&freq_typ=Y&encparam={enc}")
    req = urllib.request.Request(url, headers={**UA, "Referer": page})
    with opener.open(req, timeout=15) as r:
        s = r.read().decode("utf-8")
    periods = re.findall(r"(\d{4})/(\d{2})(\(E\))?", s)
    eps_row = re.search(r">\s*EPS\(원\)\s*<.*?</tr>", s, re.S).group(0)
    values = re.findall(r">\s*(-?[\d,\.]+|N/A)\s*<", eps_row)
    out = {}
    for (y, m, est), v in zip(periods, values):
        if est and v != "N/A":
            out[(int(y), int(m))] = (float(v.replace(",", "")), None)
    return out


def build_rows(sources, quarters, years, growth_override):
    """달력연도별로 출처 EPS 를 모으고, 끝난 연도는 실적, 빈 연도는 성장률로 추정한다."""
    by_cy = {}  # cy -> {"fy": (y, m), "eps": [..], "n": [..]}
    for src in sources.values():
        for (fy, fm), (eps, n) in src.items():
            row = by_cy.setdefault(calendar_year(fy, fm), {"fy": (fy, fm), "eps": [], "n": []})
            row["eps"].append(eps)
            row["n"].append(n)

    this_year = datetime.date.today().year
    known = sorted(cy for cy in by_cy if cy >= this_year)
    if not known:
        raise SystemExit("컨센서스 EPS 를 찾지 못했습니다.")

    def mid(cy):
        e = by_cy[cy]["eps"]
        return sum(e) / len(e)

    # 애널리스트 3명 이하 연도는 성장률 기준에서 뺀다.
    # 컨센서스가 2개 연도 이하(해외 종목 등)면 --growth 없이는 추정하지 않는다.
    growth, basis = growth_override, None
    def thin(cy):
        ns = [x for x in by_cy[cy]["n"] if x is not None]
        return bool(ns) and max(ns) <= 3  # 수가 공개되지 않은 출처(FnGuide)는 거르지 않는다

    reliable = [cy for cy in known if not thin(cy)]
    if growth is None and len(known) >= 3 and len(reliable) >= 2 and mid(reliable[-2]) > 0:
        growth = mid(reliable[-1]) / mid(reliable[-2]) - 1
        basis = (reliable[-2], reliable[-1])

    rows = []
    last_cy = known[-1]
    fy, fm = by_cy[last_cy]["fy"]
    for i in range(years + 1):
        cy = this_year + i
        if cy in by_cy:
            r = by_cy[cy]
            rows.append({"i": i, "cy": cy, "fy": r["fy"], "eps": (min(r["eps"]), max(r["eps"])),
                         "n": [x for x in r["n"] if x is not None], "est": False})
        elif cy < known[0]:
            # 이미 끝난 회계연도라 컨센서스 대신 분기 실적 합계를 쓴다 (예: 8월 결산 종목의 올해)
            k = known[0] - cy
            f0y, f0m = by_cy[known[0]]["fy"]
            closed_fy = (f0y - k, f0m)
            acts = [a for a in (fiscal_year_actual(q, closed_fy) for q in quarters.values())
                    if a is not None]
            rows.append({"i": i, "cy": cy, "fy": closed_fy, "n": [], "est": False, "actual": True,
                         "eps": (min(acts), max(acts)) if acts else None})
        elif cy > last_cy:
            k = cy - last_cy
            if growth is None:
                rows.append({"i": i, "cy": cy, "fy": (fy + k, fm), "eps": None, "n": [], "est": True})
                continue
            e = mid(last_cy) * (1 + growth) ** k
            base_n = [x for x in by_cy[last_cy]["n"] if x is not None]
            rows.append({"i": i, "cy": cy, "fy": (fy + k, fm), "eps": (e, e), "n": base_n,
                         "est": True, "base": last_cy})
    return rows, growth, basis


def fmt_range(lo, hi, f, paren=False):
    s = f(lo) if f(lo) == f(hi) else f"{f(lo)} ~ {f(hi)}"
    return f"({s})" if paren else s


def compute(ticker, years, growth_override, opener):
    price, ts, cur = fetch_price(opener, ticker)
    sources = {}
    fetchers = [("Zacks", fetch_nasdaq_eps), ("Yahoo", fetch_yahoo_eps)]
    if ticker.endswith((".KS", ".KQ")):
        fetchers[0] = ("FnGuide", fetch_wisereport_eps)
    for name, fn in fetchers:
        try:
            sources[name] = fn(opener, ticker)
        except Exception as e:
            print(f"  [{name}] 조회 실패: {e}", file=sys.stderr)
    quarters = {}
    for name, fn in (("Zacks", fetch_nasdaq_quarters), ("Yahoo", fetch_yahoo_quarters)):
        try:
            quarters[name] = fn(opener, ticker)
        except Exception:
            pass  # 끝난 회계연도가 있을 때만 쓰는 보조 데이터
    rows, growth, basis = build_rows(sources, quarters, years, growth_override)
    for r in rows:
        lo_hi = r["eps"]
        r["per"] = sorted(price / x for x in lo_hi) if lo_hi and lo_hi[0] > 0 else None
    return {"ticker": ticker, "price": price, "time": ts.isoformat(), "currency": cur,
            "rows": rows, "growth": growth, "basis": basis}


def report(ticker, years, growth_override, opener):
    res = compute(ticker, years, growth_override, opener)
    price, cur, rows, growth, basis = (res[k] for k in ("price", "currency", "rows", "growth", "basis"))
    ts = datetime.datetime.fromisoformat(res["time"])

    print(f"\n## {ticker} (주가 {price:,.2f} {cur}, {ts:%Y-%m-%d %H:%M})\n")
    print("| 연도 | 달력연도 | 회계연도 | EPS (컨센서스/실적) | 애널리스트 수 | PER |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        suffix = "A" if r.get("actual") else "E"
        fy_label = f"FY{r['fy'][0]}{suffix}" + (f" ({r['fy'][1]}월 결산)" if r["fy"][1] != 12 else "")
        if r["eps"] is None:
            note = "실적 조회 불가" if r.get("actual") else "-"
            print(f"| +{r['i']} | {r['cy']} | {fy_label} | {note} | 없음 | - |")
            continue
        lo, hi = r["eps"]
        sym = "$" if cur == "USD" else f"{cur} "
        eps = fmt_range(lo, hi, lambda x: f"{sym}{x:,.2f}", r["est"])
        per = fmt_range(*r["per"], lambda x: f"{x:.1f}", r["est"]) if r["per"] else "n/a"
        n = fmt_range(min(r["n"]), max(r["n"]), str) if r["n"] else "미공개"
        if r.get("actual"):
            n = "실적 (4분기 합)"
        elif r["est"]:
            n = f"({n}, {r['base']} 기준)"
        print(f"| +{r['i']} | {r['cy']} | {fy_label} | {eps} | {n} | {per} |")

    if any(r["est"] and r["eps"] for r in rows):
        how = "지정" if basis is None else f"{basis[0]}→{basis[1]} 성장률"
        print(f"\n- 괄호 값은 연 {growth:.1%} 성장({how})을 이어 붙인 추정입니다. "
              "애널리스트 수는 출발점 연도의 값입니다.")
    if any(r["eps"] is None and r["est"] for r in rows):
        print("\n- '-' 연도는 믿을 만한 컨센서스 연도가 부족해 추정하지 않았습니다. --growth 로 채울 수 있습니다.")
    thin = [r["cy"] for r in rows if not r["est"] and r["n"] and max(r["n"]) <= 3]
    if thin:
        print(f"- 애널리스트 3명 이하 연도({', '.join(map(str, thin))})는 소수 의견입니다.")


def main():
    p = argparse.ArgumentParser(description="연도별 forward PER 계산")
    p.add_argument("tickers", nargs="+")
    p.add_argument("--years", type=int, default=5, help="+0 부터 몇 년 뒤까지 (기본 5)")
    p.add_argument("--growth", type=float, help="추정 연도 성장률 (예: 0.10)")
    p.add_argument("--json", action="store_true", help="표 대신 JSON 으로 출력")
    args = p.parse_args()

    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    if args.json:
        out = []
        for t in args.tickers:
            try:
                out.append(compute(t.upper(), args.years, args.growth, opener))
            except Exception as e:
                out.append({"ticker": t.upper(), "error": str(e)})
        json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
        return
    for t in args.tickers:
        try:
            report(t.upper(), args.years, args.growth, opener)
        except Exception as e:
            print(f"\n## {t.upper()}: 실패 — {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
