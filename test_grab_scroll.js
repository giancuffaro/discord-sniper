const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('extension/content.js','utf8').replace(/\r\n/g,'\n');
const block=source.slice(source.indexOf('let grabbing = false;'),source.indexOf('\ntry {\n  /* CTRL+SHIFT+X'));
async function scenario(mode) {
  let tick=0, oldest=mode==='default'?Date.now()-130*86400000:Date.parse('2026-09-13'), current, captures=0, room='123';
  const reports=[], panes=[];
  function pane() {
    const scroll={parentElement:null,scrollHeight:2000,clientHeight:500,scrollTop:0};
    const row={id:'chat-messages-'+oldest};
    const list={parentElement:scroll,querySelector:()=>row,querySelectorAll:s=>s.startsWith('li')?[row]:[{getAttribute:()=>new Date(oldest).toISOString()}]};
    panes.push(scroll); return list;
  }
  current=pane();
  const ctx={Date,Math,String,document:{body:{},visibilityState:'visible',querySelector:()=>current},
    getComputedStyle:()=>({overflowY:'auto'}),channelId:()=>room,
    chrome:{runtime:{sendMessage:async x=>reports.push(x)}},
    handle:()=>{captures++; if(mode==='error'&&captures===2)throw Error('bad row');},
    setTimeout:fn=>{tick++;if(tick>500)throw Error('loop did not terminate');
      if(mode==='navigation')room='456';
      if(mode==='replace'||mode==='virtual'||mode==='default') {oldest-=86400000;if(mode==='replace')current=pane();else current.querySelector=()=>({id:'chat-messages-'+oldest});}
      fn();}};
  vm.createContext(ctx);vm.runInContext(block,ctx);
  await ctx.grabHistory(mode==='default'?0:Date.parse('2026-09-01'));
  return {reports,panes,tick,captures,ctx};
}
(async()=>{
  const extended=await scenario('default');
  assert(extended.tick>200,'default must continue past four-month-old loaded messages');
  assert(extended.reports.some(x=>x.reached==='date'));
  for(const mode of ['replace','virtual']){
    const r=await scenario(mode);
    assert(r.reports.some(x=>x.reached==='date'),mode+' must reach requested date');
    assert(r.tick>=12,mode+' must keep scrolling');
  }
  const stalled=await scenario('stalled');
  assert(stalled.tick>=40,'slow fetch gets 30 seconds before partial stop');
  assert(stalled.reports.some(x=>x.reached==='top'));
  const error=await scenario('error');
  assert(error.reports.some(x=>x.done&&x.why.includes('interrupted')));
  assert.equal(vm.runInContext('grabbing',error.ctx),false);
  const nav=await scenario('navigation');
  assert(nav.reports.some(x=>x.done&&x.channelId==='123'&&x.why.includes('channel changed')));

  // THE GRAB'S OWN ROWS (9/19): every row the scroll reads goes to the worker
  // as GRAB_ROWS chunks — full text, embeds, image urls — and the done report
  // says how many were sent. The shared `captured` store is not the file.
  {
    let oldest=Date.parse('2026-09-13'), tick=0; const reports=[], chunks=[];
    const scroll={parentElement:null,scrollHeight:2000,clientHeight:500,scrollTop:0};
    const rows=()=>[{id:'chat-messages-'+oldest,querySelector:()=>({getAttribute:()=>new Date(oldest).toISOString()})}];
    const list={parentElement:scroll,querySelector:()=>rows()[0],querySelectorAll:s=>s.startsWith('li')?rows():[{getAttribute:()=>new Date(oldest).toISOString()}]};
    const ctx={Date,Math,String,Object,document:{body:{},visibilityState:'visible',querySelector:()=>list},
      getComputedStyle:()=>({overflowY:'auto'}),channelId:()=>'123',handle:()=>{},
      fullTextOf:li=>'Entry Contract: TSLA $372.5c Price: $1.43 '+li.id,imagesOf:()=>['https://cdn.discordapp.com/attachments/1/2/x.png'],authorOf:()=>'Owner Alerts',
      chrome:{runtime:{sendMessage:async x=>{reports.push(x);if(x.type==='GRAB_ROWS'){chunks.push(x);return {ok:true};}}}},
      setTimeout:fn=>{tick++;if(tick>500)throw Error('loop did not terminate');oldest-=86400000;fn();}};
    vm.createContext(ctx);vm.runInContext(block,ctx);
    await ctx.grabHistory(Date.parse('2026-09-01'));
    const done=reports.find(x=>x.done);
    assert(done&&done.reached==='date','rows run must finish on the date');
    const sent=chunks.reduce((n,c)=>n+c.rows.length,0);
    assert(sent>=12&&done.rows===sent&&done.unsent===0,'every row read must reach the worker before done: sent='+sent+' done.rows='+done.rows);
    assert(chunks.every(c=>c.channelId==='123'&&c.rows.every(r=>/^chat-messages-/.test(r.mid)&&r.text.includes('TSLA $372.5c')&&r.images.length===1&&r.author==='Owner Alerts')),'rows carry mid, full text, images, author');
    assert(new Set(chunks.flatMap(c=>c.rows.map(r=>r.mid))).size===sent,'a row is sent once, not once per sweep');
  }
  // DISCORD PAINTS LATE (9/19): no pane = FAILED after the wait, never "done".
  {
    const reports=[]; let tick=0;
    const ctx={Date,Math,String,Object,document:{body:{},visibilityState:'visible',querySelector:()=>null},
      getComputedStyle:()=>({overflowY:'auto'}),channelId:()=>'123',handle:()=>{},
      chrome:{runtime:{sendMessage:async x=>{reports.push(x);return {ok:true};}}},
      setTimeout:fn=>{tick++;if(tick>1000)throw Error('wait did not end');fn();}};
    vm.createContext(ctx);vm.runInContext(block,ctx);
    await ctx.grabHistory(Date.parse('2026-09-01'));
    assert(reports.some(x=>x.failed&&x.channelId==='123'),'no pane must report failed');
    assert(!reports.some(x=>x.done||x.started),'no pane must never say started or done');
    assert.equal(vm.runInContext('grabbing',ctx),false);
  }
  console.log('PASS: replaced pane, constant-height pagination, slow fetch, capture failure cleanup, navigation isolation, own-row stream, no-pane failure.');
})().catch(e=>{console.error(e);process.exitCode=1;});
