from datetime import datetime, date, time, timezone, timedelta
from zoneinfo import ZoneInfo

MERCHANT_TIMEZONE = ZoneInfo("Africa/Nairobi")


def ensure_utc_datetime(value: datetime | None) -> datetime | None:
    """
    Return a timezone-aware UTC datetime.

    Some DB drivers can return naive datetimes even when the ORM column is
    declared with timezone=True. We treat naive values as UTC to avoid runtime
    comparison/arithmetic errors in request paths.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def utc_to_merchant_date(value: datetime | None) -> date | None:
    """
    Convert a UTC datetime to the merchant's local business date.
    """
    value = ensure_utc_datetime(value)
    if value is None:
        return None
    return value.astimezone(MERCHANT_TIMEZONE).date()


def merchant_today() -> date:
    """
    Return today's date in the merchant timezone.
    """
    return datetime.now(timezone.utc).astimezone(MERCHANT_TIMEZONE).date()


def merchant_date_range(start_date: date, end_date: date | None = None) -> tuple[datetime, datetime]:
    """
    Convert merchant-local business dates into a UTC datetime range.
    End is exclusive, which is safer for DB queries.
    """
    if end_date is None:
        end_date = start_date

    start_local = datetime.combine(start_date, time.min, tzinfo=MERCHANT_TIMEZONE)
    end_local_exclusive = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=MERCHANT_TIMEZONE)

    return (
        start_local.astimezone(timezone.utc),
        end_local_exclusive.astimezone(timezone.utc),
    )