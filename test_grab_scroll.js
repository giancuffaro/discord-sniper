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
  console.log('PASS: replaced pane, constant-height pagination, slow fetch, capture failure cleanup, navigation isolation.');
})().catch(e=>{console.error(e);process.exitCode=1;});
