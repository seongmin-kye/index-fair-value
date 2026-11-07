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


if __name__ == "__main__":
    unittest.main()
