"""Build an observation-only, shareable Lantern handoff; never opens writable DBs.

Run with the public UtilitySim checkout on PYTHONPATH. The input is an isolated
captured acceptance world, not a production database or an administrative dump.
"""
import argparse
import collections
import contextlib
import hashlib
import json
import shutil
import sqlite3
import zipfile
from pathlib import Path

from jsonschema import Draft202012Validator

from utilsim.world import World


class ReadOnlyWorld(World):
    @contextlib.contextmanager
    def db(self):
        connection = sqlite3.connect(Path(self.path).resolve().as_uri() + '?mode=ro', uri=True)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_files = [
        'schemas/utility-observations-2.0.schema.json',
        'schemas/customer-contact-intent-1.schema.json',
        'schemas/financial-contact-intent-1.schema.json',
        'schemas/payment-intent-1.schema.json',
        'schemas/customer-finance-delivery-1.schema.json',
        'schemas/customer-finance-provider-receipt-1.schema.json',
        'schemas/customer-finance-provider-receipt-2.schema.json',
        'schemas/field-world-report-1.schema.json',
        'docs/COMPUTE_CONNECTOR_CONTRACT.md',
        'deploy/hosted-runtime/CONTRACT.md',
        'deploy/hosted-runtime/HOSTING.md',
        'deploy/hosted-runtime/Dockerfile',
    ]
    for relative in source_files:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.repo / relative, target)
    shutil.copyfile(Path(__file__), output / Path(__file__).name)

    before = hashlib.sha256(args.database.read_bytes()).hexdigest()
    world = ReadOnlyWorld(args.database)
    batch = world.export_v2('2026-07-17', '2026-07-18', delay_seconds=21600)
    assert world.export_v2('2026-07-17', '2026-07-18', delay_seconds=21600) == batch
    schema = json.loads((output / source_files[0]).read_text(encoding='utf-8'))
    Draft202012Validator(schema).validate(batch)
    assert batch['townId'] == 'town-47ecb8e861787476'
    assert len({a['premiseId'] for a in batch['assets']}) == 436
    assert sum(a['measurementType'] == 'metered' for a in batch['assets']) == 1262
    assert {r['start'] for r in batch['observations']} == {'2026-07-15'}
    assert {r['end'] for r in batch['observations']} == {'2026-07-18'}
    assert {r['availableAt'] for r in batch['observations']} == {'2026-07-18T06:00:00Z'}
    assert hashlib.sha256(args.database.read_bytes()).hexdigest() == before
    write(output / 'fixtures/lantern-three-day-v2.json', batch)
    bindings = {a['servicePointId']: 'FIXTURE-' + a['installationId'] for a in batch['assets']}
    write(output / 'fixtures/example-bindings.json', bindings)
    unmapped = dict(bindings)
    omitted = next(a['servicePointId'] for a in batch['assets'] if a['commodity'] == 'electric')
    del unmapped[omitted]
    write(output / 'fixtures/example-unmapped-bindings.json', unmapped)
    counts = dict(sorted(collections.Counter(r['commodity'] for r in batch['observations']).items()))
    write(output / 'expected-results.json', {
        'producerChecksPassed': ['JSON Schema validation', 'identical re-export', 'input database unchanged',
                                '436 accepted-map premises', '1262 real meter assets', 'full three-day measured intervals',
                                'six-hour availability delay retained'],
        'batchId': batch['batchId'], 'environmentId': batch['environmentId'],
        'premises': 436, 'meterAssets': 1262, 'observationCounts': counts,
        'batchCollectionWindow': [batch['start'], batch['end']],
        'measurementInterval': ['2026-07-15', '2026-07-18'],
        'availableAt': '2026-07-18T06:00:00Z', 'omittedServicePointId': omitted,
        'recipientAcceptanceNotExecuted': [
            'Queue into a fresh authorized isolated run before its clock passes availableAt.',
            'At 05:59:59Z all observations are not_available; at 06:00:00Z each observed row is eligible.',
            'Keep original source IDs, intervals, quantities, observedAt, availableAt and sewer provenance.',
            'Provision fixture installations and commercial records explicitly; example bindings do not create them.',
            'Current candidate rejects unmapped preflight before writes and pauses on failed handler execution.',
            'Retry exact command after lost reply and recipient restart without duplicate meter reads.',
            'Do not mistake held, missing or failed processing for billing success.'
        ]})
    write(output / 'handoff-manifest.json', {
        'scope': 'Captured physical observations and public producer contracts only; no administrative truth, tokens, sessions, private VS code or production data.',
        'configurationVersion': 'physical-setup/4', 'observationVersion': 'utility-observations/2.0',
        'producerRevision': '44e5af22df6e552773a4554c912bd05e0b764c9b',
        'contractsCapturedFrom': 'shell checkout; exact copied bytes recorded in checksums.json',
        'referenceRevision': '6cfd056',
        'publicReferenceBase': 'https://github.com/gragedmonds/utiltiysim/blob/6cfd056/',
        'publicReferences': source_files + ['utilsim/world/exchange.py', 'utilsim/world/delivery.py',
            'utilsim/world/runtime.py', 'utilsim/world/contacts.py', 'utilsim/world/customer_finance.py',
            'utilsim/world/customer_notices.py', 'utilsim/world/field_execution.py', 'utilsim/world/field_reporting.py'],
        'instructions': [
            'Unzip; schemas and contracts are included, so no P: access is required to review this bundle.',
            'Use fixtures/lantern-three-day-v2.json and expected-results.json for the first recipient slice.',
            'BillingAdapter expects explicit servicePointId-to-installation bindings; example bindings are illustrative only.',
            'Hosted observations still returns v1; this fixture comes from actual engine export_v2, not the hosted gateway.',
            'The VS authenticated scheduler command receipt fits the producer outbox; worldfeed per-item report alone does not.',
            'Current producer local_sender is loopback HTTP only; authenticated hosted transport remains a gap.',
            'Use existing /api/commands and one agreed clock owner; do not restamp historical availability to bypass late-command rejection.',
            'Follow HOSTING.md for packaging; provisioning, production connection and container build are not verified here.'
        ],
        'fieldContractCaveat': 'field-world-report/1 schema is the legacy standalone layer; current execution emits field-ack/1 and field-report/1 envelopes. Consult field_execution.py/field_reporting.py and recipient owner before adapting.',
        'remainingFixtureSlices': ['normal AMI', 'missing collection', 'two independent world/run identities',
            'actual invoice receipt -> payment intent -> provider receipt -> ledger', 'actual field completion -> later read',
            'experienced call-centre outcomes -> bounded sentiment feedback'],
        'releaseGate': 'Recipient draft candidates and collection-window fix need agreed repo/PR references and recipient execution evidence. No hosted or production compatibility claim.'
    })
    write(output / 'producer-contract-audit.json', {
        'observationExport': {'function': 'World.export_v2(start,end,sewer_factor="0.9",delay_seconds=0)',
            'schema': 'utility-observations/2.0', 'cursor': 'completed collection-day range; original measured interval retained',
            'hostedGap': 'GET /hosted/worlds/{id}/observations calls legacy World.export, schema1.0'},
        'dailyOutbox': {'functions': ['delivery.configure', 'delivery.status', 'delivery.relay', 'runtime.daily_commands', 'runtime.DailyWorld'],
            'envelopeFields': ['id', 'runId', 'target', 'operation', 'requestedAt', 'availableAt', 'payload', 'cause', 'correlation'],
            'receipt': 'Same id and status pending|delivering|completed|failed; acceptance is scheduler durability, not domain success.',
            'availability': 'relay queues pending rows without an availability filter; scheduler owns timed execution.',
            'failure': 'Malformed or lost receipt retains the oldest pending row; concurrent retries require recipient deduplication.',
            'hostedGap': 'No hosted outbox/relay route or authenticated HTTPS sender; local_sender is loopback HTTP.'},
        'contacts': {'functions': ['contacts.ready', 'contacts.relay'], 'schema': 'customer-contact-intent/1',
            'cursor': 'available_at|sequence, available-only relative to world clock',
            'receiptFields': ['id', 'environmentId', 'fingerprint', 'status=accepted', 'receiptId'],
            'hostedGap': 'No hosted intent feed or relay route'},
        'payments': {'functions': ['customer_finance.ready', 'customer_finance.relay'], 'schema': 'payment-intent/1',
            'cursor': 'integer sequence, available-only relative to world clock',
            'receiptFields': ['id', 'runId', 'fingerprint', 'status=accepted', 'receiptId'],
            'semantics': 'Intention reserves household cash; transport acceptance does not settle cash or enterprise ledger.',
            'hostedGap': 'No hosted payment-intent feed or relay route'},
        'invoiceReturn': {'function': 'customer_finance.receive_delivery', 'schema': 'customer-finance-delivery/1',
            'semantics': 'Trusted actually delivered invoice/notice, matched world/run/cohort; USD positive cents; due/delivery dates retained; durable exact inbox dedup.',
            'hostedGap': 'No hosted authenticated return route'},
        'providerReturn': {'function': 'customer_finance.provider_receipt',
            'schemas': ['customer-finance-provider-receipt/1', 'customer-finance-provider-receipt/2'],
            'semantics': 'Full intent amount/fingerprint only. Settled consumes reserved cash; returned requires linked settlement and refunds; v2 failed releases reservation. No partial settlement.',
            'hostedGap': 'No hosted authenticated return route'},
        'financialContacts': {'functions': ['customer_notices.ready', 'customer_notices.relay'],
            'schema': 'financial-contact-intent/1', 'cursor': 'available_at|sequence, available-only',
            'receiptFields': ['id', 'runId', 'fingerprint', 'status=accepted', 'receiptId'],
            'semantics': 'Requires actual received notice and known invoice; separate policy is not enabled by hosted v4 setup.',
            'hostedGap': 'No hosted notice-policy/feed/relay route'},
        'field': {'modules': ['field_execution', 'field_managed', 'field_reporting'],
            'semantics': 'Separate field DB/outbox, stable assignment/revision/report identities; physical visit and reported claim are distinct.',
            'currentEnvelopes': ['field-ack/1', 'field-report/1'],
            'hostedGap': 'No hosted assignment/execute/report adapter. Legacy field-world-report/1 schema is not the current execution envelope.'},
        'clockAndLimits': ['Managed delivery configuration prevents competing manual world advance.',
            'DailyWorld commits a day and relays its durable outbox before completion; pending prior delivery blocks the next daily job.',
            'VS Run.enqueue accepts durably, Run.advance orders available/sequence and rejects new backdated commands; no continuous hosted supervisor confirmed.',
            'Producer envelope limit8MiB; gateway request64KiB, response3000000bytes, timeout20seconds. Hosted batching/transport needs explicit design without changing source identity.',
            'Call-centre experienced-outcome return for sentiment remains a new contract gap.'],
        'schemaRequiredFields': {relative: json.loads((output / relative).read_text(encoding='utf-8')).get('required', [])
                                 for relative in source_files if relative.startswith('schemas/')}
    })
    files = sorted(p for p in output.rglob('*') if p.is_file() and p.name != 'checksums.json')
    write(output / 'checksums.json', {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    archive = output.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(p for p in output.rglob('*') if p.is_file()):
            zipped.write(path, path.relative_to(output).as_posix())
    print(json.dumps({'bundle': str(archive), 'files': len(files) + 1, 'observations': counts,
                      'schemaValid': True, 'databaseUnchanged': True, 'recipientExecuted': False}))


if __name__ == '__main__':
    main()
