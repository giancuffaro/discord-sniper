// The grab's own rows (9/19): chunks in, one merged file out, store cleared.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('extension/background.js','utf8');
const block=source.slice(source.indexOf("/* ---- The grab's own rows"),source.indexOf('/* ---- Grab queue'));
(async()=>{
  let store={}; const posts=[], logs=[];
  const ctx={Date,Math,String,Object,Array,Map,Set,Number,JSON,encodeURIComponent,
    chrome:{storage:{local:{get:async k=>{if(Array.isArray(k))return Object.fromEntries(k.map(x=>[x,store[x]]));return {[k]:store[k]};},
                            set:async o=>{Object.assign(store,JSON.parse(JSON.stringify(o)));},
                            remove:async ks=>{for(const k of ks)delete store[k];}}},
            downloads:{download:async()=>{throw Error('no bridge fallback expected');}}},
    cfg:async()=>({bridge_url:'http://127.0.0.1:8787'}),bridgeBaseFrom:x=>x,addLog:async x=>logs.push(x),
    fetch:async(url,o)=>{posts.push(JSON.parse(o.body));return {ok:true,json:async()=>({ok:true})};}};
  vm.createContext(ctx);vm.runInContext(block,ctx);
  // nothing grabbed -> nothing written, no file
  assert.equal(await ctx.downloadRoom('911','Platinum nitro'),0);
  assert.equal(posts.length,0,'no rows must write no file');
  // two chunks, one row read twice (embed hydrated on the second read), one image-only row
  await ctx.addGrabRows('911',[
    {mid:'chat-messages-911-2',t:2000,author:'Nitro Trades',text:'@Owner Alerts',images:[]},
    {mid:'chat-messages-911-1',t:1000,author:'Owner Alerts',text:'[ 9:40 AM ] Entry Contract: NVDA $175c Price: .72',images:['https://cdn.discordapp.com/attachments/1/2/a.png']}]);
  await ctx.addGrabRows('911',[
    {mid:'chat-messages-911-2',t:2000,author:'Nitro Trades',text:'@Owner Alerts Comment TSLA +69% @nitro_trades',images:['https://media.discordapp.net/attachments/3/4/b.png']},
    {mid:'chat-messages-911-3',t:3000,author:'Nitro Trades',text:'',images:['https://cdn.discordapp.com/attachments/5/6/c.png']}]);
  await ctx.addGrabRows('777',[{mid:'chat-messages-777-9',t:9,author:'x',text:'other room',images:[]}]);
  assert.equal(Object.keys(store).filter(k=>k.startsWith('grab_part_')).length,3);
  const n=await ctx.downloadRoom('911','Platinum nitro');
  assert.equal(n,3,'one row per message id');
  const txt=posts.find(p=>p.name.endsWith('.txt')), js=posts.find(p=>p.name.endsWith('.json'));
  assert(txt&&js,'txt and json twin');
  const lines=txt.text.split('\n').filter(l=>/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}\s{2}\[message_id=/.test(l));
  assert.equal(lines.length,3);
  assert(lines[0].includes('chat-messages-911-1')&&lines[1].includes('chat-messages-911-2')&&lines[2].includes('chat-messages-911-3'),'sorted by time');
  assert(lines[1].includes('Comment TSLA +69%')&&lines[1].endsWith(' [image]'),'fullest read wins, image marked: '+lines[1]);
  assert(!txt.text.includes('discordapp'),'urls never reach the .txt (digit runs would hit the price parser)');
  const j=JSON.parse(js.text);
  assert.equal(j.schema_version,3);
  assert.deepEqual(j.messages.map(m=>m.images.length),[1,1,1]);
  assert.equal(j.messages[1].message_id,'chat-messages-911-2');
  assert(txt.text.includes('messages: 3')&&txt.text.includes('with_images: 3'));
  assert(!Object.keys(store).some(k=>k.startsWith('grab_part_911')),'parts cleared after the file is written');
  assert(Object.keys(store).some(k=>k.startsWith('grab_part_777')),'the other room keeps its parts');
  assert.deepEqual(store.grab_parts['911'],undefined);
  console.log('PASS: no-rows writes nothing, chunks merge by message id (fullest read wins), time order, [image] marker, json twin carries urls, store cleared per room.');
})().catch(e=>{console.error(e);process.exit(1)});
