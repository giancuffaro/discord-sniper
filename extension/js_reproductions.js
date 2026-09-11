const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const results = [];
(async () => {
  const source = fs.readFileSync('extension/background.js', 'utf8');
  const start = source.indexOf('async function sendOrder(');
  const end = source.indexOf('/* Consecutive', start);
  const calls = [], logs = [];
  const ctx = {Date,Math,JSON,String,Number,Array,Object,performance,
    tradeableSymbol: async () => true,
    BRIDGE_DEFAULT: 'http://fake.invalid/order',
    fetch: async (url,opts) => {
      calls.push(JSON.parse(opts.body));
      return {ok:calls.length===1,status:calls.length===1?200:502,text:async()=>calls.length===1?'accepted':'refused'};
    },addLog:async e=>logs.push(e)};
  vm.createContext(ctx);vm.runInContext(source.slice(start,end),ctx);
  const result = await ctx.sendOrder({action:'OPEN',symbol:'SPY',side:'CALLS',strike:600,
      expiry:'2026-10-16',also:[{strike:605}]},1,{},'Caller',Date.now());
  assert(result.ok && calls.length===2 && logs.length===0);
  results.push({name:'second_contract_refusal_hidden',reproduced:true,
    detail:{requests:calls.length,second_http_status:502,reported_success:result.ok,error_logs:logs.length}});

  const gctx={Date,Intl,console,chrome:{storage:{local:{get:async()=>({})}}}};
  vm.createContext(gctx);vm.runInContext(fs.readFileSync('extension/guards.js','utf8'),gctx);
  vm.runInContext('etNow = () => ({wd:"Fri",h:16,m:5});',gctx);
  const guard = await gctx.guardCheck({action:'OPEN',kind:'option',symbol:'SPY'},
      {postedAt:Date.now(),author:'Caller'},{guards:{regular_hours_only:true}});
  assert(!guard.allowed && guard.reason.includes('16:00'));
  results.push({name:'spy_guard_disagrees_with_market_hours',reproduced:true,detail:guard});
  fs.writeFileSync('js-reproductions.json',JSON.stringify(results,null,2));
  results.forEach(r=>console.log('REPRODUCED',r.name));
})().catch(e=>{console.error(e);process.exitCode=1;});
