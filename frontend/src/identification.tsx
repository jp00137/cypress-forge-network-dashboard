import {vendorRegistry} from './vendorRegistry';

export function identifyDevice(client:{mac:string;name:string;ip:string}){
 const mac=client.mac.toUpperCase().replaceAll('-',':');
 const valid=/^([0-9A-F]{2}:){5}[0-9A-F]{2}$/.test(mac);
 const first=valid?parseInt(mac.slice(0,2),16):0;
 const usable=valid&&mac!=='00:00:00:00:00:00'&&!(first&1);
 const privateMac=usable&&!!(first&2);
 const hex=mac.replaceAll(':','');
 const vendor=usable&&!privateMac?([9,7,6].map(n=>vendorRegistry[hex.slice(0,n)]).find(Boolean)||null):null;
 const hostname=client.name?.trim()||'';
 const meaningful=!!hostname&&!['*','unknown','localhost'].includes(hostname.toLowerCase())&&hostname!==client.ip&&hostname.toUpperCase()!==mac&&!/^\d{1,3}(\.\d{1,3}){3}$/.test(hostname);
 const friendlyName=meaningful?hostname.replace(/-s-(?=[A-Z])/g,"'s ").replace(/[_-]+/g,' ').replace(/\s+/g,' ').slice(0,80):null;
 let icon:string|null=null;
 if(meaningful){
  if(/roku|hisense|smart.?tv|television/i.test(hostname))icon='tv';
  else if(/galaxy|iphone|ipad|android|pixel|fold|tab[-_ ]/i.test(hostname))icon='phone';
  else if(/desktop|laptop|macbook|thinkpad|surface/i.test(hostname))icon='computer';
  else if(/printer|epson|brother|laserjet|officejet/i.test(hostname))icon='printer';
  else if(/camera|doorbell/i.test(hostname))icon='camera';
  else if(/^wiz[_-]|shelly|tasmota|esphome/i.test(hostname))icon='iot';
 }
 return {vendor,privateMac,valid:usable,friendlyName,icon,macStatus:!usable?'Invalid or non-device MAC':privateMac?'Private / locally administered MAC':'Globally administered MAC'};
}

export function IdentificationFacts({client}:{client:{mac:string;name:string;ip:string}}){
 const hint=identifyDevice(client);
 return <div className="profile-facts"><h3>Automatic identification hints</h3><p>{hint.macStatus}<br/>Address registrant: <b>{hint.vendor|| (hint.privateMac?'Lookup skipped for private addresses':'Unknown')}</b><br/>Observed name: {client.name||'Unknown'}<br/>Name suggestion: {hint.friendlyName||'None'}<br/>Category suggestion: {hint.icon||'Unknown'}</p><p>Registry matches identify an address-block organization, not a verified brand or model. Private addresses may be randomized or manually assigned. Name and category suggestions come from hostnames; they do not establish identity, connectivity or trust. Offline IEEE registry snapshot: 2026-11-14.</p></div>
}

export type ReviewFilter='all'|'unrecognized'|'private'|'unknown-vendor';
type ReviewClient={mac:string;name:string;ip:string;state:string;source:string;last_seen?:number};
type ReviewProfiles=Record<string,{name:string;trusted:boolean;attachment:string;notes:string;tag:string}>;
export function reviewMatch(c:ReviewClient,profiles:ReviewProfiles,filter:ReviewFilter){
 const hint=identifyDevice(c);
 return filter==='all'||(filter==='unrecognized'&&!profiles[c.mac]?.trusted)||(filter==='private'&&hint.privateMac)||(filter==='unknown-vendor'&&!hint.privateMac&&!hint.vendor);
}
export function inventoryRows(clients:ReviewClient[],profiles:ReviewProfiles,mode:string,stale:boolean){
 return [['Mode','Reading status','Saved name','Observed name','IP address','MAC address','Address registrant hint','MAC classification','Recognized (owner label)','Manual attachment','Tag','Notes','Neighbor / observation state','Observation source','Last observed (UTC)'],...clients.map(c=>{
  const p=profiles[c.mac],hint=identifyDevice(c);
  return [mode,stale?'Stale / retained':'Latest cached observation',p?.name||'',c.name,c.ip,c.mac,hint.vendor||'',hint.macStatus,p?.trusted?'Yes':'No',p?.attachment||'',p?.tag||'',p?.notes||'',c.state,c.source,c.last_seen?new Date(c.last_seen*1000).toISOString():''];
 })];
}
