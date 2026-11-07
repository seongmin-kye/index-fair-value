"""update.py 단위 테스트: python3 scripts/test_update.py"""
import datetime as dt
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update  # noqa: E402


def _row(name, cusip, isin, bal, val, pct, cat="EC"):
    ident = f'<identifiers><isin value="{isin}"/></identifiers>' if isin else ""
    return (f"<invstOrSec><name>{name}</name><cusip>{cusip}</cusip>{ident}<balance>{bal}</balance>"
            f"<valUSD>{val}</valUSD><pctVal>{pct}</pctVal><assetCat>{cat}</assetCat></invstOrSec>")


FIXTURE = (
    '<?xml version="1.0"?><edgarSubmission xmlns="http://www.sec.gov/edgar/nport">'
    "<formData><genInfo><seriesId>S000004354</seriesId><repPdDate>2024-12-31</repPdDate></genInfo>"
    "<invstOrSecs>"
    + _row("NVIDIA Corp", "67066G104", "US67066G1040", "100", "1000", "8.0")
    + _row("Lam Research Corp", "512807108", "US5128071082", "10", "200", "2.0")
    + _row("Lam Research Corp", "512807306", "US5128073062", "20", "300", "2.5")
    + _row("ASML Holding NV", "N/A", "USN070592100", "5", "400", "3.0")
    + _row("BlackRock Cash", "000000000", "", "1", "50", "0.5", "STIV")
    + _row("Futures", "000000000", "", "1", "10", "0.1", "DE")
    + "</invstOrSecs></formData></edgarSubmission>"
)


