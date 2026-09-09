"""chart_contracts.py — SEE every contract's move, to choose ratchet spacing.

G: "I wanted option contract charts so we can see the movement of every contract
to make a wiser choice." This reads the same backfilled quote tape the sweeps
use and draws one small chart per real fill: gain % from entry over time, with
the entry line (0%), the born stop (-7.5%), the arm (+5%), the peak (MFE) and
trough (MAE), and an X where the LIVE 7.5/5/5 ratchet would have sold. Grouped by
price bucket so the cheap-vs-expensive behaviour is visible at a glance.

Read-only. Reuses ratchet_sweep's tape + fills. Writes contracts.html.
"""
import os
import re
import html

from ratchet_sweep import load_tape, load_trades

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "contracts.html")

BORN = 7.5
ARM = 5.0
STEP = 5.0

W, H = 260, 130
PADL, PADR, PADT, PADB = 34, 8, 20, 16

_OCC = re.compile(r"^([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")


def label(occ):
    m = _OCC.match(occ)
    if not m:
        return occ
    sym, yy, mm, dd, cp, strike = m.groups()
    return "%s %g%s %s/%s" % (sym, int(strike) / 1000.0, cp, int(mm), int(dd))


def locked_pct(gain, arm, step):
    if gain < arm - 1e-9:
        return None
    return step * int((gain - arm + 1e-9) // step)


def series(trade):
    """(gain% list, mfe, mae, final, stop_index or None)."""
    entry = trade["entry"]
    stop = entry * (1.0 - BORN / 100.0)
    gains = []
    stop_i = None
    for i, (_ts, bid, _ask) in enumerate(trade["quotes"]):
        g = (bid - entry) / entry * 100.0
        gains.append(g)
        lk = locked_pct(g, ARM, STEP)
        if lk is not None:
            stop = max(stop, entry * (1.0 + lk / 100.0))
        if stop_i is None and bid <= stop:
            stop_i = i
    mfe = max(gains)
    mae = min(gains)
    return gains, mfe, mae, gains[-1], stop_i


def chart_svg(trade):
    gains, mfe, mae, final, stop_i = series(trade)
    # downsample to <=180 points so the SVG stays light
    if len(gains) > 180:
        step = len(gains) / 180.0
        idx = [int(i * step) for i in range(180)]
        gg = [gains[i] for i in idx]
        smap = {j: k for k, j in enumerate(idx)}       # orig->downsampled
        s_i = None
        if stop_i is not None:
            s_i = min(range(len(idx)), key=lambda k: abs(idx[k] - stop_i))
    else:
        gg = gains
        s_i = stop_i

    lo = min(mae, -BORN, 0.0) - 4
    hi = max(mfe, ARM, 0.0) + 4
    span = (hi - lo) or 1.0
    n = len(gg)

    def X(i):
        return PADL + (W - PADL - PADR) * (i / max(1, n - 1))

    def Y(v):
        return PADT + (H - PADT - PADB) * (1 - (v - lo) / span)

    def hline(v, color, dash=""):
        if v < lo or v > hi:
            return ""
        y = Y(v)
        d = ' stroke-dasharray="3 3"' if dash else ""
        return ('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" '
                'stroke-width="1"%s/>' % (PADL, y, W - PADR, y, color, d))

    pts = " ".join("%.1f,%.1f" % (X(i), Y(v)) for i, v in enumerate(gg))
    parts = ['<svg viewBox="0 0 %d %d" width="%d" height="%d">' % (W, H, W, H)]
    parts.append('<rect x="0" y="0" width="%d" height="%d" fill="#0b0f19"/>' % (W, H))
    parts.append(hline(0.0, "#556", ""))                 # entry
    parts.append(hline(-BORN, "#e0507a", "d"))           # born stop
    parts.append(hline(ARM, "#3ad07a", "d"))             # arm to BE
    # y labels
    for v in (hi - 2, 0.0, lo + 2):
        parts.append('<text x="2" y="%.1f" fill="#8a93a6" font-size="8">%+d%%</text>'
                     % (Y(v) + 3, int(round(v))))
    # the path
    parts.append('<polyline fill="none" stroke="#5aa9ff" stroke-width="1.5" points="%s"/>' % pts)
    # peak / trough dots
    pk = gg.index(max(gg))
    tr = gg.index(min(gg))
    parts.append('<circle cx="%.1f" cy="%.1f" r="2.4" fill="#3ad07a"/>' % (X(pk), Y(max(gg))))
    parts.append('<circle cx="%.1f" cy="%.1f" r="2.4" fill="#e0507a"/>' % (X(tr), Y(min(gg))))
    # where the live stop sold
    if s_i is not None:
        parts.append('<text x="%.1f" y="%.1f" fill="#ffd24a" font-size="11" '
                     'text-anchor="middle">✕</text>' % (X(s_i), Y(gg[s_i]) + 4))
    parts.append('</svg>')
    return "".join(parts), mfe, mae, final, (stop_i is not None)


def card(trade):
    svg, mfe, mae, final, stopped = chart_svg(trade)
    lab = html.escape(label(trade["occ"]))
    sub = ("in $%.2f · peak %+.0f%% · low %+.0f%% · %s"
           % (trade["entry"], mfe, mae,
              ("stopped %+.0f%%" % final if stopped else "ran to %+.0f%%" % final)))
    return ('<div class="card"><div class="t">%s</div>'
            '<div class="s">%s</div>%s</div>' % (lab, html.escape(sub), svg))


def main():
    tape = load_tape()
    trades = load_trades(tape)
    trades.sort(key=lambda t: t["entry"])
    buckets = [("Cheap  (under $1.00)", lambda p: p < 1.0),
               ("Mid  ($1.00 – $1.99)", lambda p: 1.0 <= p < 2.0),
               ("Expensive  ($2.00+)", lambda p: p >= 2.0)]

    body = []
    for name, pred in buckets:
        tb = [t for t in trades if pred(t["entry"])]
        if not tb:
            continue
        body.append('<h2>%s <span class="n">%d contracts</span></h2>'
                    % (html.escape(name), len(tb)))
        body.append('<div class="grid">')
        body.extend(card(t) for t in tb)
        body.append('</div>')

    legend = ('<div class="legend">gain %% from entry over time · '
              '<b style="color:#556">— entry</b> · '
              '<b style="color:#e0507a">-- born −7.5%%</b> · '
              '<b style="color:#3ad07a">-- arm +5%%</b> · '
              '<span style="color:#3ad07a">●</span> peak · '
              '<span style="color:#e0507a">●</span> trough · '
              '<span style="color:#ffd24a">✕</span> where live 7.5/5/5 sold</div>')

    doc = """<!doctype html><meta charset="utf-8">
<title>Option contract movement — %d fills</title>
<style>
 body{background:#070a12;color:#e6e9ef;font:13px system-ui,Segoe UI,Roboto,sans-serif;margin:18px}
 h1{font-size:18px;margin:0 0 4px} h2{font-size:14px;margin:22px 0 8px;color:#cdd3df}
 .n{color:#8a93a6;font-weight:normal;font-size:12px}
 .legend{color:#8a93a6;font-size:12px;margin:6px 0 4px}
 .grid{display:flex;flex-wrap:wrap;gap:10px}
 .card{background:#0b0f19;border:1px solid #1b2233;border-radius:8px;padding:6px 6px 2px}
 .card .t{font-weight:600;font-size:12px} .card .s{color:#8a93a6;font-size:11px;margin-bottom:2px}
</style>
<h1>Option contract movement — every real fill</h1>
%s
%s
<p style="color:#8a93a6;font-size:11px;margin-top:20px">Same 80-fill / ~5-week backfilled sample the sweeps use. Regenerate with <code>python3 chart_contracts.py</code>.</p>
""" % (len(trades), legend, "\n".join(body))

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print("wrote %s  (%d contracts)" % (OUT, len(trades)))


if __name__ == "__main__":
    main()
