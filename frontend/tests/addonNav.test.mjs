import {test} from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {addonLinks,addonClients,loadAddons,loadAddonLinks,loadClients,AddonNav} from '../.test-build/AddonNav.mjs';

const entry=(over={})=>({name:'hello',title:'Hello',version:'0.1.0',hooks:[],api:null,ui:'/addon/hello/',errors:0,last_error:null,...over});

test('add-on links keep entries that serve a page',()=>{
 assert.deepEqual(addonLinks({addons:[entry()]}),[{name:'hello',title:'Hello',ui:'/addon/hello/'}]);
});
test('add-on links drop entries without a safe add-on page path',()=>{
 const bad=[null,undefined,'javascript:alert(1)','https://evil.example/','//evil.example/','/api/dashboard','/addon/../api/','/addon/x','/addon/a/b/',42];
 const payload={addons:[...bad.map((ui,i)=>entry({name:`a${i}`,ui})),entry({ui:undefined}),'text',null,7]};
 delete payload.addons[bad.length].ui;
 assert.deepEqual(addonLinks(payload),[]);
});
test('malformed add-on payloads give an empty list without throwing',()=>{
 for(const p of [null,undefined,{},{addons:'x'},[],'text',{addons:null}])assert.deepEqual(addonLinks(p),[]);
});
test('add-on titles fall back to the name, are trimmed and shortened, and duplicates are dropped',()=>{
 const links=addonLinks({addons:[entry({title:undefined}),entry({name:'b',title:7,ui:'/addon/b/'}),entry({name:'c',title:'  '+'x'.repeat(200)+'  ',ui:'/addon/c/'}),entry({name:'d',title:'   ',ui:'/addon/d/'}),entry({name:'dup',title:'Dup',ui:'/addon/hello/'})]});
 assert.deepEqual(links.map(l=>l.title),['hello','b','x'.repeat(60),'d']);
});
test('add-on link loading fails quietly',async()=>{
 assert.deepEqual(await loadAddonLinks(async()=>{throw new Error('offline')}),[]);
 assert.deepEqual(await loadAddonLinks(async()=>({ok:false,status:500,json:async()=>({addons:[entry()]})})),[]);
 assert.deepEqual(await loadAddonLinks(async()=>({ok:true,status:200,json:async()=>{throw new SyntaxError('bad')}})),[]);
 let asked;
 const links=await loadAddonLinks(async url=>{asked=url;return {ok:true,status:200,json:async()=>({addons:[entry()]})}});
 assert.equal(asked,'/api/addons');assert.equal(links.length,1);
});
test('add-on clients keep only plain .js files inside an add-on folder',()=>{
 assert.deepEqual(addonClients({addons:[entry({client:'/addon/hello/client.js'}),entry({name:'b',client:'/addon/hello/client.js'})]}),['/addon/hello/client.js']);
 const bad=[null,undefined,42,'javascript:alert(1)','//evil.example/x.js','https://evil.example/addon/a/x.js','/assets/x.js','/addon/a/../x.js','/addon/../a/x.js','/addon/a/b/x.js','/addon/a/x.mjs','/addon/a/x.js?y','/addon/a/'];
 assert.deepEqual(addonClients({addons:bad.map(client=>entry({client}))}),[]);
 for(const p of [null,{},{addons:'x'},'text'])assert.deepEqual(addonClients(p),[]);
});
test('add-ons load links and clients from one request, quietly on failure',async()=>{
 let calls=0;
 const got=await loadAddons(async()=>{calls++;return {ok:true,status:200,json:async()=>({addons:[entry({client:'/addon/hello/client.js'})]})}});
 assert.equal(calls,1);assert.equal(got.links.length,1);assert.deepEqual(got.clients,['/addon/hello/client.js']);
 assert.deepEqual(await loadAddons(async()=>{throw new Error('offline')}),{links:[],clients:[]});
});
test('client modules are imported, and a failing one is ignored',async()=>{
 const asked=[];
 const n=await loadClients(['/addon/a/ok.js','/addon/b/bad.js','/addon/c/throws.js'],async u=>{asked.push(u);if(u.includes('bad'))throw new TypeError('404');if(u.includes('throws'))return Promise.reject(new Error('boom'));return {}});
 assert.equal(n,1);assert.deepEqual(asked,['/addon/a/ok.js','/addon/b/bad.js','/addon/c/throws.js']);
 let imported=0;assert.equal(await loadClients([],async()=>{imported++}),0);assert.equal(imported,0);
});
test('no add-on pages render nothing',()=>{
 assert.equal(renderToStaticMarkup(React.createElement(AddonNav,{links:[]})),'');
});
test('add-on links render as same-tab links with escaped titles',()=>{
 const html=renderToStaticMarkup(React.createElement(AddonNav,{links:[{name:'hello',title:'Hello',ui:'/addon/hello/'}]}));
 assert.ok(html.includes('ADD-ONS'));assert.ok(html.includes('href="/addon/hello/"'));assert.ok(html.includes('>Hello<'));
 assert.ok(!html.includes('target='));assert.ok(!html.includes('role="alert"'));
 const evil=renderToStaticMarkup(React.createElement(AddonNav,{links:addonLinks({addons:[entry({title:'<img src=x onerror=alert(1)>'})]})}));
 assert.ok(evil.includes('&lt;img'));assert.ok(!evil.includes('<img'));
});
