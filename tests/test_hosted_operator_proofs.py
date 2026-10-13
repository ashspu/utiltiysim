"""Authenticated HTTP proof binding and explicit invoice cohort projection."""
import hashlib
import json
import subprocess
import uuid

import pytest
from fastapi.testclient import TestClient
from test_hosted_machine import MACHINE_KEY
from test_hosted_operator import CONTROL_TOKEN, OPERATOR_TOKEN, post
from test_hosted_operator import hosted as hosted
from test_hosted_worlds import TOKEN, headers
from test_hosted_worlds import setup as setup

from utilsim.hosted.operator import ENVELOPE, browser_request_hash
from utilsim.hosted.server import create_app


def private_hash(value, **options):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False, **options)
    return hashlib.sha256(encoded.encode()).hexdigest()


def refusal(hosted, status=403, proof_change=None, envelope_change=None, request_change=None, marked=True):
    def answer(trusted, original):
        result = {key: original[key] for key in ENVELOPE}
        result['error'] = 'Actual in-scope permanent business refusal'
        if marked:
            hashed = request_change(trusted) if request_change else trusted
            result['rejection'] = {'commandId': trusted.get('commandId'), 'requestHash': private_hash(hashed),
                'status': status, 'disposition': 'permanently-rejected', **(proof_change or {})}
        return status, {**result, **(envelope_change or {})}
    hosted['response'] = answer


def invoice(hosted, **changes):
    body = {'action': 'invoice', 'premiseId': 'P1', 'commandId': str(uuid.uuid4()),
            'cycleId': 'cycle', 'accountId': 'A1', **changes}
    response = hosted['client'].post(f"/hosted/worlds/{hosted['world']['id']}/operator", json=body, headers=headers())
    return body, response


@pytest.mark.parametrize('action,status,fields', [
    ('invoice', 403, {'cycleId': 'cycle', 'accountId': 'A1'}),
    ('retry-job', 403, {'jobId': 'invoice-job'}),
    ('release-read', 404, {'exceptionId': 'resolved', 'note': 'Reviewed café 😀\n\t\u2028'}),
])
def test_exact_trusted_proof_rehashed_for_unchanged_browser_body(hosted, action, status, fields):
    refusal(hosted, status)
    value = {'action': action, 'premiseId': 'P1', 'commandId': str(uuid.uuid4()), **fields}
    response = post(hosted, **value)
    assert response.status_code == status
    proof = response.json()['rejection']
    assert proof == {'commandId': value['commandId'], 'status': status,
        'disposition': 'permanently-rejected', 'requestHash': browser_request_hash(value)}
    trusted = hosted['calls'][-1]
    assert trusted['actor'] == {'subject': 'user-a', 'capabilities': ['billing.view', 'billing.run']}
    assert proof['requestHash'] != private_hash(trusted)
    assert response.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('change', [
    {'commandId': str(uuid.uuid4())}, {'commandId': 'x' * 201},
    {'requestHash': 'a' * 64}, {'requestHash': 'a' * 65}, {'requestHash': 'A' * 64},
    {'requestHash': None}, {'status': 404}, {'status': 403.0}, {'status': True},
    {'disposition': 'rejected'}, {'extra': 'unexpected'},
])
def test_changed_or_malformed_proof_does_not_clear_uncertainty(hosted, change):
    refusal(hosted, proof_change=change)
    _, response = invoice(hosted)
    assert response.status_code == 503
    assert 'rejection' not in response.json()


@pytest.mark.parametrize('change', [
    {'schemaVersion': 'wrong'}, {'runId': 'other'}, {'controllerId': 'other'},
    {'premiseId': 'other'}, {'action': 'retry-job'}, {'commandId': str(uuid.uuid4())},
])
def test_proof_cannot_override_envelope_scope(hosted, change):
    refusal(hosted, envelope_change=change)
    _, response = invoice(hosted)
    assert response.status_code == 503 and 'rejection' not in response.json()


@pytest.mark.parametrize('change', [
    lambda value: {key: item for key, item in value.items() if key not in ('actor', 'schemaVersion')},
    lambda value: {**value, 'actor': {**value['actor'], 'subject': 'other'}},
    lambda value: {**value, 'actor': {**value['actor'], 'capabilities': ['billing.view']}},
    lambda value: {**value, 'actor': {**value['actor'], 'capabilities': ['billing.run', 'billing.view']}},
    lambda value: {**value, 'accountId': 'other'},
    lambda value: {**value, 'cycleId': 'other'},
])
def test_digest_must_bind_exact_forwarded_body_actor_and_current_capabilities(hosted, change):
    refusal(hosted, request_change=change)
    _, response = invoice(hosted)
    assert response.status_code == 503 and 'rejection' not in response.json()


def test_unicode_private_digest_uses_ascii_escapes_not_browser_json(hosted):
    note = 'café 😀 \" \\ \b \n \t \u2028 \u2029'
    value = {'action': 'release-read', 'premiseId': 'P1', 'commandId': str(uuid.uuid4()),
             'exceptionId': 'resolved', 'note': note}
    def wrong_encoding(trusted, original):
        result = {key: original[key] for key in ENVELOPE}
        return 404, {**result, 'error': 'Already resolved', 'rejection': {
            'commandId': trusted['commandId'], 'status': 404, 'disposition': 'permanently-rejected',
            'requestHash': private_hash(trusted, ensure_ascii=False)}}
    hosted['response'] = wrong_encoding
    assert post(hosted, **value).status_code == 503
    refusal(hosted, 404)
    response = post(hosted, **value)
    assert response.status_code == 404
    assert response.json()['rejection']['requestHash'] == browser_request_hash(value)


