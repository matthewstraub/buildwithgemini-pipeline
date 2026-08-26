"""US Federal Holiday calendar and business day math utilities."""

from datetime import date, timedelta
from typing import Set


def get_us_holidays(year: int) -> Set[date]:
    """Return set of US federal holiday dates for a given year."""
    holidays: Set[date] = set()

    # Fixed date holidays
    # New Year's Day
    holidays.add(date(year, 1, 1))
    # Juneteenth
    holidays.add(date(year, 6, 19))
    # Independence Day
    holidays.add(date(year, 7, 4))
    # Veterans Day
    holidays.add(date(year, 11, 11))
    # Christmas
    holidays.add(date(year, 12, 25))

    # Nth weekday of month helpers
    def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
        # weekday: 0=Mon, 6=Sun
        first_day = date(year, month, 1)
        offset = (weekday - first_day.weekday()) % 7
        return first_day + timedelta(days=offset + (n - 1) * 7)

    def last_weekday(year: int, month: int, weekday: int) -> date:
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        last_day = next_month - timedelta(days=1)
        offset = (last_day.weekday() - weekday) % 7
        return last_day - timedelta(days=offset)

    # MLK Jr. Day: 3rd Monday in January
    holidays.add(nth_weekday(year, 1, 0, 3))
    # Washington's Birthday: 3rd Monday in February
    holidays.add(nth_weekday(year, 2, 0, 3))
    # Memorial Day: Last Monday in May
    holidays.add(last_weekday(year, 5, 0))
    # Labor Day: 1st Monday in September
    holidays.add(nth_weekday(year, 9, 0, 1))
    # Columbus Day: 2nd Monday in October
    holidays.add(nth_weekday(year, 10, 0, 2))
    # Thanksgiving: 4th Thursday in November
    holidays.add(nth_weekday(year, 11, 3, 4))

    # Adjust for weekend observed rules (if holiday falls on Sat -> Fri observed; Sun -> Mon observed)
    observed_holidays: Set[date] = set(holidays)
    for h in list(holidays):
        if h.weekday() == 5:  # Saturday -> Friday before
            observed_holidays.add(h - timedelta(days=1))
        elif h.weekday() == 6:  # Sunday -> Monday after
            observed_holidays.add(h + timedelta(days=1))

    return observed_holidays


def is_business_day(d: date) -> bool:
    """Return True if `d` is a Monday-Friday and not a US federal holiday."""
    if d.weekday() >= 5:  # 5=Sat, 6=Sun
        return False
    holidays = get_us_holidays(d.year)
    return d not in holidays


def add_business_days(start_date: date, num_days: int) -> date:
    """Add `num_days` business days to `start_date`."""
    current = start_date
    added = 0
    while added < num_days:
        current += timedelta(days=1)
        if is_business_day(current):
            added += 1
    return current


def count_business_days_between(start_date: date, end_date: date) -> int:
    """
    Count number of business days between start_date (exclusive) and end_date (inclusive).
    If start_date >= end_date, returns 0.
    """
    if start_date >= end_date:
        return 0
    current = start_date + timedelta(days=1)
    count = 0
    while current <= end_date:
        if is_business_day(current):
            count += 1
        current += timedelta(days=1)
    return count
