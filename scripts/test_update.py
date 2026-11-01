import os
import sys
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

    def test_sec_ua_default(self):
        os.environ.pop("SEC_UA", None)
        self.assertIn("github.com/seongmin-kye/index-fair-value", update.sec_ua()["User-Agent"])


if __name__ == "__main__":
    unittest.main()
