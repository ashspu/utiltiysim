import json
from pathlib import Path

import jsonschema
import pytest
from test_world_contacts import command as contact_command
from test_world_customer_finance import command as finance_command
from test_world_customer_finance import delivery
from test_world_network_faults import command as fault_command
from test_world_network_faults import world
from test_world_occupancy import schedule as occupancy_command

from utilsim.world import World, contacts, customer_finance, network_faults, occupancy, sentiment


def configure(w, **overrides):
    return sentiment.configure(w, 'sentiment-setup', {**sentiment.DEFAULTS, 'enabled': True, **overrides}, ['P1'])


def news(w, identity='news', **overrides):
    with w.read_db() as db:
        meta = w.metadata(db)
    return {'schemaVersion': sentiment.VERSION, 'commandId': identity, 'environmentId': meta['environment'],
            'worldFingerprint': meta['fingerprint'], 'actorId': 'world-admin', 'expectedRevision': 0,
            'effectiveDate': meta['through'], 'action': 'schedule', 'reason': 'Public-news scenario',
            'causalReference': 'scenario', 'eventDate': '2026-01-03', 'trustChange': -60,
            'headline': 'Repeated utility problems reported', **overrides}


def test_news_is_dated_bounded_recovers_and_does_not_fabricate_contacts(tmp_path):
    w = world(tmp_path)
    configure(w, initialTrust=100, communityInfluence=1, recoveryDays=30)
    contacts.command(w, contact_command(w))
    command = news(w)
    receipt = sentiment.command(w, command)
    w.advance('2026-01-03')
    assert sentiment.inspect(w)['communityTrust'] == 100
    w.advance('2026-01-04')
    affected = sentiment.inspect(w, 'P1')
    assert affected['householdTrust'] < 50 and affected['communityTrust'] < 50
    assert contacts.inspect(w)['items'] == []
    assert sentiment.command(World(w.path), command) == receipt
    w.advance('2026-02-01')
    assert sentiment.inspect(w)['communityTrust'] > affected['communityTrust']
    assert all(0 <= r['community'] <= 1 for r in sentiment.inspect(w)['history'])
    assert sum('NEWS-' in json.dumps(r['payload']['newsIds']) for r in sentiment.inspect(w, limit=50)['history']) == 1


def test_real_experience_amplifies_repeats_but_envelope_and_physics_stay_unchanged(tmp_path):
    base, reactive = (world(tmp_path, name) for name in ('base', 'reactive'))
    configure(reactive, initialTrust=0, experienceImpact=1, maxContactMultiplier=5)
    for w in (base, reactive):
        contacts.command(w, contact_command(w, repeatAfterDays=3, maxContacts=2, deliveryDelaySeconds=0))
        network_faults.command(w, fault_command(w))
        w.advance('2026-01-11')
    assert len(contacts.ready(base)['items']) == 2
    intents = contacts.ready(reactive)['items']
    assert len(intents) == 10
    schema = json.loads((Path(__file__).parents[1] / 'schemas/customer-contact-intent-1.schema.json').read_text())
    for row in intents:
        jsonschema.validate(row['intent'], schema)
        assert not any(k in row['intent'] for k in ('frustration', 'policy', 'newsIds', 'faultId'))
    assert base.export_v2('2026-01-01', '2026-01-11') == reactive.export_v2('2026-01-01', '2026-01-11')
    with reactive.read_db() as db:
        meta = reactive.metadata(db)
        derived = sentiment.contact_policy(db, meta, 'P1', {'noticeProbabilityPerDay': .8, 'repeatAfterDays': 1, 'maxContacts': 9})
    assert derived == {'noticeProbabilityPerDay': 1, 'repeatAfterDays': 1, 'maxContacts': 10}


def test_missing_meter_and_hidden_fault_do_not_create_frustration(tmp_path):
    w = world(tmp_path, annual_meter_failure=1)
    configure(w, initialTrust=100)
    # An enabled redundant path prevents an experienced loss from a hidden edge fault.
    other = world(tmp_path, 'redundant', loop=True)
    configure(other, initialTrust=100)
    network_faults.command(other, fault_command(other))
    for candidate in (w, other):
        candidate.advance('2026-01-04')
        assert sentiment.inspect(candidate, 'P1')['householdTrust'] == 100


def test_only_actually_received_late_bills_affect_mood_once(tmp_path):
    w = world(tmp_path)
    configure(w, initialTrust=100, lateBillImpact=.4, communityInfluence=0, recoveryDays=365)
    customer_finance.command(w, finance_command(w, paymentProbability=0))
    w.advance('2026-01-02')
    assert sentiment.inspect(w, 'P1')['householdTrust'] == 100
    with pytest.raises(ValueError, match='not yet'):
        customer_finance.receive_delivery(w, delivery(w, deliveredAt='2026-01-03T00:00:00Z'))
    message = delivery(w)
    customer_finance.receive_delivery(w, message)
    w.advance('2026-01-03')
    assert sentiment.inspect(w, 'P1')['householdTrust'] == pytest.approx(60)
    customer_finance.receive_delivery(World(w.path), message)
    customer_finance.receive_delivery(w, delivery(w, 'on-time-learned-later', invoiceId='INV-2', deliveredAt='2026-01-01T00:00:00Z'))
    w.advance('2026-01-04')
    view = sentiment.inspect(w, 'P1')
    assert view['householdTrust'] > 60
    assert sum(r['payload']['lateDeliveredBills'] for r in view['history']) == 1


def test_new_occupants_do_not_inherit_prior_household_mood(tmp_path):
    w = world(tmp_path)
    configure(w, initialTrust=100, communityInfluence=0, experienceImpact=.5)
    fault = network_faults.command(w, fault_command(w))
    w.advance('2026-01-02')
    assert sentiment.inspect(w, 'P1')['householdTrust'] == 50
    network_faults.command(w, fault_command(w, 'restore', 'restore', expectedRevision=1, faultId=fault['faultId']))
    occupancy.command(w, occupancy_command(w, effectiveDate='2026-01-02', occupied=True, occupants=3))
    w.advance('2026-01-03')
    assert sentiment.inspect(w, 'P1')['householdTrust'] == 100


def test_atomic_rollback_restart_and_same_day_news_pagination(tmp_path, monkeypatch):
    expected, interrupted = (world(tmp_path, name) for name in ('expected', 'interrupted'))
    for w in (expected, interrupted):
        configure(w)
        for i in range(3):
            sentiment.command(w, news(w, 'news-' + str(i), expectedRevision=i, eventDate='2026-01-01'))
    def failure(*args):
        raise RuntimeError('Stop after sentiment writes')
    with monkeypatch.context() as patch:
        patch.setattr(contacts, 'daily', failure)
        with pytest.raises(RuntimeError, match='Stop after'):
            interrupted.advance('2026-01-02')
    assert sentiment.inspect(interrupted)['history'] == []
    assert not any(n['applied'] for n in sentiment.inspect(interrupted)['news'])
    expected.advance('2026-01-04')
    resumed = World(interrupted.path)
    resumed.advance('2026-01-02')
    resumed.advance('2026-01-04')
    assert sentiment.inspect(expected) == sentiment.inspect(resumed)
    first = sentiment.inspect(resumed, limit=2)
    second = sentiment.inspect(resumed, limit=2, news_before=first['nextNewsBefore'])
    assert len(first['news']) == 2 and len(second['news']) == 1
    assert {n['id'] for n in first['news']}.isdisjoint(n['id'] for n in second['news'])
