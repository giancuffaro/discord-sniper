"""occ.py — ONE place that knows what a contract is called.

    from occ import build, parse, to_dx, from_dx, side_letter

WHY (9/7/26)
------------
G asked for things the app does in several places that could be one thing.
This was the worst of them. The contract symbol was built or translated in
SEVEN places:

    webull_options.occ_symbol      the base builder
    bridge._occ_build              wraps it, normalises the side
    positions._occ_for             calls the builder the bridge installs
    bars_capture.occ               its own copy
    dxlink.occ_to_dx               OCC -> dxfeed
    quote_shadow.dx_to_occ         dxfeed -> OCC
    bridge, inline (9/6)           an eighth, written for the decay sampler

A wrong contract symbol is not a cosmetic bug. It buys something nobody
named, or it points the watchdog at a contract we do not hold — and it does
that silently, because a well-formed wrong symbol looks exactly like a
well-formed right one.

THE LANDMINE THIS REMOVES
-------------------------
`webull_options.occ_symbol` decides the side like this:

    cp = "C" if option_type == "CALL" else "P"

Anything that is not the exact string "CALL" becomes a **PUT**. "CALLS",
"call", "c", "C", None, "" — all puts, silently. Today no caller trips it,
because all five of them repeat the same incantation:

    "CALL" if str(side).upper().startswith("C") else "PUT"

Five copies of one line, and the whole thing holds together only because
everybody remembers to say it. `side_letter()` below accepts every form the
rooms and the brokers actually use and **RAISES on anything else**. A refused
build is a missed trade; a silent flip is the wrong trade.

FORMATS
-------
OCC      NVDA260904C00235000   root + YYMMDD + C/P + strike*1000, 8 digits
dxfeed   .NVDA260904C235       leading dot, plain strike, no padding,
                               half-strikes keep the decimal (.IWM260904P243.5)

This module is pure: no I/O, no config, no network. Import it from anywhere.
"""

# Every spelling of a side seen in rooms, broker payloads and our own code.
_CALL = {"C", "CALL", "CALLS", "CA", "LONG CALL"}
_PUT = {"P", "PUT", "PUTS", "PU", "LONG PUT"}


def side_letter(side):
    """'CALLS' / 'call' / 'C' -> 'C'.  Raises on anything unrecognised.

    THE POINT OF THIS FUNCTION IS THE RAISE. The old behaviour — default to
    PUT on anything unexpected — is the single most dangerous line this
    codebase had, because it turns a typo into the opposite trade with no
    error anywhere.
    """
    s = str(side or "").strip().upper()
    if s in _CALL:
        return "C"
    if s in _PUT:
        return "P"
    raise ValueError(
        "cannot tell if %r is a call or a put — refusing to guess. "
        "(A guess here buys the opposite contract and nothing errors.)"
        % (side,))


def build(symbol, expiry, side, strike):
    """Root + expiry + side + strike -> OCC.

    `expiry` accepts 'YYYY-MM-DD' or 'YYMMDD' or a date object.
    `side` accepts anything side_letter() accepts.
    Raises rather than returning a wrong-but-plausible symbol.
    """
    root = str(symbol or "").strip().upper()
    if not root or not root.isalpha():
        raise ValueError("bad option root %r" % (symbol,))
    ymd = _ymd(expiry)
    cp = side_letter(side)
    try:
        k = float(strike)
    except (TypeError, ValueError):
        raise ValueError("bad strike %r" % (strike,))
    if k <= 0:
        raise ValueError("strike must be positive, got %r" % (strike,))
    return "%s%s%s%08d" % (root, ymd, cp, int(round(k * 1000)))


def _ymd(expiry):
    """-> 'YYMMDD'. Accepts a date, 'YYYY-MM-DD', 'YYYYMMDD' or 'YYMMDD'."""
    if hasattr(expiry, "strftime"):
        return expiry.strftime("%y%m%d")
    s = str(expiry or "").strip().replace("-", "").replace("/", "")
    if len(s) == 8 and s.isdigit():
        return s[2:]
    if len(s) == 6 and s.isdigit():
        return s
    raise ValueError("cannot read an expiry out of %r" % (expiry,))


def parse(occ):
    """OCC -> (root, 'YYMMDD', 'C'|'P', strike_float), or None if it is not
    an OCC symbol. Returns None rather than raising: callers use this to ASK
    whether a string is a contract."""
    s = str(occ or "").strip().replace(" ", "")
    if len(s) < 15:
        return None
    tail = s[-15:]
    root, ymd, cp, k8 = s[:-15], tail[:6], tail[6], tail[7:]
    if not root or cp not in ("C", "P") or not k8.isdigit() \
            or not ymd.isdigit():
        return None
    return (root.upper(), ymd, cp, int(k8) / 1000.0)


def to_dx(occ):
    """OCC -> dxfeed ('.NVDA260904C235'), or None.

    dxfeed wants the strike plainly: no zero padding, no trailing '.0'.
    Half-strikes keep their decimal. Verbatim behaviour of the old
    dxlink.occ_to_dx, which was correct — it is moved, not rewritten.
    """
    p = parse(occ)
    if not p:
        return None
    root, ymd, cp, k = p
    ks = ("%.3f" % k).rstrip("0").rstrip(".")
    return ".%s%s%s%s" % (root, ymd, cp, ks)


def from_dx(dx):
    """dxfeed -> OCC, or None. The exact inverse of to_dx()."""
    s = str(dx or "").strip()
    if not s.startswith("."):
        return None
    s = s[1:]
    i = 0
    while i < len(s) and s[i].isalpha():
        i += 1
    root, rest = s[:i], s[i:]
    if not root or len(rest) < 8 or not rest[:6].isdigit():
        return None
    ymd, cp, strike = rest[:6], rest[6:7], rest[7:]
    if cp not in ("C", "P"):
        return None
    try:
        return "%s%s%s%08d" % (root.upper(), ymd, cp,
                               int(round(float(strike) * 1000)))
    except ValueError:
        return None


def is_occ(s):
    return parse(s) is not None
