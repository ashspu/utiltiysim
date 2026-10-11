"""Bounded community/household sentiment from known or experienced evidence.

This changes customer propensity to contact about an existing experienced problem;
it neither creates enterprise queues nor invents a service problem from bad news.
"""
import json
import math
from datetime import date

from .store import canonical, stable

VERSION = 'world-sentiment/1'
DEFAULTS = {'enabled': False, 'initialTrust': 70, 'recoveryDays': 30, 'experienceImpact': .08,
            'lateBillImpact': .1, 'communityInfluence': .05, 'maxContactMultiplier': 2}


def validate(policy):
    if not isinstance(policy, dict) or set(policy) != set(DEFAULTS) or type(policy['enabled']) is not bool:
        raise ValueError('Invalid sentiment policy.')
    for key, low, high in [('initialTrust', 0, 100), ('recoveryDays', 1, 365), ('experienceImpact', 0, 1),
                           ('lateBillImpact', 0, 1), ('communityInfluence', 0, 1), ('maxContactMultiplier', 1, 5)]:
        value = policy[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Sentiment setting outside supported bounds: ' + key)
    if type(policy['recoveryDays']) is not int:
        raise ValueError('Recovery days must be an integer.')


def configure(world, identity, policy, premises):
    validate(policy)
    encoded = canonical({'modelVersion': VERSION, 'policy': policy, 'premises': sorted(premises)})
    with world.db() as db:
        old = db.execute('SELECT * FROM commands WHERE id=?', (identity,)).fetchone()
        if old:
            if old['payload'] != encoded:
                raise ValueError('Conflicting sentiment setup retry.')
            return json.loads(old['result'])
        meta = world.metadata(db)
        if meta['through'] != meta['start'] or db.execute('SELECT 1 FROM days LIMIT 1').fetchone():
            raise ValueError('Initial sentiment must be configured before advancing.')
        if 'sentimentModelVersion' in meta:
            raise ValueError('Initial sentiment is already pinned.')
        if not policy['enabled']:
            raise ValueError('Explicitly enable sentiment before configuring it.')
        for sql in (
            'CREATE TABLE sentiment_households(premise TEXT PRIMARY KEY,frustration REAL NOT NULL,stamp TEXT NOT NULL)',
            'CREATE TABLE sentiment_days(day TEXT PRIMARY KEY,community REAL NOT NULL,mean_household REAL NOT NULL,payload TEXT NOT NULL)',
            'CREATE TABLE sentiment_household_days(premise TEXT NOT NULL,day TEXT NOT NULL,frustration REAL NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(premise,day))',
            'CREATE TABLE sentiment_news(id TEXT PRIMARY KEY,day TEXT NOT NULL,change REAL NOT NULL,headline TEXT NOT NULL,cause TEXT NOT NULL,applied TEXT,cancelled TEXT)',
            'CREATE TABLE sentiment_financial_seen(delivery TEXT PRIMARY KEY)',
        ):
            db.execute(sql)
        initial = 1 - policy['initialTrust'] / 100
        for premise in sorted(premises):
            db.execute('INSERT INTO sentiment_households VALUES(?,?,?)', (premise, initial, 'baseline'))
        for key, value in {'sentimentModelVersion': VERSION, 'sentimentPolicy': policy,
                           'sentimentCommunity': initial, 'sentimentRevision': 0}.items():
            world.put(db, key, value)
        event = world.event(db, meta['environment'], meta['start'], 'SentimentConfigured', meta['town'], json.loads(encoded), identity)
        result = {'commandId': identity, 'eventId': event, 'modelVersion': VERSION}
        db.execute('INSERT INTO commands VALUES(?,?,?)', (identity, encoded, canonical(result)))
        return result


def command(world, payload):
    if not isinstance(payload, dict):
        raise ValueError('A sentiment command object is required.')
    common = {'commandId', 'expectedRevision', 'effectiveDate', 'action', 'reason', 'causalReference',
              'schemaVersion', 'actorId', 'environmentId', 'worldFingerprint'}
    action = payload.get('action')
    extra = {'eventDate', 'trustChange', 'headline'} if action == 'schedule' else {'newsId'} if action == 'cancel' else None
    if extra is None or set(payload) != common | extra or payload['schemaVersion'] != VERSION or payload['actorId'] != 'world-admin':
        raise ValueError('Invalid sentiment event command.')
    for key in (common - {'expectedRevision'}) | (extra - {'trustChange'}):
        if not isinstance(payload[key], str) or not payload[key].strip() or len(payload[key]) > 512:
            raise ValueError('Sentiment event text must be nonempty and at most 512 characters.')
    if type(payload['expectedRevision']) is not int or not 0 <= payload['expectedRevision'] <= 2147483647:
        raise ValueError('Invalid sentiment revision.')
    if date.fromisoformat(payload['effectiveDate']).isoformat() != payload['effectiveDate']:
        raise ValueError('Use canonical event dates.')
    if action == 'schedule':
        if date.fromisoformat(payload['eventDate']).isoformat() != payload['eventDate']:
            raise ValueError('Use canonical event dates.')
        change = payload['trustChange']
        if type(change) not in (int, float) or not math.isfinite(change) or not -100 <= change <= 100:
            raise ValueError('Trust change must be between -100 and 100 points.')
    encoded = canonical(payload)
    with world.db() as db:
        meta = world.metadata(db)
        if payload['environmentId'] != meta['environment'] or payload['worldFingerprint'] != meta['fingerprint']:
            raise ValueError('World identity mismatch.')
        old = db.execute('SELECT * FROM commands WHERE id=?', (payload['commandId'],)).fetchone()
        if old:
            if old['payload'] != encoded:
                raise ValueError('Conflicting sentiment event retry.')
            return json.loads(old['result'])
        if meta.get('sentimentModelVersion') != VERSION:
            raise ValueError('Enable supported sentiment during world setup first.')
        if payload['effectiveDate'] != meta['through'] or payload['expectedRevision'] != meta['sentimentRevision']:
            raise ValueError('Sentiment revision or world date changed.')
        if action == 'schedule':
            if not 0 <= (date.fromisoformat(payload['eventDate']) - date.fromisoformat(meta['through'])).days <= 3650:
                raise ValueError('News must be scheduled within the next 3650 days.')
            identity = 'NEWS-' + stable(meta['environment'], payload['commandId'])
            db.execute('INSERT INTO sentiment_news VALUES(?,?,?,?,?,NULL,NULL)',
                       (identity, payload['eventDate'], payload['trustChange'], payload['headline'], payload['commandId']))
        else:
            identity = payload['newsId']
            news = db.execute('SELECT * FROM sentiment_news WHERE id=?', (identity,)).fetchone()
            if not news or news['applied'] or news['cancelled'] or news['day'] < meta['through']:
                raise ValueError('Only unprocessed scheduled news can be cancelled.')
            db.execute('UPDATE sentiment_news SET cancelled=? WHERE id=?', (payload['commandId'], identity))
        revision = meta['sentimentRevision'] + 1
        world.put(db, 'sentimentRevision', revision)
        event = world.event(db, meta['environment'], meta['through'], 'SentimentNewsScheduled' if action == 'schedule' else 'SentimentNewsCancelled', identity, payload, payload['commandId'])
        result = {'commandId': payload['commandId'], 'newsId': identity, 'revision': revision,
                  'eventId': event, 'status': 'completed', 'modelVersion': VERSION, 'effectiveDate': meta['through']}
        db.execute('INSERT INTO commands VALUES(?,?,?)', (payload['commandId'], encoded, canonical(result)))
        return result


def bounded(value):
    return max(0, min(1, value))


def daily(world, db, meta):
    if 'sentimentModelVersion' not in meta:
        return
    if meta['sentimentModelVersion'] != VERSION:
        raise ValueError('Unsupported sentiment model.')
    from .contacts import _symptoms

    day, policy = meta['through'], meta['sentimentPolicy']
    households = db.execute('SELECT * FROM sentiment_households ORDER BY premise').fetchall()
    assets = {a['id']: dict(a) for a in db.execute('SELECT id,premise,profile FROM assets')}
    occupied = {a['premise']: json.loads(a['profile']).get('occupied', True) for a in assets.values()}
    experienced = {assets[asset]['premise'] for asset, _ in _symptoms(db, day, meta)}
    stamps = {r['premise']: r['applied_command'] for r in db.execute('SELECT premise,applied_command FROM occupancy_premises')} if 'occupancyModelVersion' in meta else {}
    news = db.execute('SELECT * FROM sentiment_news WHERE day=? AND applied IS NULL AND cancelled IS NULL ORDER BY id', (day,)).fetchall()
    news_change = sum(r['change'] for r in news) / 100
    public = bounded(meta['sentimentCommunity'] - news_change)
    late = {}
    if 'customerFinanceModelVersion' in meta:
        # These are trusted, actually received world inbox records; no enterprise database is read.
        for row in db.execute('SELECT i.* FROM customer_finance_inbox i LEFT JOIN sentiment_financial_seen s ON s.delivery=i.id WHERE s.delivery IS NULL').fetchall():
            message = json.loads(row['payload'])
            if message.get('kind') != 'invoice':
                db.execute('INSERT INTO sentiment_financial_seen VALUES(?)', (row['id'],))
                continue
            invoice = db.execute('SELECT * FROM customer_finance_invoices WHERE id=?', (message['invoiceId'],)).fetchone()
            if not invoice or invoice['known_at'] > day + 'T00:00:00Z' or message['deliveredAt'] > day + 'T00:00:00Z':
                continue
            profile = db.execute('SELECT * FROM customer_finance_profiles WHERE premise=?', (message['premiseId'],)).fetchone()
            if profile and profile['recipient'] == message['recipientRef'] and profile['stamp'] == (stamps.get(profile['premise']) or 'baseline') and occupied.get(profile['premise'], False):
                if message['deliveredAt'][:10] > message['dueDate']:
                    late[profile['premise']] = late.get(profile['premise'], 0) + 1
            db.execute('INSERT INTO sentiment_financial_seen VALUES(?)', (row['id'],))
    values = []
    for row in households:
        premise = row['premise']
        stamp = stamps.get(premise) or 'baseline'
        prior = row['frustration'] if stamp == row['stamp'] else 1 - policy['initialTrust'] / 100
        is_occupied = occupied.get(premise, False)
        service = int(is_occupied and premise in experienced)
        bills = min(1, late.get(premise, 0))
        influence = policy['communityInfluence'] * (public - prior) if is_occupied else 0
        frustration = bounded(prior - prior / policy['recoveryDays'] + influence +
                              service * policy['experienceImpact'] + bills * policy['lateBillImpact'])
        evidence = {'experiencedProblem': bool(service), 'lateDeliveredBills': bills, 'communityInfluence': influence,
                    'occupancyStamp': stamp, 'priorFrustration': prior, 'publicFrustration': public}
        db.execute('UPDATE sentiment_households SET frustration=?,stamp=? WHERE premise=?', (frustration, stamp, premise))
        db.execute('INSERT INTO sentiment_household_days VALUES(?,?,?,?)', (premise, day, frustration, canonical(evidence)))
        if is_occupied:
            values.append(frustration)
    mean = sum(values) / len(values) if values else 0
    community = bounded(public - public / policy['recoveryDays'] + policy['communityInfluence'] * (mean - public))
    evidence = {'newsIds': [r['id'] for r in news], 'trustChange': news_change * 100,
                'occupiedHouseholds': len(values), 'experiencedHouseholds': sum(1 for p in experienced if occupied.get(p)),
                'lateDeliveredBills': sum(late.values())}
    db.execute('INSERT INTO sentiment_days VALUES(?,?,?,?)', (day, community, mean, canonical(evidence)))
    db.execute('UPDATE sentiment_news SET applied=? WHERE day=? AND applied IS NULL AND cancelled IS NULL', (day, day))
    world.put(db, 'sentimentCommunity', community)
    world.event(db, meta['environment'], day, 'SentimentDayCompleted', meta['town'],
                {'communityTrust': (1 - community) * 100, 'meanHouseholdTrust': (1 - mean) * 100, **evidence})


def contact_policy(db, meta, premise, base):
    if meta.get('sentimentModelVersion') != VERSION:
        return base
    row = db.execute('SELECT frustration FROM sentiment_households WHERE premise=?', (premise,)).fetchone()
    if row is None:
        return base
    multiplier = 1 + row['frustration'] * (meta['sentimentPolicy']['maxContactMultiplier'] - 1)
    return {**base, 'noticeProbabilityPerDay': min(1, base['noticeProbabilityPerDay'] * multiplier),
            'repeatAfterDays': max(1, math.ceil(base['repeatAfterDays'] / multiplier)),
            'maxContacts': min(10, math.ceil(base['maxContacts'] * multiplier))}


def inspect(world, premise=None, before=None, limit=25, news_before=None):
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError('Use a sentiment history limit from 1 to 50.')
    if before is not None and date.fromisoformat(before).isoformat() != before:
        raise ValueError('Use a canonical history cursor.')
    if news_before is not None and (type(news_before) is not int or not 1 <= news_before <= 9223372036854775807):
        raise ValueError('Use a positive news cursor.')
    with world.read_db() as db:
        meta = world.metadata(db)
        if 'sentimentModelVersion' not in meta:
            return {'enabled': False, 'modelVersion': VERSION, 'view': 'administrator-truth', 'through': meta['through']}
        state = db.execute('SELECT * FROM sentiment_households WHERE premise=?', (premise,)).fetchone() if premise else None
        if premise and state is None:
            raise ValueError('Premise has no configured sentiment profile.')
        rows = db.execute('SELECT * FROM sentiment_household_days WHERE premise=? AND day<? ORDER BY day DESC LIMIT ?',
                          (premise, before or '9999-12-31', limit + 1)).fetchall() if premise else db.execute(
            'SELECT * FROM sentiment_days WHERE day<? ORDER BY day DESC LIMIT ?', (before or '9999-12-31', limit + 1)).fetchall()
        history = [{**dict(row), 'payload': json.loads(row['payload'])} for row in rows[:limit]]
        news = [dict(r) for r in db.execute('SELECT rowid sequence,* FROM sentiment_news WHERE rowid<? ORDER BY rowid DESC LIMIT ?',
                                          (news_before or 9223372036854775807, limit + 1))]
        return {'enabled': True, 'modelVersion': VERSION, 'view': 'administrator-truth', 'through': meta['through'],
                'revision': meta['sentimentRevision'], 'policy': meta['sentimentPolicy'],
                'communityTrust': (1 - meta['sentimentCommunity']) * 100,
                'householdTrust': (1 - state['frustration']) * 100 if state else None,
                'history': history, 'nextBefore': history[-1]['day'] if len(rows) > limit else None,
                'news': news[:limit], 'nextNewsBefore': news[limit - 1]['sequence'] if len(news) > limit else None}
