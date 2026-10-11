import { WorkOS } from '@workos-inc/node';
import { config, identity, reply, sameOrigin } from '../server/auth.mjs';
import { grantsFor, permits } from '../server/permissions.mjs';
import { catalog, validateSetup, draftStore, publicSetup } from '../server/setup-drafts.mjs';
import { setupStorageConfigured } from '../server/setup-storage.mjs';

export function createSetupsHandler({env=process.env, client=cfg=>new WorkOS(cfg.apiKey,{clientId:cfg.clientId}), store=()=>draftStore(env)}={}) {
  return async (req,res) => {
    try {
      const cfg = config(env);
      if (!['GET','POST'].includes(req.method)) return reply(res,405,{detail:'Method not allowed.'});
      if (req.method === 'POST' && !sameOrigin(req,cfg)) return reply(res,403,{detail:'Request origin refused.'});
      const auth = await identity(req,res,cfg,client(cfg));
      if (!auth) return reply(res,401,{detail:'Sign in to open your saved setups.'});
      const grants = auth.user.emailVerified ? grantsFor(auth.user.id,env) : [];
      if (!grants.length) return reply(res,403,{detail:'Workspace access required.'});
      const url = new URL(req.url,cfg.origin);
      if (req.method === 'GET' && url.searchParams.get('view') === 'catalog') {
        return reply(res,200,{...catalog,sources:catalog.sources.filter(s=>permits(grants,'world.view',s.grantTownId)).map(s=>({...s,canSave:grants.some(g=>g.role==='owner'&&(g.town==='*'||g.town===s.grantTownId))})),
          setupStorageConfigured:setupStorageConfigured(env), runtimeConfigured:false});
      }
      if (req.method === 'GET') {
        const setups = (await store().list(auth.user.id)).filter(s=>permits(grants,'world.view',s.grantTownId)).map(publicSetup);
        return reply(res,200,{setups});
      }
      if (Buffer.byteLength(JSON.stringify(req.body||{})) > 16384) return reply(res,413,{detail:'Setup request is too large.'});
      const input = validateSetup(req.body);
      if (!grants.some(g=>g.role==='owner'&&(g.town==='*'||g.town===input.grantTownId))) return reply(res,403,{detail:'Owner access is required to save this town setup.'});
      return reply(res,200,{setup:publicSetup(await store().save(auth.user.id,input))});
    } catch (error) {
      if (![409,422].includes(error.status)) {
        // Categorize infrastructure failures without logging credentials, URLs,
        // setup bodies, or provider error text.
        const message = String(error.message || '').toLowerCase();
        const category = /unauthorized|wrongpass|invalid.*token|401|403/.test(message) ? 'storage-authentication'
          : /resolve|enotfound|fetch failed|timeout|econn/.test(message) ? 'storage-network'
          : /quota|limit|exceeded/.test(message) ? 'storage-capacity'
          : /disabled|suspended|archived|not found/.test(message) ? 'storage-unavailable'
          : /eval|script|lua|cjson/.test(message) ? 'storage-script'
          : /setup storage unavailable/.test(message) ? 'storage-configuration'
          : 'storage-unclassified';
        console.error('setup-storage-failure', category, ['TypeError','SyntaxError','UpstashError','Error'].includes(error.name) ? error.name : 'ProviderError');
      }
      return reply(res,[409,422].includes(error.status)?error.status:503,{detail:[409,422].includes(error.status)?error.message:'Online setup storage is unavailable. Your unsaved values are still on this page; try saving again.'});
    }
  };
}
export default createSetupsHandler();
