"""update.py 단위 테스트: python3 scripts/test_update.py"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update  # noqa: E402


def test_bar_date_dst():
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


if __name__ == "__main__":
    test_bar_date_dst()
    print("ok")
