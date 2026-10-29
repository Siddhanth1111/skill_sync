from datetime import date

from app.services.dates import merge_periods, parse_date, total_years, years_of_experience
from app.schemas import Role

TODAY = date(2025, 6, 15)


def test_parse_formats():
    assert parse_date("Jan 2020", TODAY) == date(2020, 1, 1)
    assert parse_date("January 2020", TODAY) == date(2020, 1, 1)
    assert parse_date("01/2020", TODAY) == date(2020, 1, 1)
    assert parse_date("2020-03", TODAY) == date(2020, 3, 1)
    assert parse_date("2020", TODAY) == date(2020, 1, 1)
    assert parse_date("2020", TODAY, is_end=True) == date(2020, 12, 1)
    assert parse_date("Present", TODAY) == date(2025, 6, 1)
    assert parse_date("garbage", TODAY) is None
    assert parse_date("13/2020", TODAY) is None


def test_future_dates_clamped():
    assert parse_date("Dec 2030", TODAY) == date(2025, 6, 1)


def test_overlap_merged_not_double_counted():
    a = (date(2018, 1, 1), date(2020, 12, 1))   # 3 years
    b = (date(2020, 6, 1), date(2022, 12, 1))   # overlaps a by 7 months
    assert merge_periods([b, a]) == [(date(2018, 1, 1), date(2022, 12, 1))]
    assert total_years([a, b]) == 5.0


def test_adjacent_months_merge_and_gaps_do_not():
    a = (date(2019, 1, 1), date(2019, 6, 1))
    b = (date(2019, 7, 1), date(2019, 12, 1))
    assert total_years([a, b]) == 1.0
    c = (date(2021, 1, 1), date(2021, 12, 1))
    assert total_years([a, c]) == 1.5


def test_years_of_experience_from_roles():
    roles = [Role(title="x", start="2018-01", end="2020-12"), Role(title="y", start="2020-06", end="present"),
             Role(title="no start")]
    assert years_of_experience(roles, TODAY) == 7.5  # Jan 2018 .. Jun 2025 inclusive = 90 months
