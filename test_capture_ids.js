const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('extension/background.js','utf8');
let stored=[];
const ctx={Map,Date,String,Math,Promise,setTimeout:()=>1,
 chrome:{storage:{local:{get:async()=>({captured:stored}),set:async x=>{stored=x.captured;}}}}};
vm.createContext(ctx);
vm.runInContext(src.slice(src.indexOf('let CAPTURE_PENDING'),src.indexOf('/* Save one room')),ctx);
async function batch(items){const pending=items.map(x=>ctx.capture(...x));await ctx.flushCaptures();await Promise.all(pending);}
(async()=>{
 await batch(Array.from({length:30},(_,i)=>['same words','caller','room',1000,true,'clean','id'+i]));
 await batch([['same words','caller','room',1000,true,'clean','id0']]);
 assert.equal(stored.length,30,'stable ID dedup is not limited to last eight posts');
 await batch([['same words','caller','other',1000,true,'clean','id0']]);
 assert.equal(stored.length,31,'channel identity must remain separate');
 await batch([['edited words','caller','room',1000,true,'edited','id0']]);
 assert.equal(stored.length,31);
 assert.equal(stored[0].revisions[0].text,'same words');
 assert.equal(stored[0].text,'edited words');
 await batch([['legacy','caller','room',1000,true,'legacy'],['legacy','caller','other',1000,true,'legacy']]);
 assert.equal(stored.length,33,'legacy fallback cannot merge channels');
 console.log('PASS: stable IDs, distant duplicate, same-text distinct posts, channel isolation, observed revisions, legacy isolation.');
})().catch(e=>{console.error(e);process.exitCode=1;});