class NportTest(unittest.TestCase):
    def setUp(self):
        self._figi = update.openfigi

    def tearDown(self):
        update.openfigi = self._figi

    def test_parse_keeps_only_equities_and_picks_id(self):
        date, rows = update.nport_parse(FIXTURE)
        self.assertEqual(date, "2024-12-31")
        self.assertEqual([r[1] for r in rows], ["67066G104", "512807108", "512807306", "USN070592100"])

    def test_parse_merges_same_ticker(self):
        ids = {"67066G104": "NVDA", "512807108": "LRCX", "512807306": "LRCX", "USN070592100": "ASML"}
        out = update.resolve_ids(update.nport_parse(FIXTURE)[1], ids, {})
        lrcx = [r for r in out if r[0] == "LRCX"]
        self.assertEqual(len(lrcx), 1)
        self.assertAlmostEqual(lrcx[0][2], 4.5)
        self.assertAlmostEqual(lrcx[0][3], 30)
        self.assertAlmostEqual(lrcx[0][4], 500)
        self.assertEqual(lrcx[0][5], "512807108")

    def test_resolve_prefers_zacks_ticker_on_same_name(self):
        update.openfigi = lambda ids: {i: "TSMWI" for i in ids}
        rows = [("Taiwan Semiconductor Manufacturing Co Ltd", "US8740391003", 9.0, 1, 1)]
        ids = {}
        out = update.resolve_ids(rows, ids, {"TSM": "TAIWAN SEMICONDUCTOR MFG"})
        self.assertEqual(out[0][0], "TSM")
        self.assertEqual(ids["US8740391003"], "TSM")

    def test_resolve_unmapped_is_none(self):
        update.openfigi = lambda ids: {}
        ids = {}
        out = update.resolve_ids([("Mystery Corp", "123456789", 1.0, 1, 1)], ids, {})
        self.assertIsNone(out[0][0])
        self.assertEqual(ids, {})

    def test_resolve_keeps_earlier_batches_when_later_batch_fails(self):
        calls = []

        def fake(batch):
            calls.append(batch)
            if len(calls) == 2:
                raise RuntimeError("429")
            return {i: "T" + i for i in batch}
        update.openfigi = fake
        rows = [(f"Co{n}", f"{n:09d}", 1.0, 1, 1) for n in range(1, 16)]
        ids = {}
        with self.assertRaises(RuntimeError):
            update.resolve_ids(rows, ids, {})
        self.assertEqual(len(ids), 10)
        self.assertEqual(ids["000000001"], "T000000001")

    def test_openfigi_skips_entries_without_ticker(self):
        resp = [{"data": [{"ticker": "NVDA"}]}, {"data": [{"name": "no ticker"}]}, {"warning": "No identifier found."}]
        urlopen, sleep = update.urllib.request.urlopen, update.time.sleep
        update.urllib.request.urlopen = lambda req, timeout=None: io.BytesIO(json.dumps(resp).encode())
        update.time.sleep = lambda s: None
        try:
            out = self._figi(["67066G104", "512807108", "USN070592100"])
        finally:
            update.urllib.request.urlopen, update.time.sleep = urlopen, sleep
        self.assertEqual(out, {"67066G104": "NVDA"})

    def test_parse_empty_numbers_are_zero(self):
        xml = FIXTURE.replace("<pctVal>8.0</pctVal>", "<pctVal></pctVal>")
        self.assertEqual(update.nport_parse(xml)[1][0][2], 0.0)

    def test_sec_ua_default(self):
        os.environ.pop("SEC_UA", None)
        self.assertIn("github.com/seongmin-kye/index-fair-value", update.sec_ua()["User-Agent"])
        os.environ["SEC_UA"] = ""
        try:
            self.assertIn("github.com/seongmin-kye/index-fair-value", update.sec_ua()["User-Agent"])
        finally:
            os.environ.pop("SEC_UA", None)

    def test_nport_atom_reads_content_nested_fields(self):
        xml = """<feed xmlns="http://www.w3.org/2005/Atom">
<entry><content type="text/xml"><accession-number>A-1</accession-number><filing-date>2026-08-25</filing-date><filing-type>NPORT-P</filing-type></content></entry>
<entry><content type="text/xml"><accession-number>A-2</accession-number><filing-date>2026-07-13</filing-date><filing-type>NPORT-P/A</filing-type></content></entry>
</feed>"""
        self.assertEqual(update.nport_atom(xml), [("A-1", "2026-08-25", "NPORT-P"), ("A-2", "2026-07-13", "NPORT-P/A")])

    def test_pick_filings_original_beats_amendment(self):
        p = [("2026-06-30", "NPORT-P", "2026-08-01", "orig"),
             ("2026-06-30", "NPORT-P/A", "2026-09-01", "amend"),
             ("2026-03-31", "NPORT-P/A", "2026-05-01", "a1"),
             ("2026-03-31", "NPORT-P/A", "2026-06-01", "a2"),
             ("2025-12-31", "NPORT-P", "2026-02-01", "o1"),
             ("2025-12-31", "NPORT-P", "2026-03-01", "o2")]
        self.assertEqual(update.pick_filings(p), {"2026-06-30": "orig", "2026-03-31": "a2", "2025-12-31": "o2"})

    def test_ntm_eps_weights_fiscal_years(self):
        fwd = [{"fy": [2026, 12], "eps": [10, 10]}, {"fy": [2027, 12], "eps": [20, 20]}]
        self.assertAlmostEqual(update.ntm_eps(fwd, dt.date(2026, 7, 1)), 10 * (184/365) + 20 * (181/365), places=1)

    def test_ntm_eps_none_when_gap(self):
        self.assertIsNone(update.ntm_eps([{"fy": [2026, 12], "eps": [10, 10]}], dt.date(2026, 7, 1)))

    def test_ntm_eps_none_when_eps_missing(self):
        fwd = [{"fy": [2026, 12], "eps": None}, {"fy": [2027, 12], "eps": [20, 20]}]
        self.assertIsNone(update.ntm_eps(fwd, dt.date(2026, 7, 1)))

    def test_should_snapshot_only_for_full_run(self):
        self.assertTrue(update.should_snapshot([]))
        self.assertFalse(update.should_snapshot(["AAA", "BBB"]))

    def test_snapshot_once_per_month(self):
        old = update.DATA
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "stocks"))
            fwd = [{"fy": [2026, 12], "eps": [10, 12]}, {"fy": [2027, 12], "eps": [20, 20]}, {"fy": [2028, 12], "eps": None}]
            with open(os.path.join(d, "stocks", "AAA.json"), "w") as f:
                json.dump({"fwd": fwd}, f)
            update.DATA = d
            try:
                p = update.consensus_snapshot(["AAA", "NOPE"], dt.date(2026, 7, 1))
                self.assertEqual(os.path.basename(p), "2026-07.json")
                self.assertIsNone(update.consensus_snapshot(["AAA"], dt.date(2026, 7, 20)))
                snap = json.load(open(p))
            finally:
                update.DATA = old
        self.assertEqual(list(snap), ["AAA"])
        self.assertEqual(snap["AAA"]["fy"], [[2026, 12, 11.0], [2027, 12, 20.0]])
        self.assertIsInstance(snap["AAA"]["ntm"], float)

    def test_bar_date_dst(self):
        # Yahoo 월봉: 2026-10-01 00:00 EDT = 04:00 UTC. 서머타임이 끝난 뒤(EST) 변환해도 10월 1일이어야 한다
        ts = int(dt.datetime(2026, 10, 1, 4, 0, tzinfo=dt.timezone.utc).timestamp())
        assert update.bar_date(ts, "America/New_York") == dt.date(2026, 10, 1)
        # 2025-11-01 00:00 EDT (2025년 서머타임은 11-02 종료) = 04:00 UTC → 11월 1일
        ts = int(dt.datetime(2025, 11, 1, 4, 0, tzinfo=dt.timezone.utc).timestamp())
        assert update.bar_date(ts, "America/New_York") == dt.date(2025, 11, 1)
        # 2026-12-01 00:00 EST = 05:00 UTC → 12월 1일
        ts = int(dt.datetime(2026, 12, 1, 5, 0, tzinfo=dt.timezone.utc).timestamp())
        assert update.bar_date(ts, "America/New_York") == dt.date(2026, 12, 1)
        # 한국(서머타임 없음): 2026-10-01 00:00 KST = 09-30 15:00 UTC → 10월 1일
        ts = int(dt.datetime(2026, 9, 30, 15, 0, tzinfo=dt.timezone.utc).timestamp())
        assert update.bar_date(ts, "Asia/Seoul") == dt.date(2026, 10, 1)

    # ---- 액면분할: Yahoo 는 분할 뒤 전체 이력을 조정하지만 갱신은 최근 몇 달만 덮어쓴다 (2026-11-05 SOXX 3:1 사고)
    def test_split_adjust_index_rescales_older_rows(self):
        rows = [["2026-07-01", 500.0], ["2026-08-01", 511.04], ["2026-09-01", 568.64], ["2026-10-30", 471.51]]
        got = update.split_adjust(rows, [("2026-09", 189.55), ("2026-10", 157.17), ("2026-11", 136.53)], 1)
        self.assertEqual([r[1] for r in rows], [166.67, 170.35, 189.55, 157.17])
        self.assertEqual([ym for ym, _ in got], ["2026-09", "2026-10", "<2026-09"])
        self.assertAlmostEqual(got[0][1], 3.0, places=2)

    def test_split_adjust_stock_divides_eps_keeps_per(self):
        rows = [["2026-07-01", 25.0, 20.0, 500.0], ["2026-09-01", 28.43, 20.0, 568.64]]
        update.split_adjust(rows, [("2026-09", 189.55), ("2026-10", 157.17)], 3, 2)
        self.assertEqual([r[:2] + [r[3]] for r in rows], [["2026-07-01", 25.0, 166.67], ["2026-09-01", 28.43, 189.55]])
        for r in rows:
            self.assertAlmostEqual(r[2], 20 / 3, places=3)  # 배수는 568.64/189.55 ≈ 2.99995 라 정확히 3 은 아님

    def test_split_adjust_fixes_half_adjusted_series(self):
        # 분할 뒤 이미 한 번 갱신돼 최근 달만 조정된 상태: 겹치는 가장 오래된 달(08)의 배수로 그 앞을 고치고 09·10 은 그대로
        rows = [["2026-07-01", 500.0], ["2026-08-01", 511.04], ["2026-09-01", 189.55], ["2026-10-01", 157.17]]
        update.split_adjust(rows, [("2026-08", 170.35), ("2026-09", 189.55), ("2026-10", 157.17)], 1)
        self.assertEqual([r[1] for r in rows], [166.67, 170.35, 189.55, 157.17])

    def test_split_adjust_ignores_small_revisions_and_none(self):
        rows = [["2026-08-01", 100.0], ["2026-09-01", None, None, None][:2], ["2026-10-01", 102.0]]
        rows[1] = ["2026-09-01", None]
        self.assertEqual(update.split_adjust(rows, [("2026-09", 101.0), ("2026-10", 100.5)], 1), [])
        self.assertEqual([r[1] for r in rows], [100.0, None, 102.0])


class RecentTest(unittest.TestCase):
    def test_is_recent(self):
        self.assertTrue(update.is_recent({"last_report": "2026-10-29"}, dt.date(2026, 11, 8)))
        self.assertFalse(update.is_recent({"last_report": "2026-10-24"}, dt.date(2026, 11, 8)))
        self.assertFalse(update.is_recent({}, dt.date(2026, 11, 8)))


if __name__ == "__main__":
    unittest.main()
