# NinjaTrader ATM templates for the index mirror (the LEVEL shape)

Written by ninjatrader/atm_templates.py from futures_mirror_daily.LEVEL —
the exits the nightly FUTURES MIRROR scores. The names are the ones
settings.json `futures_brokers.ninjatrader.atm_templates` points at.

Create each in NinjaTrader 8: open a Chart Trader or SuperDOM on the micro,
set the ATM Strategy fields exactly as below, then ATM Strategy > Save as
template with that NAME. Quantity 1. Ticks are 0.25 points on ES/NQ micros.

## SNIPER-MES-LEVEL  (MES)

| field | value | = |
|---|---|---|
| Quantity | 1 | one contract |
| Stop loss | 50 ticks | 12.5 pts |
| Profit target | 50 ticks | 12.5 pts (1:1) |
| Auto breakeven | OFF | the bracket is the whole exit |
| Auto trail | OFF | |

Entry (the bridge, not the ATM): limit 2 pts before the 25 level in the pullback's path, cancelled after 30 minutes.

## SNIPER-MNQ-LEVEL  (MNQ)

| field | value | = |
|---|---|---|
| Quantity | 1 | one contract |
| Stop loss | 40 ticks | 10 pts |
| Profit target | 4000 ticks | no target (1,000 pts = never; NT requires a number) |
| Auto breakeven: profit trigger | 20 ticks | +5 pts moves the stop to entry |
| Auto breakeven: plus | 0 ticks | exactly breakeven |
| Auto trail: profit trigger | 20 ticks | starts with the breakeven |
| Auto trail: stop loss | 20 ticks | the stop follows 5 pts behind the best price |
| Auto trail: frequency | 10 ticks | moves in 2.5-pt rungs |

Entry (the bridge, not the ATM): limit AT the 50 level in the pullback's path, cancelled after 30 minutes.

## Before the first real one

1. NinjaTrader 8 open on the Hulk, connected, with `SniperQuoteTape` on an ES and an NQ chart (nt_quote_ES.json / nt_quote_NQ.json in the sniper folder, timestamps moving).
2. Tools > Options > Automated Trading Interface ON (the bridge writes order files into Documents\NinjaTrader 8\incoming).
3. settings.json: futures_brokers.webull false, topstep.enabled false, ninjatrader.enabled true, account = the NT account name. The popup's mirror switch refuses until that is so.
4. First fill supervised on Sim101: watch the limit rest at the level, the ATM bracket appear on the DOM, the cancel file land at 30 minutes if untouched.
5. The proof this shape trades as measured is the nightly FUTURES MIRROR `level` column against the NinjaTrader fills — same alerts, same levels.
