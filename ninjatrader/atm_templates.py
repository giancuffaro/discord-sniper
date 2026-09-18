#!/usr/bin/env python3
"""atm_templates.py — writes ninjatrader/ATM-TEMPLATES.md from
futures_mirror_daily.LEVEL, so the NinjaTrader ATM templates G creates by hand
hold exactly the numbers the nightly mirror scores. Numbers are never typed
into the doc; change LEVEL, rerun this, recreate the templates."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from futures_mirror_daily import LEVEL, LEVEL_WAIT, MAP        # noqa: E402

TICK = {"ES": 0.25, "NQ": 0.25}
NAMES = {"ES": "SNIPER-MES-LEVEL", "NQ": "SNIPER-MNQ-LEVEL"}   # what settings names


def ticks(root, pts):
    return int(round(pts / TICK[root]))


def main():
    doc = ["# NinjaTrader ATM templates for the index mirror (the LEVEL shape)", "",
           "Written by ninjatrader/atm_templates.py from futures_mirror_daily.LEVEL —",
           "the exits the nightly FUTURES MIRROR scores. The names are the ones",
           "settings.json `futures_brokers.ninjatrader.atm_templates` points at.", "",
           "Create each in NinjaTrader 8: open a Chart Trader or SuperDOM on the micro,",
           "set the ATM Strategy fields exactly as below, then ATM Strategy > Save as",
           "template with that NAME. Quantity 1. Ticks are 0.25 points on ES/NQ micros.", ""]
    for root, L in LEVEL.items():
        micro = MAP["SPY" if root == "ES" else "QQQ"][1]
        doc += ["## %s  (%s)" % (NAMES[root], micro), "", "| field | value | = |", "|---|---|---|",
                "| Quantity | 1 | one contract |",
                "| Stop loss | %d ticks | %g pts |" % (ticks(root, L["stop"]), L["stop"])]
        if L.get("target"):
            doc += ["| Profit target | %d ticks | %g pts (1:1) |" % (ticks(root, L["target"]), L["target"]),
                    "| Auto breakeven | OFF | the bracket is the whole exit |",
                    "| Auto trail | OFF | |"]
        else:
            doc += ["| Profit target | 4000 ticks | no target (1,000 pts = never; NT requires a number) |",
                    "| Auto breakeven: profit trigger | %d ticks | +%g pts moves the stop to entry |" % (ticks(root, L["arm"]), L["arm"]),
                    "| Auto breakeven: plus | 0 ticks | exactly breakeven |",
                    "| Auto trail: profit trigger | %d ticks | starts with the breakeven |" % ticks(root, L["arm"]),
                    "| Auto trail: stop loss | %d ticks | the stop follows %g pts behind the best price |" % (ticks(root, L["arm"]), L["arm"]),
                    "| Auto trail: frequency | %d ticks | moves in %g-pt rungs |" % (ticks(root, L["step"]), L["step"])]
        doc += ["", "Entry (the bridge, not the ATM): limit %s the %g level in the pullback's path, cancelled after %d minutes."
                % (("%g pts before" % L["buf"] if L["buf"] > 0 else "%g pts THROUGH" % -L["buf"]) if L["buf"] else "AT", L["grid"], LEVEL_WAIT), ""]
    doc += ["## Before the first real one", "",
            "1. NinjaTrader 8 open on the Hulk, connected, with `SniperQuoteTape` on an ES and an NQ chart (nt_quote_ES.json / nt_quote_NQ.json in the sniper folder, timestamps moving).",
            "2. Tools > Options > Automated Trading Interface ON (the bridge writes order files into Documents\\NinjaTrader 8\\incoming).",
            "3. settings.json: futures_brokers.webull false, topstep.enabled false, ninjatrader.enabled true, account = the NT account name. The popup's mirror switch refuses until that is so.",
            "4. First fill supervised on Sim101: watch the limit rest at the level, the ATM bracket appear on the DOM, the cancel file land at %d minutes if untouched." % LEVEL_WAIT,
            "5. The proof this shape trades as measured is the nightly FUTURES MIRROR `level` column against the NinjaTrader fills — same alerts, same levels.", ""]
    with open(os.path.join(HERE, "ATM-TEMPLATES.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(doc))
    for root, L in LEVEL.items():
        with open(os.path.join(HERE, NAMES[root] + ".xml"), "w", encoding="utf-8") as fh:
            fh.write(template_xml(root, L))
    print("\n".join(doc))


def template_xml(root, L):
    """The NinjaTrader 8 ATM template file for one micro — what NT writes to
    Documents\\NinjaTrader 8\\templates\\AtmStrategy\\<name>.xml when you
    press 'save as template'. Ticks. Copied there by hand or by the setup step;
    NT lists it in the ATM Strategy dropdown after a restart or a template
    refresh. If NT rejects the file, ATM-TEMPLATES.md has the same numbers for
    creating it by hand."""
    name = NAMES[root]
    if L.get("target"):
        target, be_trig, be_plus, trail = ticks(root, L["target"]), 0, 0, ""
    else:
        target, be_trig, be_plus = 4000, ticks(root, L["arm"]), 0
        trail = ("\n          <AutoTrailSteps>\n            <AutoTrailStep>\n"
                 "              <Frequency>%d</Frequency>\n              <ProfitTrigger>%d</ProfitTrigger>\n"
                 "              <StopLoss>%d</StopLoss>\n            </AutoTrailStep>\n          </AutoTrailSteps>"
                 % (ticks(root, L["step"]), ticks(root, L["arm"]), ticks(root, L["arm"])))
    return """<?xml version="1.0" encoding="utf-8"?>
<NinjaTrader>
  <AtmStrategy xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <Brackets>
      <Bracket>
        <Quantity>1</Quantity>
        <StopLoss>%d</StopLoss>
        <StopStrategy>
          <AutoBreakEvenPlus>%d</AutoBreakEvenPlus>
          <AutoBreakEvenProfitTrigger>%d</AutoBreakEvenProfitTrigger>%s
          <IsSimStopEnabled>false</IsSimStopEnabled>
          <VolumeTrigger>0</VolumeTrigger>
        </StopStrategy>
        <Target>%d</Target>
      </Bracket>
    </Brackets>
    <Calculate>OnPriceChange</Calculate>
    <ChaseLimit>0</ChaseLimit>
    <EntryQuantity>1</EntryQuantity>
    <IsChase>false</IsChase>
    <IsChaseIfTouched>false</IsChaseIfTouched>
    <IsTargetChase>false</IsTargetChase>
    <ReverseAtStop>false</ReverseAtStop>
    <ReverseAtTarget>false</ReverseAtTarget>
    <ShadowStrategy />
    <Template>%s</Template>
    <TimeInForce>Day</TimeInForce>
  </AtmStrategy>
</NinjaTrader>
""" % (ticks(root, L["stop"]), be_plus, be_trig, (trail if trail else "\n          <AutoTrailSteps />"), target, name)


if __name__ == "__main__":
    main()
