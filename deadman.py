"""deadman.py — nothing in this bot may die quietly.

    import deadman; deadman.arm(note)

WHY (9/7/26)
------------
G asked what expert engineers do to find errors faster. The answer that fits
this codebase is not a framework — it is one measured fact:

    threads started                    23
    except: pass                      174
    except with NO log at all         274
    except that RETURNS a sentinel     61

and, before this file existed, **nothing anywhere caught a thread that died.**

That is the single most expensive failure shape here. Python's default is
that an exception escaping `Thread.run()` is printed to stderr and the
thread is simply GONE. The process keeps running. The popup still draws.
The bridge still answers. But the ratchet is no longer being managed, no
stop is being moved, and nothing anywhere says so — you find out from your
account.

Joe Duffy calls this class of bug out by name in "The Error Model": a
silently swallowed error meant 80% of requests returned gibberish and
"failing in a way the developers immediately saw" is exactly what did NOT
happen. Google's SRE book makes the same point from the operator's side:
exposing current state is worth more than any amount of after-the-fact log
archaeology.

WHAT THIS DOES — four hooks, all stdlib, ~zero cost
---------------------------------------------------
1. `threading.excepthook`  — a worker thread dying now writes a CRITICAL
   line naming the thread and its traceback, and marks it dead in a
   registry. (3.8+; before that the exception was unreachable.)
2. `sys.excepthook`        — same for the main thread.
3. `sys.unraisablehook`    — exceptions inside __del__ / GC, which Python
   prints and swallows BY DESIGN. Rare, and invisible without this.
4. `faulthandler`          — a hard fault (segfault, C-level crash in the
   SDK) dumps every thread's stack instead of vanishing.

Plus `watch()`: a heartbeat registry so a thread that is alive but STUCK —
blocked on a socket that never returns, which reads exactly like "a quiet
market" — can be seen. A dead thread and a wedged thread look identical
from outside; both are silence.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not restart anything and it does not stop trading. Automatic
recovery in a process that places real orders is a second system that can
be wrong, and a restart that re-arms a stop from stale state is worse than
a loud stop. This tells you and the log. Deciding is yours.
"""
import faulthandler
import os
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "deadman.log")

_LOCK = threading.Lock()
_BEATS = {}          # name -> (last_beat_ts, max_silence_s)
_DEAD = {}           # name -> (ts, one-line reason)
_note = None
_armed = False


def _say(line):
    """Say it three ways: the caller's own logger, our file, and stderr.
    A death notice that itself depends on one working channel is not a
    death notice."""
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        if _note:
            _note(line)
    except Exception:                                       # noqa: BLE001
        pass
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (stamp, line))
    except OSError:
        pass
    try:
        sys.stderr.write("%s  %s\n" % (stamp, line))
    except Exception:                                       # noqa: BLE001
        pass


def _thread_died(args):
    name = getattr(args.thread, "name", "?") if args.thread else "?"
    exc = "".join(traceback.format_exception(
        args.exc_type, args.exc_value, args.exc_traceback))[-1200:]
    with _LOCK:
        _DEAD[name] = (time.time(), "%s: %s" % (
            getattr(args.exc_type, "__name__", "?"),
            str(args.exc_value)[:120]))
    _say("THREAD DEAD  '%s' stopped on an unhandled %s — it is NOT coming "
         "back, and whatever it was doing is no longer being done. Check "
         "your open positions against Webull."
         % (name, getattr(args.exc_type, "__name__", "?")))
    _say("THREAD DEAD  '%s' traceback:\n%s" % (name, exc))


def _main_died(etype, evalue, etb):
    _say("MAIN THREAD DIED on %s: %s"
         % (getattr(etype, "__name__", "?"), str(evalue)[:160]))
    try:
        _say("".join(traceback.format_exception(etype, evalue, etb))[-1600:])
    except Exception:                                       # noqa: BLE001
        pass


def _unraisable(u):
    # Exceptions in __del__ and during GC. Python prints these and moves on
    # BY DESIGN — they are invisible unless you ask for them.
    _say("UNRAISABLE  %s in %r — swallowed by Python by design, surfaced here"
         % (getattr(u.exc_type, "__name__", "?"), u.object))


def arm(note=None, fault_dump_seconds=0):
    """Install the hooks. Call ONCE, as early as possible.

    fault_dump_seconds > 0 also dumps EVERY thread's stack on that interval
    to deadman.log — for hunting a wedge. Off by default: it is noisy, and
    a stack dump every N seconds in a live log is its own problem.
    """
    global _note, _armed
    _note = note
    if _armed:
        return
    _armed = True
    try:
        threading.excepthook = _thread_died          # 3.8+
    except Exception:                                       # noqa: BLE001
        pass
    sys.excepthook = _main_died
    try:
        sys.unraisablehook = _unraisable             # 3.8+
    except Exception:                                       # noqa: BLE001
        pass
    try:
        faulthandler.enable(file=open(LOG, "a", encoding="utf-8"))
        if fault_dump_seconds:
            faulthandler.dump_traceback_later(float(fault_dump_seconds),
                                              repeat=True)
    except Exception:                                       # noqa: BLE001
        pass
    _say("DEADMAN armed — a thread that dies will say so instead of "
         "vanishing.")


def beat(name, every=60.0):
    """Call from inside a loop you care about. `every` is how long silence
    is allowed before `stalled()` reports it."""
    with _LOCK:
        _BEATS[name] = (time.time(), float(every))


def stalled():
    """[(name, seconds_silent, allowed)] for every heartbeat gone quiet.

    A STUCK thread and a DEAD thread look the same from outside — both are
    silence — so both are reported, separately.
    """
    now = time.time()
    out = []
    with _LOCK:
        for n, (t, allow) in _BEATS.items():
            if now - t > allow:
                out.append((n, round(now - t, 1), allow))
    return sorted(out, key=lambda x: -x[1])


def dead():
    with _LOCK:
        return {k: v for k, v in _DEAD.items()}


def report():
    """One dict for /debug/state and for health.py."""
    alive = {t.name for t in threading.enumerate()}
    return {"armed": _armed, "threads_alive": sorted(alive),
            "thread_count": len(alive), "dead": dead(), "stalled": stalled()}


if __name__ == "__main__":
    # Prove it: start a thread that dies, and show that it is NOT silent.
    arm(note=lambda s: None)
    print("before:", len(threading.enumerate()), "threads\n")

    def boom():
        raise ValueError("pretend the ratchet watchdog hit a bad quote")

    t = threading.Thread(target=boom, name="ratchet-watchdog")
    t.start()
    t.join()
    time.sleep(0.2)
    d = dead()
    print("\ndead threads seen:", list(d))
    print("reason:", d.get("ratchet-watchdog", ("", "?"))[1])
    print("\nWithout deadman this printed to stderr and the thread was gone,")
    print("with nothing in trades.log and nothing in the popup.")
