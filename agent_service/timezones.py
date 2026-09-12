"""UTC instants, IANA display zones, and airport-local schedule boundaries."""
import os
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc
AIRPORT_TIMEZONES = {
    'SFO': 'America/Los_Angeles', 'LAX': 'America/Los_Angeles', 'SEA': 'America/Los_Angeles',
    'LAS': 'America/Los_Angeles', 'JFK': 'America/New_York', 'BOS': 'America/New_York',
    'MIA': 'America/New_York', 'ATL': 'America/New_York', 'ORD': 'America/Chicago',
    'DFW': 'America/Chicago', 'AUS': 'America/Chicago', 'DEN': 'America/Denver',
    'PVG': 'Asia/Shanghai', 'SZX': 'Asia/Shanghai', 'HKG': 'Asia/Hong_Kong',
    'NRT': 'Asia/Tokyo', 'ICN': 'Asia/Seoul', 'SIN': 'Asia/Singapore',
    'LHR': 'Europe/London', 'CDG': 'Europe/Paris', 'FRA': 'Europe/Berlin',
    'DXB': 'Asia/Dubai', 'SYD': 'Australia/Sydney', 'YVR': 'America/Vancouver',
}


def valid_zone(value):
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValueError('Use a valid IANA timezone, such as America/New_York.') from None
    return value


def business_timezone():
    return valid_zone(os.getenv('BUSINESS_TIMEZONE', 'UTC'))


def utc_now():
    return datetime.now(UTC)


def as_utc(value):
    """MySQL drivers return naive TIMESTAMP values from our explicitly UTC sessions."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def utc_sql(value):
    return as_utc(value).strftime('%Y-%m-%d %H:%M:%S')


def utc_iso(value):
    return as_utc(value).isoformat().replace('+00:00', 'Z') if value else ''


def local_to_utc(value, zone):
    """Reject DST gaps and ambiguous wall times; accept an explicit matching offset."""
    zone = ZoneInfo(valid_zone(zone))
    wall = datetime.fromisoformat(value) if isinstance(value, str) else value
    if wall.tzinfo is not None:
        instant = wall.astimezone(UTC)
        if instant.astimezone(zone).replace(tzinfo=None) != wall.replace(tzinfo=None):
            raise ValueError('The explicit offset does not match the airport timezone.')
        return instant
    candidates = set()
    for fold in (0, 1):
        instant = wall.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if instant.astimezone(zone).replace(tzinfo=None) == wall:
            candidates.add(instant)
    if not candidates:
        raise ValueError('This local time does not exist because of daylight saving time.')
    if len(candidates) != 1:
        raise ValueError('This local time occurs twice. Enter an ISO time with an explicit UTC offset.')
    return candidates.pop()


def local_date_bounds(start, end, zone):
    # Calendar bounds use independent midnights, never a fixed 24-hour duration.
    return tuple(utc_sql(local_to_utc(datetime.combine(date.fromisoformat(str(day)), time.min), zone))
                 for day in (start, end))


def business_today():
    return utc_now().astimezone(ZoneInfo(business_timezone())).date()


def airport_timezone(code):
    return AIRPORT_TIMEZONES.get(str(code).upper(), 'UTC')


def display_time(value, zone='UTC'):
    return as_utc(value).astimezone(ZoneInfo(valid_zone(zone))).strftime('%Y-%m-%d %H:%M %Z') + f' ({zone})'


def departure_window_sql(start, end, airport=None, column='f.departure_date_time', airport_column='f.departure_airport'):
    if airport:
        return f'{column}>=%s AND {column}<%s', list(local_date_bounds(start, end, airport_timezone(airport)))
    # Each airport's calendar date is resolved to UTC in Python; no MySQL timezone tables required.
    groups = {}
    for code, zone in AIRPORT_TIMEZONES.items():
        groups.setdefault(zone, []).append(code)
    parts, args = [], []
    for zone, codes in groups.items():
        parts.append(f'({airport_column} IN ({",".join(["%s"] * len(codes))}) AND {column}>=%s AND {column}<%s)')
        args.extend([*codes, *local_date_bounds(start, end, zone)])
    codes = list(AIRPORT_TIMEZONES)
    parts.append(f'({airport_column} NOT IN ({",".join(["%s"] * len(codes))}) AND {column}>=%s AND {column}<%s)')
    args.extend([*codes, *local_date_bounds(start, end, 'UTC')])
    return '(' + ' OR '.join(parts) + ')', args
