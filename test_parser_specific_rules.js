const assert = require('node:assert/strict');
const parser = require('./extension/parser.js');
const fs = require('node:fs');
parser.setOptionable(new Set(fs.readFileSync('extension/optionable.txt','utf8').split(/\r?\n/).map(x=>x.trim()).filter(x=>x && !x.startsWith('#'))));
const read = text => parser.parseSignal(text, {});
const slv = 'Entered SLV 7/17 62C @ 3.10 Starter position. Beautiful daily bullish engulfing yesterdays session and held/retested that PDH perfectly. Long as we are above 58 here love this. Want to add if we can build here target is back into 65. GLD/GC also looks really nice for a swing as long as it is above 4200 on GC and 380-385 on GLD.';
assert.equal(read(slv).action,'OPEN');
assert.equal(read(slv).symbol,'SLV');
assert.equal(read(slv).limit,3.1);
for (const text of [
  'If we entered SLV 7/17 62C @ 3.10 this session',
  'Entered SLV 7/17 62C @ 3.10 yesterday',
  'Entered SLV 7/17 62C @ 3.10 this session but never filled',
  'Entered SLV 7/17 62C @ 3.10 paper account this session',
  'QQQ 728c > 727.00 718p < 720.00',
]) assert.notEqual(read(text).action,'OPEN',text);
for (const price of ['2.17','2.37']) {
  const s = read(`Full close. @everyone Qqq Aug 14 720 put at ${price} Target 2.30`);
  assert.equal(s.action,'CLOSE');
  assert.equal(s.symbol,'QQQ');
  assert.equal(s.strike,720);
  // Reuse existing Close-label policy; do not broaden exit execution.
  assert.equal(s.fire,read(`Close Qqq Aug 14 720 put at ${price}`).fire);
}
assert.notEqual(read('If we full close QQQ Aug 14 720 put at 2.17').action,'CLOSE');
assert.equal(read('70 points $1,400 a con on NQ short Taking one more trim leaving one runner for full target, not moving stop still BE. Beautiful trade guys').action,'TRIM');
assert.notEqual(read('not moving stop to 29900 on NQ').action,'STOPMOVE');
assert.notEqual(read('do not move stop to 29900 on NQ').action,'STOPMOVE');
assert.equal(read('70 points on NQ moving stop to 29900').their_stop,29900);
assert.equal(read('lowering my stop loss on Tesla, 351 new stop loss').their_stop,351);
assert.equal(read('NQ stop to breakeven').be,true);
assert.notEqual(read('$750 a contract on ES short. Moving stop BE').their_stop,750);
console.log('Specific parser rule regressions passed.');
