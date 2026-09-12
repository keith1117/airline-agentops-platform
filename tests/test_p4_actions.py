import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

import app as web_app
from agent_service import actions
from agent_service.db import get_conn, ensure_agent_schema


def test_action_pages_enforce_role(monkeypatch):
    monkeypatch.setattr(web_app, 'list_actions', lambda **kwargs: [])
    client = web_app.app.test_client()
    assert client.get('/customer/actions').status_code == 302
    assert client.get('/staff/actions').status_code == 302
    with client.session_transaction() as session:
        session.update(role='customer', email='customer@example.com')
    assert client.get('/customer/actions').status_code == 200
    assert client.get('/staff/actions').status_code == 302
    with client.session_transaction() as session:
        session.update(role='staff', airline='United')
    assert client.get('/customer/actions').status_code == 302
    assert client.get('/staff/actions').status_code == 200


def test_record_handoffs_only_persists_actual_previews(monkeypatch):
    calls = []
    monkeypatch.setattr(actions, 'create_action', lambda *args: calls.append(args) or 'action-id')
    assert actions.record_handoffs({'answer': 'No results'}, 'owner', 'session') == {'answer': 'No results'}
    assert calls == []
    result = actions.record_handoffs({'pending_cancellation': {'ticket_id': 1}}, 'owner', 'session')
    assert result['pending_cancellation']['action_id'] == 'action-id'
    assert calls[0][:2] == ('owner', 'CANCELLATION')


@pytest.fixture
def inventory():
    if os.getenv('RUN_P4_ACTIONS') != '1':
        pytest.skip('Set RUN_P4_ACTIONS=1 for MySQL transaction and concurrency tests.')
    ensure_agent_schema(retries=1)
    token = uuid.uuid4().hex[:8]
    email = f'p4-{token}@demo.local'
    airline = f'P4-{token}'
    dep = (datetime.now() + timedelta(days=60)).replace(microsecond=0)
    flight = dict(airline_name=airline, flight_number='P4TEST', departure_date_time=str(dep),
                  departure_airport='SFO', arrival_airport='LAX', base_price=100)
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute('INSERT INTO Airline(name) VALUES(%s)', (airline,))
        cur.execute("INSERT INTO Customer(email,name,password) VALUES(%s,'P4 Tester','1234')", (email,))
        cur.execute("INSERT IGNORE INTO Airport(code,city) VALUES('SFO','San Francisco'),('LAX','Los Angeles')")
        cur.execute("INSERT INTO Airplane(id_number,airline_name,seats) VALUES('P4',%s,1)", (airline,))
        cur.execute("INSERT INTO Flight(airline_name,flight_number,departure_date_time,arrival_date_time,base_price,departure_airport,arrival_airport,airplane_id_number,status) "
                    "VALUES(%s,'P4TEST',%s,%s,100,'SFO','LAX','P4','ON_TIME')", (airline,dep,dep+timedelta(hours=2)))
    conn.commit()
    conn.close()
    yield email, flight
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute('DELETE e FROM agent_action_events e JOIN agent_actions a ON a.id=e.action_id WHERE a.airline_name=%s', (airline,))
        for table in ['agent_actions','ticket_cancellations','Ticket','Flight','Airplane']:
            cur.execute(f'DELETE FROM {table} WHERE airline_name=%s', (airline,))
        cur.execute('DELETE FROM Customer WHERE email=%s', (email,))
        cur.execute('DELETE FROM Airline WHERE name=%s', (airline,))
    conn.commit()
    conn.close()


PAYMENT = dict(name_on_card='P4 Tester',card_number='4111111111111111',card_type='Credit',expiration_date='2035-01-01')


def _booking(email, flight):
    action_id = actions.create_action(email, 'BOOKING_HANDOFF', flight)
    actions.decide_action(action_id, email, 'checkout')
    return action_id


def test_checkout_is_atomic_idempotent_and_does_not_store_card(inventory):
    email, flight = inventory
    action_id = _booking(email, flight)
    with pytest.raises(actions.ActionError, match='account'):
        actions.purchase_action(action_id, 'another@example.com', PAYMENT)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: actions.purchase_action(action_id,email,PAYMENT), range(2)))
    assert results[0]['ticket_id'] == results[1]['ticket_id']
    queue = actions.list_actions(customer_email=email)
    assert queue[0]['status'] == 'CONFIRMED'
    assert [e['event'] for e in queue[0]['events']] == ['PENDING','CHECKOUT_STARTED','CONFIRMED']
    conn=get_conn()
    with conn.cursor() as cur:
        cur.execute('SELECT card_number FROM Ticket WHERE ticket_ID=%s', (results[0]['ticket_id'],))
        assert cur.fetchone()['card_number'] == 'MOCK-PAYMENT'
    conn.close()


def test_last_seat_cannot_be_sold_twice(inventory):
    email,flight=inventory
    ids=[_booking(email,flight),_booking(email,flight)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda aid: actions.purchase_action(aid,email,PAYMENT),ids))
    assert sum('ticket_id' in r for r in results) == 1
    assert sum(r.get('error') == 'Flight is sold out.' for r in results) == 1


def test_cancel_confirm_and_reject_are_persistent(inventory):
    email,flight=inventory
    ticket=actions.purchase_action(_booking(email,flight),email,PAYMENT)['ticket_id']
    preview=actions.create_cancellation(email,ticket)
    actions.decide_action(preview,email,'reject')
    with pytest.raises(actions.ActionError,match='rejected'):
        actions.decide_action(preview,email,'confirm')
    preview=actions.create_cancellation(email,ticket)
    first=actions.decide_action(preview,email,'confirm')
    second=actions.decide_action(preview,email,'confirm')
    assert first == second
    assert first['refund_amount'] == 40
    assert actions.list_actions(airline_name='another-airline') == []


def test_expired_and_changed_terms_cannot_execute(inventory):
    email,flight=inventory
    expired=_booking(email,flight)
    conn=get_conn()
    with conn.cursor() as cur:
        cur.execute('UPDATE agent_actions SET expires_at=DATE_SUB(CURRENT_TIMESTAMP,INTERVAL 1 MINUTE) WHERE id=%s',(expired,))
    conn.commit();conn.close()
    with pytest.raises(actions.ActionError,match='expired'):
        actions.purchase_action(expired,email,PAYMENT)
    assert actions.list_actions(customer_email=email)[0]['status'] == 'EXPIRED'
    ticket=actions.purchase_action(_booking(email,flight),email,PAYMENT)['ticket_id']
    preview=actions.create_cancellation(email,ticket)
    conn=get_conn()
    with conn.cursor() as cur:
        cur.execute("UPDATE Flight SET status='DELAYED' WHERE airline_name=%s",(flight['airline_name'],))
    conn.commit();conn.close()
    assert 'terms changed' in actions.decide_action(preview,email,'confirm')['error']
    assert actions.list_actions(customer_email=email,status='FAILED')[0]['id'] == preview


def test_invalid_payment_leaves_no_ticket_and_can_retry(inventory):
    email,flight=inventory
    action_id=_booking(email,flight)
    with pytest.raises(actions.ActionError,match='match'):
        actions.purchase_action(action_id,email,{**PAYMENT,'name_on_card':'Another Name'})
    with pytest.raises(actions.ActionError,match=r'^Invalid card number\.$'):
        actions.purchase_action(action_id,email,{**PAYMENT,'card_number':'123456789012'})
    assert actions.list_actions(customer_email=email)[0]['status'] == 'CHECKOUT_STARTED'
    assert actions.purchase_action(action_id,email,PAYMENT)['ticket_id']
