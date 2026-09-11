"""test_architecture.py — does ARCHITECTURE.md still match the source?

    python test_architecture.py          (exit 0 = the map is honest)

WHY (9/7/26)
------------
A map written in prose goes stale silently. That is the known weakness of
documentation, and G named it before I wrote a line: *"it can go stale
silently, which is exactly how I got confused reading confident comments
that were out of date."*

So the load-bearing claims in ARCHITECTURE.md are asserted HERE, against the
real source, by parsing it. When someone renames `buying_power()` or flips
the tuple order of `QuoteBus.get`, this fails and the map gets fixed instead
of quietly lying to the next session.

Every claim below is one a previous session got WRONG in live code:

    called client_from_settings()      -> name that does not exist
    called balance()                   -> wrong name
    WebullOptions(sub-dict)            -> wrong input
    read QUOTES.get as (bid, ask)      -> wrong output
    backed off on an exception         -> wrong failure mode (429 returns [])
    returned a tuple from do_POST      -> wrong output shape

WRITE THE CHECKS WITH AST, NOT WITH grep
----------------------------------------
The first version of this file used string search and reported that
`priority=True` was passed by a caller. It is not — the only occurrence in
the repo is inside `Budget.take`'s own DOCSTRING. A test that reads comments
as code is a test that will lie to you, which is the exact failure it exists
to prevent. Parse the tree; ask the tree.
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAILED = []


def tree(name):
    return ast.parse(open(os.path.join(HERE, name), encoding="utf-8",
                          errors="replace").read())


def klass(t, name):
    for c in t.body:
        if isinstance(c, ast.ClassDef) and c.name == name:
            return c
    return None


def methods(cls):
    return {m.name for m in cls.body if isinstance(m, ast.FunctionDef)}


def check(label, cond, detail=""):
    if cond:
        print("  OK    %s" % label)
    else:
        print("  WRONG %s   %s" % (label, detail))
        FAILED.append(label)


def call_sites(kwarg, value_is_true=True):
    """Every REAL call passing `kwarg=True` — parsed, so docstrings and
    comments cannot vote."""
    out = []
    for f in os.listdir(HERE):
        # Production callers only. A test that PROVES the priority lane still
        # serves an order instantly is not a caller of it — it is the thing
        # that checks it works, and counting it here would mean the guard
        # could only pass while the behaviour was untested. (9/11)
        if not f.endswith(".py") or f.startswith("test_") \
                or f == os.path.basename(__file__):
            continue
        try:
            t = tree(f)
        except SyntaxError:
            continue
        for n in ast.walk(t):
            if not isinstance(n, ast.Call):
                continue
            for kw in n.keywords:
                if kw.arg != kwarg:
                    continue
                v = kw.value
                is_true = isinstance(v, ast.Constant) and v.value is True
                if is_true == value_is_true:
                    out.append("%s:%d" % (f, n.lineno))
    return out



def _refuses(fn):
    try:
        fn()
        return False
    except Exception:
        return True


def main():
    print("ARCHITECTURE.md vs the source\n")

    # --- webull_options: the module that got me three times ---------------
    wo_src = open(os.path.join(HERE, "webull_options.py"),
                  encoding="utf-8", errors="replace").read()
    wo = klass(tree("webull_options.py"), "WebullOptions")
    m = methods(wo)
    check("WebullOptions.buying_power exists", "buying_power" in m)
    check("WebullOptions.balance does NOT exist", "balance" not in m,
          "the map says there is no balance(); add it to the map if there is")
    check("WebullOptions.connect exists", "connect" in m)
    check("no module-level client_from_settings",
          "def client_from_settings" not in wo_src)
    init = [x for x in wo.body
            if isinstance(x, ast.FunctionDef) and x.name == "__init__"][0]
    check("ctor reads execution.webull itself (takes WHOLE config)",
          "execution" in ast.unparse(init))

    # --- the 429-does-not-raise contract ----------------------------------
    check("_try_calls returns on 429 rather than raising",
          "return None, \" | \".join(errors)" in wo_src
          or "return (None," in wo_src,
          "if this changed, the futures-position backoff must change too")

    # --- quote_bus: tuple order and the reserve ---------------------------
    qb = tree("quote_bus.py")
    get = [x for x in klass(qb, "QuoteBus").body
           if isinstance(x, ast.FunctionDef) and x.name == "get"][0]
    check("QuoteBus.get documents (ask, bid, row) — ASK FIRST",
          "ask, bid, row" in (ast.get_docstring(get) or ""))
    take = [x for x in klass(qb, "Budget").body
            if isinstance(x, ast.FunctionDef) and x.name == "take"][0]
    check("Budget.take takes priority and reserve",
          {a.arg for a in take.args.args} >= {"priority", "reserve"})
    sites = call_sites("priority")
    check("priority=True is passed by NO caller (it is a reserve floor, "
          "not a priority lane)", not sites, "found at %s" % sites)
    check("ORDER_RESERVE still exists",
          "ORDER_RESERVE" in open(os.path.join(HERE, "quote_bus.py"),
                                  encoding="utf-8").read())

    # --- dxlink: the shadow feed must stay unwired ------------------------
    gb = methods(klass(tree("dxlink.py"), "GreeksBus"))
    check("GreeksBus exposes get/quote/watch/quote_tape_to",
          {"get", "quote", "watch", "quote_tape_to"} <= gb)
    readers = []
    for f in os.listdir(HERE):
        if not f.endswith(".py") or f in ("dxlink.py", os.path.basename(__file__)):
            continue
        try:
            t = tree(f)
        except SyntaxError:
            continue
        for n in ast.walk(t):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "quote"
                    and getattr(n.func.value, "id", "") in ("GREEKS", "greeks")):
                readers.append("%s:%d" % (f, n.lineno))
    check("shadow quote feed has ZERO consumers (still read by nothing)",
          not readers, "read at %s" % readers)

    # --- positions ---------------------------------------------------------
    bk = klass(tree("positions.py"), "Book")
    pub = [x.name for x in bk.body
           if isinstance(x, ast.FunctionDef) and not x.name.startswith("_")]
    check("Book still exposes the money-critical methods",
          {"entry_sent", "trim", "claim", "release", "finish", "adopt",
           "reconcile_gone", "auto_ratchet", "auto_ladder",
           "rearm_overnight_stops"} <= set(pub))

    # --- telemetry integrity labels ---------------------------------------
    sys.path.insert(0, HERE)
    import telemetry as tm
    check("integrity BROKER only for a live fill with a broker",
          tm.integrity_of({"live": 1, "fill": 1.0}, True) == "BROKER")
    check("integrity ASSUMED with no broker",
          tm.integrity_of({"live": 1, "fill": 1.0}, False) == "ASSUMED")
    check("integrity PAPER on the test path",
          tm.integrity_of({"live": 0, "fill": 1.0}, True) == "PAPER")
    check("integrity never silently trusts an unknown row",
          tm.integrity_of({"live": 1}, True) == "UNKNOWN")

    # --- the documented circular dependency -------------------------------
    wf = open(os.path.join(HERE, "webull_futures.py"),
              encoding="utf-8", errors="replace").read()
    check("known cycle still present (map warns about it)",
          "import bridge" in wf or "from bridge" in wf,
          "if this is gone, DELETE the warning from ARCHITECTURE.md")


    # --- 9/7 consolidations ------------------------------------------------
    import occ as _o
    check("occ.build refuses a side it cannot read",
          _refuses(lambda: _o.build("SPY", "2026-09-08", "bull", 640)))
    check("occ.build accepts CALLS/call/C alike",
          _o.build("SPY", "2026-09-08", "CALLS", 640)
          == _o.build("SPY", "2026-09-08", "c", 640)
          == "SPY260908C00640000")
    check("occ round-trips through dxfeed",
          _o.from_dx(_o.to_dx("IWM260904P00243500")) == "IWM260904P00243500")
    hand = []
    for f in os.listdir(HERE):
        if not f.endswith(".py") or f in ("occ.py", os.path.basename(__file__)):
            continue
        txt = open(os.path.join(HERE, f), encoding="utf-8",
                   errors="replace").read()
        if "%08d" in txt and "1000" in txt:
            hand.append(f)
    check("no hand-rolled OCC construction outside occ.py", not hand,
          "found in %s" % hand)
    import tape as _t
    # 9/9: this asserted an EXACT set of four and went stale the day the
    # despiked clean tape and missed_tape were registered — tape.SOURCES is
    # now six. The point of the check is "one reader for every source", so
    # assert that shape instead: the four core sources must still be there
    # (catches a removal), and EVERY registered source must be reachable
    # through the same reader interface (catches a half-wired addition).
    _core = {"webull", "tasty_greeks", "tasty_quote", "databento"}
    _missing = _core - set(_t.SOURCES)
    _unreadable = [s for s in _t.SOURCES if not _t.path(s)]
    check("tape.py exposes one reader for every source",
          hasattr(_t, "rows") and hasattr(_t, "at") and not _missing,
          "missing %s" % sorted(_missing) if _missing else "")
    check("every registered tape source resolves to a path",
          not _unreadable, "no path for %s" % _unreadable)
    bsrc = open(os.path.join(HERE, "bridge.py"), encoding="utf-8",
                errors="replace").read()
    check("state is written atomically (tmp + fsync + os.replace)",
          "os.replace(tmp, path)" in bsrc and "os.fsync" in bsrc)
    check("load_state no longer swallows corruption",
          "is CORRUPT" in bsrc)
    jsrc = open(os.path.join(HERE, "jsparse.py"), encoding="utf-8",
                errors="replace").read()
    check("jsparse announces when it uses the stale mirror",
          "USED_MIRROR" in jsrc and "PYTHON MIRROR" in jsrc)

    # --- the map itself has to exist --------------------------------------
    check("ARCHITECTURE.md is present",
          os.path.exists(os.path.join(HERE, "ARCHITECTURE.md")))

    print()
    if FAILED:
        print("  %d CLAIM(S) IN ARCHITECTURE.md NO LONGER MATCH THE SOURCE."
              % len(FAILED))
        print("  Fix the code if the code is wrong, fix the map if the map")
        print("  is wrong, and never leave both.")
        return 1
    print("  The map matches the source.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
