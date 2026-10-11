// Dedicated Marketplace store. Never reuse the legacy placeholder Redis URL.
export function setupStorageConfig(env = process.env) {
  const url = env.UTILITYSIM_STORE_KV_REST_API_URL;
  const token = env.UTILITYSIM_STORE_KV_REST_API_TOKEN;
  let parsed; try { parsed = new URL(url); } catch {}
  if (!token || parsed?.protocol !== 'https:' || !parsed.hostname.endsWith('.upstash.io') || parsed.username || parsed.password || parsed.search || parsed.hash || parsed.pathname !== '/') throw new Error('Setup storage unavailable');
  return {url, token};
}
export function setupStorageConfigured(env = process.env) {
  try { setupStorageConfig(env); return true; } catch { return false; }
}
