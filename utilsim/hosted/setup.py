"""Validated initial customer policies and truthful slider presentation metadata.

Uses existing world commands; it does not implement enterprise billing or staffing.
"""
import copy
import uuid
from time import monotonic

from jsonschema import Draft202012Validator

from utilsim.config.wizard import world_configuration
from utilsim.world import contacts, customer_cashflow, customer_finance
from utilsim.world.store import canonical

VERSION = 'physical-setup/2'
MAX_NEW_COMMANDS = 10
MAX_BATCH_SECONDS = 8


class SetupBatchPending(Exception):
    """The bounded batch committed; the next identical create call continues."""


def number(title, default, minimum, maximum, step, unit, effect, labels, *, integer=False):
    return {'type': 'integer' if integer else 'number', 'title': title, 'default': default,
            'minimum': minimum, 'maximum': maximum,
            'x-control': {'kind': 'slider', 'step': step, 'unit': unit, 'allowExactInput': True,
                          'referenceValue': default, 'referenceLabel': 'Illustrative starting assumption',
                          'labels': labels, 'effect': effect, 'severityBasis': 'relative-to-starting-assumption'}}


def group(title, fields):
    return {'type': 'object', 'title': title, 'additionalProperties': False, 'properties': fields}


def schema():
    active = {'type': 'boolean', 'title': 'Enable this world behavior', 'default': False, 'x-control': {'kind': 'toggle'}}
    return group('Physical and customer assumptions', {
        'customerContacts': group('Customer reactions to physical problems', {
            'active': active,
            'noticeProbabilityPerDay': number('Daily chance of noticing an experienced problem', .5, 0, 1, .01, 'probability',
                'Higher values can produce earlier contact intentions after experienced supply loss or visible overflow.', ['Less likely to contact', 'More likely to contact']),
            'deliveryDelaySeconds': number('Delay before a customer contact becomes available', 86400, 0, 31622400, 3600, 'seconds',
                'Delays the customer contact evidence; this is not a call-centre processing queue.', ['Sooner', 'Later'], integer=True),
            'repeatAfterDays': number('Days before another contact about the same episode', 3, 1, 365, 1, 'days',
                'Shorter intervals permit more frequent repeat contacts while the experienced problem persists.', ['More frequent repeats', 'Less frequent repeats'], integer=True),
            'maxContacts': number('Maximum contacts per experienced episode', 3, 1, 10, 1, 'contacts',
                'Caps repeated customer contact intentions for one episode.', ['Fewer repeats', 'More repeats'], integer=True),
        }),
        'householdFinance': group('Household finances and payment behavior', {
            'enabled': {**active, 'title': 'Configure occupied residential households'},
            'cashCents': number('Starting household cash', 200000, 0, 100000000, 10000, 'minor currency units',
                'Sets each eligible household\'s initial cash; it is not an enterprise account balance.', ['Smaller cash cushion', 'Larger cash cushion'], integer=True),
            'essentialReserveCents': number('Cash protected from utility-payment intentions', 50000, 0, 100000000, 5000, 'minor currency units',
                'Higher reserves protect more household cash and can reduce money available for utility payments.', ['Less protected cash', 'More protected cash'], integer=True),
            'maxPaymentCents': number('Maximum amount per payment intention', 50000, 1, 100000000, 1000, 'minor currency units',
                'Caps a household payment intention after a trusted invoice has been received.', ['Smaller payments', 'Larger payments'], integer=True),
            'paymentProbability': number('Daily payment attempt probability', .75, 0, 1, .01, 'probability',
                'Applies only to received known obligations with available cash; does not create bills or post enterprise payments.', ['Less likely to attempt', 'More likely to attempt']),
        }),
        'householdCashflow': group('Recurring household income and essential expenses', {
            'enabled': {**active, 'title': 'Enable recurring cashflow (requires household finances)'},
            'incomeCents': number('Income per occurrence', 300000, 0, 100000000, 10000, 'minor currency units',
                'Adds income on each configured interval, starting on the world start date.', ['Less income', 'More income'], integer=True),
            'incomeIntervalDays': number('Income interval', 30, 1, 366, 1, 'UTC days',
                'Uses a fixed day interval, not calendar months.', ['More frequent', 'Less frequent'], integer=True),
            'expenseCents': number('Essential expenses per occurrence', 240000, 0, 100000000, 10000, 'minor currency units',
                'Consumes household cash for non-utility essentials; unfunded expense is recorded.', ['Lower expense pressure', 'Higher expense pressure'], integer=True),
            'expenseIntervalDays': number('Essential-expense interval', 30, 1, 366, 1, 'UTC days',
                'Shorter intervals create more frequent household expense pressure.', ['More frequent', 'Less frequent'], integer=True),
            'insufficientCashPolicy': {'type': 'string', 'title': 'When essential expenses exceed available cash',
                'enum': ['available-cash', 'all-or-nothing'], 'default': 'available-cash',
                'x-control': {'kind': 'select', 'optionLabels': {
                    'available-cash': 'Spend available cash; record the unpaid remainder',
                    'all-or-nothing': 'Skip an unaffordable expense; record the full amount unpaid'}}},
        }),
    })


def defaults():
    return {key: {name: field['default'] for name, field in spec['properties'].items()}
            for key, spec in schema()['properties'].items()}