def test_browser_digest_matches_actual_node_unicode_and_lone_surrogate_vectors():
    base = {'action': 'release-read', 'premiseId': 'P1', 'commandId': '00000000-0000-0000-0000-000000000001',
            'exceptionId': 'read'}
    vectors = [{**base, 'note': note} for note in ('ordinary', 'café', '😀', '\u2028\u2029',
        'quotes"slash\\tab\tline\n\b\f\r\u0001', '\ud800', '\udfff', '𐀀')]
    code = """const {createHash}=require('node:crypto');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const hashes=input.map(value=>createHash('sha256').update(JSON.stringify(
Object.fromEntries(Object.keys(value).sort().map(key=>[key,value[key]]))),'utf8').digest('hex'));
process.stdout.write(JSON.stringify(hashes));"""
    result = subprocess.run(['node', '-e', code], input=json.dumps(vectors), capture_output=True,
                            text=True, encoding='utf-8', check=True)
    assert json.loads(result.stdout) == [browser_request_hash(value) for value in vectors]


@pytest.mark.parametrize('action,status,extra', [
    ('bill', 403, {'cycleId': 'cycle', 'contractId': 'contract'}),
    ('invoice', 409, {'cycleId': 'cycle', 'accountId': 'A1'}),
    ('invoice', 503, {'cycleId': 'cycle', 'accountId': 'A1'}),
    ('invoice', 413, {'cycleId': 'cycle', 'accountId': 'A1'}),
    ('release-read', 403, {'exceptionId': 'resolved', 'note': 'Reviewed'}),
    ('job', 404, {'jobId': 'job'}),
])
def test_only_current_permanent_action_status_pairs_accept_proof(hosted, action, status, extra):
    refusal(hosted, status)
    if action != 'job':
        extra = {**extra, 'commandId': str(uuid.uuid4())}
    assert post(hosted, action, **extra).status_code == 503


@pytest.mark.parametrize('status', [403, 404, 409, 413, 503])
def test_unmarked_auth_scope_busy_clock_and_admission_refusals_remain_uncertain(hosted, status):
    refusal(hosted, status, marked=False)
    _, response = invoice(hosted)
    assert response.status_code == status
    assert 'rejection' not in response.json()


def test_proof_cannot_bypass_current_grants_caller_authority_or_length(hosted):
    refusal(hosted)
    body, response = invoice(hosted)
    assert response.status_code == 403 and 'rejection' in response.json()
    endpoint = f"/hosted/worlds/{hosted['world']['id']}/operator"
    for auth in [headers(role='support'), headers(town='other'), hosted['machine_auth'],
                 {**headers(), 'X-UtilitySim-Grants': json.dumps([{'role': 'owner', 'town': 'map-one', 'revoked': True}])}]:
        response = hosted['client'].post(endpoint, json=body, headers=auth)
        assert response.status_code in (401, 403) and 'rejection' not in response.json()
    assert hosted['client'].post(endpoint, json={**body, 'actor': {'subject': 'forged'}}, headers=headers()).status_code == 422
    assert hosted['client'].post(endpoint, json={**body, 'accountId': 'x' * 201}, headers=headers()).status_code == 422
    assert len(hosted['calls']) == 1


def test_uncertain_reply_reopen_exact_retry_returns_only_verified_terminal_proof(hosted):
    refusal(hosted)
    hosted['drop'] = True
    body, response = invoice(hosted)
    assert response.status_code == 503 and len(hosted['calls']) == 1
    client = TestClient(create_app(hosted['root'], TOKEN, MACHINE_KEY, controller_url=hosted['origin'],
        controller_token=CONTROL_TOKEN, controller_allow_http=True, operator_token=OPERATOR_TOKEN))
    repeated = client.post(f"/hosted/worlds/{hosted['world']['id']}/operator", json=body, headers=headers())
    assert repeated.status_code == 403 and hosted['calls'][0] == hosted['calls'][1]
    assert repeated.json()['rejection']['requestHash'] == browser_request_hash(body)


def cohort(hosted, eligible, accounts=None, omitted=False):
    def response(trusted, original):
        record = {**original['result'], 'accounts': accounts if accounts is not None else [{'id': 'A1'}, {'id': 'A2'}]}
        if not omitted:
            record['invoiceEligibleAccountIds'] = eligible
        return 200, {**original, 'result': record}
    hosted['response'] = response


def test_exact_eligible_subset_and_explicit_empty_legacy_fallback(hosted):
    cohort(hosted, ['A1'])
    assert post(hosted).json()['result']['invoiceEligibleAccountIds'] == ['A1']
    cohort(hosted, [])
    assert post(hosted).json()['result']['invoiceEligibleAccountIds'] == []
    cohort(hosted, None, omitted=True)
    assert post(hosted).json()['result']['invoiceEligibleAccountIds'] == []
    assert [row['id'] for row in post(hosted).json()['result']['accounts']] == ['A1', 'A2']


@pytest.mark.parametrize('eligible', [None, 'A1', {}, [True], [1], [{}], [' '],
    ['A1', 'A1'], ['foreign'], ['x' * 201], ['A1'] * 201])
def test_invalid_duplicate_foreign_or_unbounded_eligibility_fails_closed(hosted, eligible):
    cohort(hosted, eligible)
    assert post(hosted).status_code == 503


def test_eligibility_bound_200_and_invalid_account_identifier(hosted):
    accounts = [{'id': 'A' + str(index)} for index in range(200)]
    eligible = [row['id'] for row in accounts]
    cohort(hosted, eligible, accounts)
    response = post(hosted)
    assert response.status_code == 200 and response.json()['result']['invoiceEligibleAccountIds'] == eligible
    cohort(hosted, ['A1'], [{'id': ['A1']}])
    assert post(hosted).status_code == 503
