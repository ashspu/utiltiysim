import test from 'node:test';
import assert from 'node:assert/strict';
import {setupStorageConfig, setupStorageConfigured} from '../../server/setup-storage.mjs';
test('dedicated store never falls back to the legacy website placeholder',()=>{
  const legacy={UPSTASH_REDIS_REST_URL:'https://utiltiysim.vercel.app',UPSTASH_REDIS_REST_TOKEN:'legacy'};
  assert.equal(setupStorageConfigured(legacy),false);
  assert.throws(()=>setupStorageConfig(legacy),/unavailable/);
  assert.deepEqual(setupStorageConfig({...legacy,UTILITYSIM_STORE_KV_REST_API_URL:'https://example.upstash.io',UTILITYSIM_STORE_KV_REST_API_TOKEN:'dedicated'}),{url:'https://example.upstash.io',token:'dedicated'});
});
test('store rejects credential-bearing, non-provider and non-TLS endpoints',()=>{
  for(const url of ['https://utiltiysim.vercel.app','https://upstash.io.attacker.example','http://example.upstash.io','https://user:pass@example.upstash.io','https://example.upstash.io/pipeline'])assert.equal(setupStorageConfigured({UTILITYSIM_STORE_KV_REST_API_URL:url,UTILITYSIM_STORE_KV_REST_API_TOKEN:'token'}),false);
});
