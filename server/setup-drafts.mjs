import { createHash } from 'node:crypto';
import { Redis } from '@upstash/redis';
import { setupStorageConfig } from './setup-storage.mjs';
import catalog from './setup-catalog.json' with { type: 'json' };

export { catalog };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const fail = message => { throw Object.assign(new Error(message), { status: 422 }); };
function keys(value, expected) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some(key => !expected.includes(key))) fail('Unexpected setup fields.');
}
function validateFields(values, schema) {
  keys(values, Object.keys(schema.properties));
  const result = {};
  for (const [field, rule] of Object.entries(schema.properties)) {
    const value = values[field];
    if (rule.type === 'object') { result[field] = validateFields(value, rule); continue; }
    const valid = rule.type === 'boolean' ? typeof value === 'boolean' :
      rule.type === 'string' ? typeof value === 'string' && (!rule.enum || rule.enum.includes(value)) :
      ['number','integer'].includes(rule.type) && typeof value === 'number' && Number.isFinite(value) &&
        (rule.type !== 'integer' || Number.isSafeInteger(value)) &&
        (rule.minimum === undefined || value >= rule.minimum) && (rule.maximum === undefined || value <= rule.maximum);
    if (!valid) fail(`Invalid ${(rule.title || field).toLowerCase()}.`);
    result[field] = value;
  }
  return result;
}
export function validateSetup(input, setupCatalog = catalog) {
  keys(input, ['id','commandId','revision','name','start','sourceId','sourceRevision','snapshotSha256','configuration']);
  if (!uuid.test(input.id || '') || !uuid.test(input.commandId || '')) fail('A valid setup and save identifier are required.');
  if (!Number.isSafeInteger(input.revision) || input.revision < 0) fail('Invalid setup revision.');
  if (typeof input.name !== 'string' || !input.name.trim() || input.name.trim().length > 120) fail('Enter a setup name of 1–120 characters.');
  if (typeof input.start !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(input.start) || !Number.isFinite(Date.parse(input.start)) || new Date(input.start).toISOString().slice(0,10) !== input.start) fail('Enter a valid start date.');
  const source = setupCatalog.sources.find(source => source.id === input.sourceId && source.canConfigure);
  if (!source || source.snapshotSha256 !== input.snapshotSha256 || source.sourceRevision !== input.sourceRevision) fail('This map revision is not available for setup. Select the current accepted town.');
  const extended = input.configuration && (Object.hasOwn(input.configuration,'physical') || Object.hasOwn(input.configuration,'schemaVersion'));
  keys(input.configuration, extended ? ['world','physical','schemaVersion'] : ['world']);
  if (extended && (input.configuration.schemaVersion !== 'physical-setup/2' || setupCatalog.configuration.configurationVersion !== 'physical-setup/2' || !setupCatalog.configuration.schemas.physical)) fail('Select the advertised physical-setup/2 configuration.');
  const world = validateFields(input.configuration.world, setupCatalog.configuration.schemas.world);
  const configuration = {world};
  if (extended) {
    configuration.schemaVersion = 'physical-setup/2';
    configuration.physical = validateFields(input.configuration.physical, setupCatalog.configuration.schemas.physical);
    if (configuration.physical.householdCashflow.enabled && !configuration.physical.householdFinance.enabled) fail('Household cashflow requires household finance profiles.');
  }
  return { id:input.id, commandId:input.commandId, revision:input.revision, name:input.name.trim(), start:input.start,
    sourceId:source.id, sourceRevision:source.sourceRevision, townId:source.townId, grantTownId:source.grantTownId, snapshotSha256:source.snapshotSha256, configuration };
}
// One owner hash makes revision check + write atomic, without expiring drafts.
// A lost response can be retried with the same command and identical payload.
export const saveScript = `
local raw = redis.call('HGET', KEYS[1], ARGV[1])
local incoming = cjson.decode(ARGV[3])
if raw then
  local old = cjson.decode(raw)
  if old.commandId == incoming.commandId then
    if old.requestHash == incoming.requestHash then return raw end
    return redis.error_reply('SETUP_COMMAND_CONFLICT')
  end
  if old.revision ~= tonumber(ARGV[2]) then return redis.error_reply('SETUP_REVISION_CONFLICT') end
  if old.sourceId ~= incoming.sourceId or old.snapshotSha256 ~= incoming.snapshotSha256 or old.sourceRevision ~= incoming.sourceRevision then return redis.error_reply('SETUP_SOURCE_CONFLICT') end
  incoming.createdAt = old.createdAt
elseif tonumber(ARGV[2]) ~= 0 then
  return redis.error_reply('SETUP_REVISION_CONFLICT')
elseif redis.call('HLEN', KEYS[1]) >= 100 then
  return redis.error_reply('SETUP_LIMIT')
end
local saved = cjson.encode(incoming)
redis.call('HSET', KEYS[1], ARGV[1], saved)
return saved`;
export function draftStore(env = process.env, redis) {
  if (!redis) {
    redis = new Redis(setupStorageConfig(env));
  }
  const key = actor => 'utilitysim:setup:v1:' + createHash('sha256').update(actor).digest('hex');
  const decode = value => typeof value === 'string' ? JSON.parse(value) : value;
  return {
    async list(actor) { return (await redis.hvals(key(actor))).map(decode).sort((a,b) => b.updatedAt.localeCompare(a.updatedAt)); },
    async save(actor, input) {
      const now = new Date().toISOString();
      const record = { ...input, revision:input.revision+1, status:'setup', createdAt:now, updatedAt:now,
        requestHash:createHash('sha256').update(JSON.stringify(input)).digest('hex') };
      try { return decode(await redis.eval(saveScript, [key(actor)], [input.id,input.revision,JSON.stringify(record)])); }
      catch (error) {
        if (/SETUP_(?:REVISION|COMMAND|SOURCE)_CONFLICT/.test(error.message)) throw Object.assign(new Error('This setup changed elsewhere. Reload its saved version before saving again.'), {status:409});
        if (/SETUP_LIMIT/.test(error.message)) throw Object.assign(new Error('This account has reached its 100 saved setup limit.'), {status:409});
        throw error;
      }
    },
  };
}
export function publicSetup({commandId,requestHash,...record}) { return record; }
