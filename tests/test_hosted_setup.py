import json
import uuid

from fastapi.testclient import TestClient
from test_hosted_worlds import TOKEN, headers, setup  # noqa: F401

from utilsim.hosted import setup as physical_setup
from utilsim.hosted.server import create_app


def configured(value):
    return {**value, 'configuration': {**value['configuration'], 'schemaVersion': physical_setup.VERSION,
        'physical': {'customerContacts': {'active': True, 'noticeProbabilityPerDay': .8},
                     'householdFinance': {'enabled': True, 'cashCents': 10000, 'essentialReserveCents': 2000,
                                          'maxPaymentCents': 3000, 'paymentProbability': .6},
                     'householdCashflow': {'enabled': True, 'incomeCents': 1000, 'incomeIntervalDays': 1,
                                           'expenseCents': 400, 'expenseIntervalDays': 1}}}}


def test_initial_customer_settings_apply_and_cashflow_survives_restart(setup):  # noqa: F811
    root, template, value, snapshot = setup
    source = (template / 'source-snapshot.json').read_bytes()
    client = TestClient(create_app(root, TOKEN))
    value = configured(value)
    response = client.post('/hosted/worlds', json=value, headers=headers())
    assert response.status_code == 200, response.text
    created = response.json()
    assert created['initialization'] == {'state': 'complete', 'eligibleHouseholds': 1, 'appliedCommands': 3, 'totalCommands': 3}
    base = '/hosted/worlds/' + created['id']
    premise = snapshot['premises'][0]['id']
    customer = base + '/premises/' + premise + '/customer'
    initial = client.get(customer, headers=headers()).json()
    assert initial['finance']['cashCents'] == 10000
    assert initial['finance']['policy']['paymentProbability'] == .6
    assert initial['cashflow']['policy']['income']['amountCents'] == 1000
    assert client.post(base + '/advance', json={'through': '2026-07-17'}, headers=headers()).status_code == 200
    restarted = TestClient(create_app(root, TOKEN))
    state = restarted.get(customer, headers=headers()).json()
    assert state['finance']['cashCents'] == 11200
    assert len(state['cashflow']['history']) == 2
    assert all(day['incomeCreditedCents'] == 1000 and day['expensePaidCents'] == 400 for day in state['cashflow']['history'])
    replay = restarted.post('/hosted/worlds', json=value, headers=headers()).json()
    assert replay['id'] == created['id'] and replay['configuration'] == created['configuration']
    assert restarted.get(customer, headers=headers()).json()['finance']['cashCents'] == 11200  # no cash reset
    assert restarted.get(customer, headers=headers(user='other')).status_code == 404
    assert (template / 'source-snapshot.json').read_bytes() == source
    with restarted.app.state.library.library.world(created['id']).read_db() as db:
        assert json.loads(db.execute("SELECT value FROM meta WHERE key='contactPolicy'").fetchone()[0])['noticeProbabilityPerDay'] == .8


def test_partial_initialization_recovers_before_any_advance(setup, monkeypatch):  # noqa: F811
    root, _, value, _ = setup
    client = TestClient(create_app(root, TOKEN))
    value = configured(value)
    original = physical_setup.customer_finance.command
    def crash_after_commit(*args):
        original(*args)
        raise OSError('Simulated response lost after finance profile commit')
    monkeypatch.setattr(physical_setup.customer_finance, 'command', crash_after_commit)
    response = client.post('/hosted/worlds', json=value, headers=headers())
    assert response.status_code == 503
    listing = client.get('/hosted/worlds', headers=headers()).json()
    pending = listing['worlds'][0]
    assert pending['state'] == 'configuring' and not pending['available']
    assert pending['initialization']['appliedCommands'] == 1
    base = '/hosted/worlds/' + pending['id']
    assert client.post(base + '/advance', json={'through': '2026-07-16'}, headers=headers()).status_code == 422
    monkeypatch.setattr(physical_setup.customer_finance, 'command', original)
    restarted = TestClient(create_app(root, TOKEN))
    result = restarted.post('/hosted/worlds', json=value, headers=headers())
    assert result.status_code == 200, result.text
    assert result.json()['available'] and result.json()['id'] == pending['id']
    with restarted.app.state.library.library.world(pending['id']).read_db() as db:
        assert db.execute('SELECT COUNT(*) FROM customer_finance_profiles').fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM events WHERE type='CustomerFinanceConfigured'").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM events WHERE type='CustomerCashflowConfigured'").fetchone()[0] == 1


def test_schema_sliders_and_rejection_of_unsupported_or_invalid_fields(setup):  # noqa: F811
    root, _, value, _ = setup
    client = TestClient(create_app(root, TOKEN))
    response = client.get('/hosted/sources/test-map/configuration', params={'sourceRevision': value['sourceRevision']}, headers=headers()).json()
    assert response['configurationVersion'] == physical_setup.VERSION
    control = response['schemas']['physical']['properties']['householdFinance']['properties']['cashCents']['x-control']
    assert control['kind'] == 'slider' and control['allowExactInput'] and control['effect']
    assert 'housingAge' in response['currentAdapterFixed']  # explicit gap, not claimed effect
    for config in ({'physical': {}}, {'schemaVersion': 'unknown'},
                   {'schemaVersion': physical_setup.VERSION, 'physical': {'staffing': {}}},
                   {'schemaVersion': physical_setup.VERSION, 'physical': {'householdFinance': {'cashCents': -1}}},
                   {'schemaVersion': physical_setup.VERSION, 'physical': {'householdFinance': {'paymentProbability': True}}},
                   {'schemaVersion': physical_setup.VERSION, 'physical': {'householdCashflow': {'enabled': True}}}):
        result = client.post('/hosted/worlds', json={**value, 'commandId': str(uuid.uuid4()), 'configuration': config}, headers=headers())
        assert result.status_code == 422, result.text
    assert client.get('/hosted/worlds', headers=headers()).json()['total'] == 0


def test_bounded_batches_continue_exact_creation_command(setup, monkeypatch):  # noqa: F811
    root, _, value, _ = setup
    monkeypatch.setattr(physical_setup, 'MAX_NEW_COMMANDS', 1)
    client = TestClient(create_app(root, TOKEN))
    value = configured(value)
    stages = [client.post('/hosted/worlds', json=value, headers=headers()).json() for _ in range(3)]
    assert len({stage['id'] for stage in stages}) == 1
    assert [stage['initialization']['appliedCommands'] for stage in stages] == [1, 2, 3]
    assert [stage['state'] for stage in stages] == ['configuring', 'configuring', 'complete']
    assert [stage['available'] for stage in stages] == [False, False, True]


def test_time_budget_stops_between_atomic_commands(setup, monkeypatch):  # noqa: F811
    root, _, value, _ = setup
    ticks = iter([0, 9])
    monkeypatch.setattr(physical_setup, 'monotonic', lambda: next(ticks, 9))
    client = TestClient(create_app(root, TOKEN))
    result = client.post('/hosted/worlds', json=configured(value), headers=headers()).json()
    assert result['state'] == 'configuring' and not result['available']
    assert result['initialization']['appliedCommands'] == 1
