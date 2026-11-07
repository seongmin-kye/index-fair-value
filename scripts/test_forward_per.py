"""python3 -m unittest scripts.test_forward_per — 컨센서스 출처 파서·합치기 규칙 (외부 호출 없음)."""
import datetime
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import forward_per as fp  # noqa: E402

ZACKS_EST = ('<table><tr><th></th><th>Current Qtr <span>(10/2026)</span></th><th>Next Qtr <span>(1/2027)</span></th>'
             '<th>Current Year <span>(1/2027)</span></th><th>Next Year <span>(1/2028)</span></th></tr>'
             '<tr><td>Zacks Consensus Estimate</td><td>2.49</td><td>2.75</td><td>9.30</td><td>15.75</td></tr>'
             '<tr><td># of Estimates</td><td>13</td><td>12</td><td>17</td><td>15</td></tr>'
             '<tr><td>Year ago EPS</td><td>1.30</td><td>1.62</td><td>4.77</td><td>9.30</td></tr></table>')
SALES_TBL = ZACKS_EST.replace("Year ago EPS", "Year ago Sales").replace("9.30", "407.51B")
CAL = ('"earnings_announcements_earnings_table" : [["11/3/26","9/2026","$1.95","$2.09","+$0.14","+7.18%",""],'
       '["8/4/26","6/2026","$1.60","$1.66","",""," "],["5/5/26","3/2026","--","--","","",""]] ,')


class _FakeDate(datetime.date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 8)


class ZacksParseTest(unittest.TestCase):
    def test_parse_zacks_estimates_reads_year_columns(self):
        self.assertEqual(fp.parse_zacks_estimates(SALES_TBL + ZACKS_EST), {(2027, 1): (9.30, 17), (2028, 1): (15.75, 15)})

    def test_parse_zacks_estimates_empty_raises(self):
        with self.assertRaises(ValueError):
            fp.parse_zacks_estimates("<html>blocked</html>")

    def test_parse_zacks_calendar(self):
        self.assertEqual(fp.parse_zacks_calendar(CAL),
                         [(datetime.date(2026, 8, 4), (2026, 6), 1.66), (datetime.date(2026, 11, 3), (2026, 9), 2.09)])


class MergeTest(unittest.TestCase):
    def _rows(self, sources, quarters=None):
        with mock.patch.object(fp.datetime, "date", _FakeDate):  # today = 2026-11-08
            return fp.build_rows(sources, quarters or {}, 4, None)[0]

    def test_basis_ok(self):
        ref = {(2026, 3): 1.0, (2026, 6): 1.2, (2026, 9): 1.5}
        self.assertTrue(fp.basis_ok({(2026, 6): 1.21, (2026, 9): 1.5}, ref))
        self.assertFalse(fp.basis_ok({(2026, 6): 1.0, (2026, 9): 1.5}, ref))
        self.assertIsNone(fp.basis_ok({(2026, 9): 1.5}, ref))

    def test_level_years_weighted_by_analysts(self):
        rows = self._rows({"Zacks": {(2026, 12): (7.61, 21), (2027, 12): (15.46, 21)},
                           "Yahoo": {(2026, 12): (8.09, 43), (2027, 12): (17.64, 49)},
                           "Nasdaq": {(2026, 12): (6.57, 18), (2027, 12): (14.27, 19), (2028, 12): (20.64, 3)}})
        r0, r2 = rows[0], rows[2]
        w0 = (7.61 * 21 + 8.09 * 43) / 64
        self.assertAlmostEqual(r0["eps"][0], w0, places=4)
        self.assertEqual(r0["eps"][0], r0["eps"][1])
        self.assertEqual(r0["src"], {"Zacks": 7.61, "Yahoo": 8.09})
        self.assertEqual(sorted(r0["n"]), [21, 43])
        w1 = (15.46 * 21 + 17.64 * 49) / 70
        self.assertAlmostEqual(r2["eps"][0], 20.64 * w1 / 14.27, places=4)  # FY+2 = Nasdaq × k
        self.assertAlmostEqual(r2["rebase"], w1 / 14.27, places=6)
        self.assertEqual(r2["src"], {"Nasdaq": 20.64})
        self.assertEqual(r2["n"], [3])

    def test_fallback_nasdaq_raw(self):
        rows = self._rows({"Nasdaq": {(2026, 12): (6.57, 18), (2027, 12): (14.27, 19), (2028, 12): (20.64, 3)}})
        self.assertEqual(rows[0]["eps"], (6.57, 6.57))
        self.assertEqual(rows[2]["eps"], (20.64, 20.64))
        self.assertNotIn("rebase", rows[2])

    def test_nasdaq_without_overlap_keeps_raw(self):
        rows = self._rows({"Yahoo": {(2026, 12): (8.0, 40)}, "Nasdaq": {(2027, 12): (14.0, 10)}})
        self.assertEqual(rows[0]["eps"], (8.0, 8.0))
        self.assertEqual(rows[1]["eps"], (14.0, 14.0))

    def test_growth_uses_rebased_path(self):
        rows = self._rows({"Yahoo": {(2026, 12): (8.0, 40), (2027, 12): (16.0, 40)},
                           "Nasdaq": {(2026, 12): (6.0, 10), (2027, 12): (12.0, 10), (2028, 12): (15.0, 10)}})
        self.assertAlmostEqual(rows[2]["eps"][0], 20.0, places=6)  # 15 × (16/12)
        self.assertAlmostEqual(rows[3]["eps"][0], 25.0, places=6)  # 추정: 20 × (20/16)


if __name__ == "__main__":
    unittest.main()
