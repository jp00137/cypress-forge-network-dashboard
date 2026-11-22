import React, {useEffect, useState} from 'react';
import {Puzzle} from 'lucide-react';

// Sidebar links to pages served by loaded add-ons (GET /api/addons, entries whose `ui` is set).
// Generic core behavior: any add-on in the cypressforge.addons group gets a link the same way.
export type AddonLink = {name:string;title:string;ui:string};

// The backend only ever reports `/addon/<name>/`. Anything else is dropped, so a bad response
// can never become a javascript:, off-site or core-path link.
const ADDON_PATH = /^\/addon\/[A-Za-z0-9._-]+\/$/;
const MAX_TITLE = 60;

export function addonLinks(payload:unknown):AddonLink[]{
 const list=payload&&typeof payload==='object'?(payload as {addons?:unknown}).addons:null;
 if(!Array.isArray(list))return [];
 const seen=new Set<string>(),links:AddonLink[]=[];
 for(const item of list){
  if(!item||typeof item!=='object')continue;
  const {name,title,ui}=item as Record<string,unknown>;
  if(typeof ui!=='string'||!ADDON_PATH.test(ui)||ui.includes('..')||seen.has(ui))continue;
  const fallback=typeof name==='string'&&name.trim()?name.trim():ui.slice(7,-1);
  const label=(typeof title==='string'&&title.trim()?title.trim():fallback).slice(0,MAX_TITLE);
  seen.add(ui);links.push({name:fallback,title:label,ui});
 }
 return links;
}

// Add-on client modules (docs/THEME-SEAM.md): one plain .js file inside an add-on's own folder.
// The backend validates the name too; this repeats the check so a bad response can never make
// the page import a core path, another origin or a javascript: URL.
const CLIENT_PATH = /^\/addon\/[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+\.js$/;

export function addonClients(payload:unknown):string[]{
 const list=payload&&typeof payload==='object'?(payload as {addons?:unknown}).addons:null;
 if(!Array.isArray(list))return [];
 const out:string[]=[];
 for(const item of list){
  const client=item&&typeof item==='object'?(item as Record<string,unknown>).client:null;
  if(typeof client==='string'&&CLIENT_PATH.test(client)&&!client.includes('..')&&!out.includes(client))out.push(client);
 }
 return out;
}

type FetchLike=(url:string,init?:{signal?:AbortSignal})=>Promise<{ok:boolean;json():Promise<unknown>}>;
export type Addons={links:AddonLink[];clients:string[]};

// Never rejects: any failure means "no add-ons", with no banner and no console noise.
export async function loadAddons(fetchFn:FetchLike=fetch,signal?:AbortSignal):Promise<Addons>{
 try{const r=await fetchFn('/api/addons',{signal});if(!r.ok)return {links:[],clients:[]};const body=await r.json();return {links:addonLinks(body),clients:addonClients(body)};}
 catch{return {links:[],clients:[]};}
}

export async function loadAddonLinks(fetchFn:FetchLike=fetch,signal?:AbortSignal):Promise<AddonLink[]>{
 return (await loadAddons(fetchFn,signal)).links;
}

// Each client is imported once (the browser caches modules by URL). A client that fails to load
// or throws is ignored and the dashboard carries on. Resolves to the number that loaded.
type ImportLike=(url:string)=>Promise<unknown>;
export async function loadClients(urls:string[],importFn:ImportLike=url=>import(/* @vite-ignore */ url)):Promise<number>{
 const results=await Promise.all(urls.map(u=>importFn(u).then(()=>true,()=>false)));
 return results.filter(Boolean).length;
}

// Fetched once: add-ons are discovered only at server start.
export function useAddonLinks():AddonLink[]{
 const [links,setLinks]=useState<AddonLink[]>([]);
 useEffect(()=>{const ctl=new AbortController();loadAddons(fetch,ctl.signal).then(a=>{if(ctl.signal.aborted)return;setLinks(a.links);void loadClients(a.clients)});return()=>ctl.abort();},[]);
 return links;
}

export function AddonNav({links}:{links:AddonLink[]}){
 if(!links.length)return null;
 return <><div className="nav-label">ADD-ONS</div><nav className="addon-nav" aria-label="Add-ons">{links.map(l=><a key={l.ui} href={l.ui} title={l.title} aria-label={l.title}><Puzzle size={18}/><span>{l.title}</span></a>)}</nav></>;
}
