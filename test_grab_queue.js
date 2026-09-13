const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('extension/background.js','utf8');
const block=source.slice(source.indexOf('function grabChannel('),source.indexOf('/* Ctrl+Shift+X',source.indexOf('function grabChannel(')));
async function scenario(tabs,queue){
 let q=queue, running=null;const sent=[],removed=[];
 const c={URL,pumping:false,chrome:{tabs:{get:async id=>{const t=tabs.find(x=>x.id===id);if(!t)throw Error('No tab');return t;},query:async()=>tabs,update:async()=>{},sendMessage:async(id)=>sent.push(id),onRemoved:{addListener(){}},remove:async id=>removed.push(id)},windows:{update:async()=>{}},scripting:{executeScript:async()=>{}}},getQueue:async()=>q,setQueue:async x=>q=x,getRunning:async()=>running,setRunning:async x=>running=x,addLog:async()=>{},roomName:x=>x,downloadRoom:async()=>{},setTimeout:fn=>fn()};
 vm.createContext(c);vm.runInContext(block,c);await c.pumpGrabQueue();await new Promise(r=>setTimeout(r,10));return {c,sent,removed,get running(){return running;},get q(){return q;}};
}
(async()=>{
 let x=await scenario([{id:2,url:'https://discord.com/channels/1/123'}],[{tabId:99,channelId:'123'}]);assert.deepEqual(x.sent,[2]);
 await x.c.advanceQueue(2,true);assert.deepEqual(x.removed,[]);
 x=await scenario([{id:2,url:'https://discord.com/channels/1/456'}],[{tabId:99,channelId:'123'},{tabId:2,channelId:'456'}]);assert.deepEqual(x.sent,[2]);
 x=await scenario([{id:2,url:'https://discord.com/channels/1/456'}],[{tabId:2,channelId:'123'}]);assert.deepEqual(x.sent,[]);
 x=await scenario([{id:2,url:'https://discord.com/channels/1/123'}],[{tabId:2,channelId:'123'},{tabId:3,channelId:'456'}]);await x.c.advanceQueue(3,false);assert.equal(x.running.tabId,2);
 assert.equal(x.c.grabChannel('https://evil.test/discord.com/channels/1/123'),'');
 console.log('PASS: stale ID recovery, failed queue advancement, wrong-channel refusal, manual tab retention, queued removal isolation.');
})().catch(e=>{console.error(e);process.exit(1)});
