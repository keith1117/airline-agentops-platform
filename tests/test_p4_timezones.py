from datetime import datetime, date, timedelta, timezone
import os
import time

import pytest

from agent_service import timezones as tz
from agent_service.reporting import resolve_sales_window, aggregate_sales
from agent_service.db import get_conn
import app as web


def test_airport_and_traveler_display_preserve_same_utc_instant():
    instant=tz.local_to_utc('2027-06-08T09:30','America/Los_Angeles')
    assert tz.utc_iso(instant) == '2027-06-08T16:30:00Z'
    assert '09:30 PDT' in tz.display_time(instant,tz.airport_timezone('SFO'))
    assert '12:30 EDT' in tz.display_time(instant,'America/New_York')
    assert '2027-06-09 00:30' in tz.display_time(instant,'Asia/Shanghai')
    assert tz.utc_iso(tz.as_utc('2027-06-08T12:30:00-04:00')) == tz.utc_iso(instant)


def test_dst_gaps_and_ambiguous_schedule_input_require_resolution():
    with pytest.raises(ValueError,match='does not exist'):
        tz.local_to_utc('2026-03-08T02:30','America/New_York')
    with pytest.raises(ValueError,match='occurs twice'):
        tz.local_to_utc('2026-11-01T01:30','America/New_York')
    assert tz.utc_iso(tz.local_to_utc('2026-11-01T01:30-04:00','America/New_York')) == '2026-11-01T05:30:00Z'
    assert tz.utc_iso(tz.local_to_utc('2026-11-01T01:30-05:00','America/New_York')) == '2026-11-01T06:30:00Z'
    with pytest.raises(ValueError,match='offset'):
        tz.local_to_utc('2026-11-01T01:30+08:00','America/New_York')


def test_airport_local_days_use_23_or_25_hour_utc_windows():
    spring=tz.local_date_bounds('2026-03-08','2026-03-09','America/New_York')
    autumn=tz.local_date_bounds('2026-11-01','2026-11-02','America/New_York')
    assert tz.as_utc(spring[1])-tz.as_utc(spring[0]) == timedelta(hours=23)
    assert tz.as_utc(autumn[1])-tz.as_utc(autumn[0]) == timedelta(hours=25)
    _,args=tz.departure_window_sql('2026-06-01','2026-06-02','SFO')
    assert args == ['2026-06-01 07:00:00','2026-06-02 07:00:00']


def test_reporting_calendar_is_independent_of_machine_and_user_timezone(monkeypatch):
    monkeypatch.setenv('BUSINESS_TIMEZONE','America/New_York')
    monkeypatch.setattr(tz,'utc_now',lambda:datetime(2027,1,1,2,tzinfo=timezone.utc))
    original=os.environ.get('TZ')
    try:
        windows=[]
        for zone in ['Asia/Shanghai','America/Los_Angeles','UTC']:
            os.environ['TZ']=zone
            time.tzset()
            windows.append(resolve_sales_window('this_year'))
        assert windows[0] == windows[1] == windows[2]
        assert windows[0]['start_date'] == '2026-01-01'
        assert windows[0]['start_utc'] == '2026-01-01 05:00:00'
        assert windows[0]['end_utc'] == '2027-01-01 05:00:00'
    finally:
        if original is None:
            os.environ.pop('TZ',None)
        else:
            os.environ['TZ']=original
        time.tzset()


def test_sales_grouping_uses_business_month_at_utc_boundary():
    rows=[{'purchase_date_time':'2026-06-01 02:00:00','base_price':100},
          {'purchase_date_time':'2026-06-01 05:00:00','base_price':200}]
    totals=aggregate_sales(rows,zone='America/New_York')
    assert [(row['month'],row['tickets'],float(row['estimated_revenue'])) for row in totals] == [('2026-05',1,100),('2026-06',1,200)]


def test_timezone_preference_validates_iana_and_persists_override():
    client=web.app.test_client()
    with client.session_transaction() as session:
        session['csrf_token']='token'
    assert client.post('/preferences/timezone',data={'csrf_token':'token','timezone':'Not/AZone'}).status_code == 400
    assert client.post('/preferences/timezone',data={'csrf_token':'token','timezone':'Asia/Shanghai','manual':'1'}).status_code == 200
    with client.session_transaction() as session:
        assert session['timezone'] == 'Asia/Shanghai'
        assert session['timezone_manual'] is True


@pytest.mark.skipif(os.getenv('RUN_P4_ACTIONS')!='1',reason='Requires Docker MySQL')
def test_mysql_and_python_utc_clocks_agree():
    conn=get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT @@session.time_zone AS zone, NOW() AS now_utc')
            row=cur.fetchone()
        assert row['zone'] == '+00:00'
        assert abs((tz.utc_now()-tz.as_utc(row['now_utc'])).total_seconds()) < 5
    finally:
        conn.close()


def test_timestamp_normalizer_preserves_offset_instant():
    from agent_service.react_agent import _normalize_datetime
    assert _normalize_datetime("2027-06-08T12:30:00-04:00") == "2027-06-08 16:30:00"
