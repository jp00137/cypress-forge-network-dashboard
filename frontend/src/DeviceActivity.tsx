import {useEffect,useState} from 'react';
import type {Client,Dashboard,Event} from './workspace';
import {csv,stamp} from './workspace';

const normal=(mac:string)=>mac.toLowerCase().replaceAll('-',':');
export function deviceEvents(data:Dashboard,mac:string){
 if(data.mode!=='live')return [];
 return data.events.filter(e=>normal(e.subject)===normal(mac)).sort((a,b)=>b.ts-a.ts||b.id-a.id);
}
export function DeviceActivity({data,client}:{data:Dashboard;client:Client}){
 const [remote,setRemote]=useState<{events:Event[];truncated:boolean;retention_days:number}|null>(null),[error,setError]=useState('');
 useEffect(()=>{
  setRemote(null);setError('');if(data.mode!=='live')return;
  const abort=new AbortController();
  async function refresh(){try{const r=await fetch(`/api/device-events?mac=${encodeURIComponent(client.mac)}`,{signal:abort.signal});if(!r.ok)throw Error(r.status===404?'Restart the dashboard backend to load device-specific history.':'Device history could not be refreshed.');const result=await r.json();if(!abort.signal.aborted){setRemote(result);setError('')}}catch(e){if(!abort.signal.aborted)setError(String(e))}}
  refresh();const timer=setInterval(refresh,15000);return()=>{abort.abort();clearInterval(timer)};
 },[client.mac,data.mode]);
 const events=remote?.events||deviceEvents(data,client.mac);
 return <section className="profile-facts"><h3>Device activity</h3>{data.mode!=='live'?<p>Sample mode does not show live device events.</p>:<><p>First recorded: {stamp(client.first_seen)}<br/>Last recorded: {stamp(client.last_seen)}<br/>Recorded addresses: {(client.addresses||[client.ip]).join(', ')}</p>{data.stale&&<p className="amber">Collection is stale. This is retained activity, not current device status.</p>}<p>{remote?`Device-specific SQLite history: ${events.length} events loaded, retained for ${remote.retention_days} days.${remote.truncated?' More events exist; showing the newest 500.':''}`:`Fallback: matched within the latest ${data.events.length} loaded network events (up to 200). Older device events may not be included.`} A private MAC change creates a separate identity; absent records do not prove a device is offline.</p>{error&&<p className="amber">{error} Displayed events may be retained.</p>}<button type="button" className="button" disabled={!events.length} onClick={()=>csv(`cypress-device-activity-${normal(client.mac).replaceAll(':','')}.csv`,[['MAC address','Event time (UTC)','Event type','Recorded message','Reading status'],...events.map(e=>[client.mac,new Date(e.ts*1000).toISOString(),e.kind,e.message,data.stale||!!error?'Stale / retained':'Recorded history'])])}>Export loaded device events CSV</button>{events.length?<ol>{events.map(e=><li key={e.id}><b>{stamp(e.ts)}</b><p>{e.message}</p><small>{e.kind}</small></li>)}</ol>:<p>No matching events in the loaded window. This does not mean this device has never changed.</p>}</>}</section>
}
