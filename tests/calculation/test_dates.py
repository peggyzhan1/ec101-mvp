from datetime import date

import pytest

from ec101.calculation.engine import parse_calc_date, release_cutoff, release_reason


def test_parse_calc_date_defaults_to_today():
    assert parse_calc_date(None) == date.today().isoformat()


def test_parse_calc_date_rejects_non_iso_format():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        parse_calc_date("2026/09/22")


def test_release_cutoff_is_t_minus_two_midnight():
    assert release_cutoff("2026-09-22") == "2026-09-20 00:00:00"


@pytest.mark.parametrize(
    ("status", "order_time", "expected", "reason"),
    [
        ("处理中", "2026-09-19 23:59:59", False, "订单状态：处理中"),
        ("已完成", None, False, "下单时间缺失"),
        ("已完成", "2026-09-20 00:00:00", False, "未达 T-2"),
        ("已完成", "2026-09-19 23:59:59", True, "已完成且达到 T-2"),
    ],
)
def test_release_reason_boundaries(status, order_time, expected, reason):
    assert release_reason(status, order_time, "2026-09-20 00:00:00") == (expected, reason)
