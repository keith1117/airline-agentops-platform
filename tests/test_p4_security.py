import json

from fastapi.testclient import TestClient
import pytest

import app as web
from agent_service import main
from agent_service.agentops import scoped_dashboard_rows
from agent_service.security import issue_identity
from agent_service.tool_registry import Tool, ToolAccessError, ToolRegistry


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(main.metrics, 'log_path', None)
    return TestClient(main.app)


def headers(role='customer', principal='owner@example.com', airline='United'):
    return {'X-Agent-Identity': issue_identity(role, principal, airline)}


def test_unsigned_tampered_and_customer_staff_requests_are_denied(api):
    assert api.get('/api/agentops/dashboard').status_code == 401
    assert api.get('/api/metrics',headers={'X-Agent-Identity': 'fake'}).status_code == 401
    assert api.get('/api/agentops/dashboard',headers=headers()).status_code == 403
    assert api.post('/api/eval/run',headers=headers('staff','admin'),json={}).status_code == 403


def test_body_cannot_override_authenticated_owner_or_airline(api):
    payload={'session_id':'same','customer_email':'other@example.com','message':'Show my tickets'}
    assert api.post('/api/agent/customer/chat',headers=headers(),json=payload).status_code == 403
    payload={'session_id':'same','staff_username':'admin','airline_name':'Other','message':'Show sales'}
    assert api.post('/api/agent/staff/chat',headers=headers('staff','admin'),json=payload).status_code == 403


def test_authenticated_chat_scopes_session_and_records_pending(api,monkeypatch):
    captured={}
    def chat(session,email,message):
        captured.update(session=session,email=email)
        return {'answer':'No matches','tool_calls':[]}
    monkeypatch.setattr(main.agent,'customer_chat',chat)
    payload={'session_id':'same','customer_email':'owner@example.com','message':'Find flights'}
    assert api.post('/api/agent/customer/chat',headers=headers(),json=payload).status_code == 200
    assert captured['session'] != 'same'
    assert captured['session'] != main.scoped_session('customer','other@example.com','same')


def test_old_booking_endpoint_cannot_issue_ticket(api):
    payload={'booking_intent_id':1,'customer_email':'owner@example.com','idempotency_key':'old'}
    assert api.post('/api/agent/confirm-booking',headers=headers(),json=payload).status_code == 410
    assert api.post('/api/agent/confirm-cancellation',headers=headers(),json={'ticket_id':1,'customer_email':'owner@example.com'}).status_code == 422


def test_registry_blocks_human_actions_in_every_runtime():
    registry=ToolRegistry()
    registry.register(Tool('cancel','Cancel',['customer'],lambda: pytest.fail('Unsafe handler executed'),risk='human_confirmed'))
    with pytest.raises(ToolAccessError,match='confirmation'):
        registry.call('customer','cancel')


def test_csrf_is_required_and_cannot_be_bypassed_with_forged_token(monkeypatch):
    monkeypatch.setattr(web,'purchase_action',lambda *args: pytest.fail('Purchase executed'))
    client=web.app.test_client()
    with client.session_transaction() as session:
        session.update(role='customer',email='owner@example.com',csrf_token='valid')
    assert client.post('/customer/purchase',data={'action_id':'x'}).status_code == 400
    assert client.post('/customer/purchase',data={'action_id':'x','csrf_token':'fake'}).status_code == 400
    assert client.get('/register/staff').status_code == 200


def test_staff_dashboard_hides_customer_content_and_other_airlines():
    row={'role':'customer','principal':'private@example.com','user_message':'private request',
         'final_answer':'private answer','reasoning':'private reasoning',
         'tool_calls':json.dumps([{'name':'search_flights','args':{'airline_name':'United'}}])}
    assert scoped_dashboard_rows([row],'Other') == []
    result=scoped_dashboard_rows([row],'United')[0]
    assert 'private' not in result['principal']+result['user_message']+result['final_answer']+result['reasoning']