def normalize(supplied):
    if not isinstance(supplied, dict):
        raise ValueError('Physical configuration must be an object.')
    errors = sorted(Draft202012Validator(schema()).iter_errors(supplied), key=lambda e: str(e.path))
    if errors:
        raise ValueError('Invalid physical setup: ' + errors[0].message)
    result = defaults()
    for key, values in supplied.items():
        result[key].update(values)
    if result['householdCashflow']['enabled'] and not result['householdFinance']['enabled']:
        raise ValueError('Household cashflow requires household finance profiles.')
    return result


def presentation():
    world, initial = world_configuration()
    world = copy.deepcopy(world)
    descriptions = {
        'winter_mean_c': (-30, 20, .5, ['Colder winters', 'Milder winters'], 'Changes daily weather and temperature-sensitive demand.'),
        'summer_mean_c': (0, 45, .5, ['Cooler summers', 'Hotter summers'], 'Changes daily weather and cooling-sensitive demand.'),
        'daily_weather_spread_c': (0, 20, .5, ['Steadier weather', 'More variable weather'], 'Changes day-to-day temperature variation.'),
        'annual_meter_failure': (0, .2, .001, ['More reliable meters', 'More frequent failures'], 'Base annual failure probability; meter age further affects failures.'),
        'annual_meter_drift': (0, .2, .001, ['Less drift', 'More drift'], 'Controls how often healthy meters develop measurement drift.'),
    }
    for fields in world['properties'].values():
        for key, spec in fields['properties'].items():
            low, high, step, labels, effect = descriptions[key]
            spec['x-control'] = {'kind': 'slider', 'displayMinimum': low, 'displayMaximum': high,
                                 'step': step, 'labels': labels, 'effect': effect, 'allowExactInput': True,
                                 'referenceValue': spec['default'], 'referenceLabel': 'Engine starting value',
                                 'severityBasis': 'relative-to-starting-assumption'}
    return {'configurationVersion': VERSION, 'schemas': {'world': world, 'physical': schema()},
            'defaults': {'schemaVersion': VERSION, 'world': initial, 'physical': defaults()},
            'scope': {'householdPolicies': 'Uniform initial assumptions for occupied residential premises only',
                      'currency': 'Minor currency units; no currency conversion or enterprise tariff configuration',
                      'unsupportedRequiredControls': ['AMI/AMR/manual channel effects', 'housing age effects', 'customer sentiment feedback']}}


def apply(world, identity, configuration, bindings, snapshot, progress):
    """Replay-safe initial policy commands; caller holds manual clock ownership."""
    started = monotonic()
    with world.read_db() as db:
        meta = world.metadata(db)
        prior_commands = {row['id']: row['payload'] for row in db.execute('SELECT id,payload FROM commands')}
    common = {'environmentId': meta['environment'], 'worldFingerprint': meta['fingerprint'],
              'actorId': 'world-admin', 'expectedRevision': 0, 'effectiveDate': meta['start'],
              'action': 'configure', 'reason': 'Reviewed initial world setup', 'causalReference': identity}
    physical = configuration['physical']
    completed = new_commands = 0

    def execute(domain, module, extra, premise='world'):
        nonlocal completed, new_commands
        command = str(uuid.uuid5(uuid.UUID(identity), domain + ':' + premise))
        payload = {**common, **extra, 'schemaVersion': module.VERSION, 'commandId': command}
        if command in prior_commands:
            if prior_commands[command] != canonical(payload):
                raise ValueError('Recorded setup command differs from the pinned configuration.')
        else:
            if new_commands >= MAX_NEW_COMMANDS or (new_commands and monotonic() - started >= MAX_BATCH_SECONDS):
                raise SetupBatchPending()
            module.command(world, payload)
            new_commands += 1
        completed += 1
        if command not in prior_commands:
            progress(completed)

    premises = {p['id']: p for p in snapshot['premises']}
    eligible = [b for b in bindings if b.get('premiseType') == 'residential' and premises[b['premiseId']].get('occupied', True)]
    finance = physical['householdFinance']
    flow = physical['householdCashflow']
    total = int(physical['customerContacts']['active']) + len(eligible) * int(finance['enabled']) * (1 + int(flow['enabled']))
    try:
        if physical['customerContacts']['active']:
            execute('contacts', contacts, physical['customerContacts'])
        if finance['enabled']:
            for binding in sorted(eligible, key=lambda b: b['premiseId']):
                premise = binding['premiseId']
                recipient = 'household:' + identity + ':' + premise
                personal = {'premiseId': premise, 'runId': meta['environment'], 'recipientRef': recipient}
                execute('finance', customer_finance, {**personal, 'active': True, 'customerKind': 'household',
                    **{key: finance[key] for key in ('cashCents', 'essentialReserveCents', 'maxPaymentCents', 'paymentProbability')}}, premise)
                if flow['enabled']:
                    execute('cashflow', customer_cashflow, {**personal, 'active': True,
                        'income': {'amountCents': flow['incomeCents'], 'firstDate': meta['start'], 'intervalDays': flow['incomeIntervalDays']},
                        'essentialExpense': {'amountCents': flow['expenseCents'], 'firstDate': meta['start'], 'intervalDays': flow['expenseIntervalDays']},
                        'insufficientCashPolicy': flow['insufficientCashPolicy'], 'incomeOverflowPolicy': 'skip-with-record'}, premise)
    except SetupBatchPending:
        pass
    return {'eligibleHouseholds': len(eligible), 'appliedCommands': completed,
            'totalCommands': total, 'complete': completed == total}
