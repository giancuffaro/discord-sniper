"""eastern.py — what time it is in New York, on any machine, always.

Why this file exists:

Python asks the operating system for the world's timezone rules. Linux and Mac
ship them. **Windows does not.** So `ZoneInfo("America/New_York")` works fine
everywhere I build this and then dies on your PC with:

    ZoneInfoNotFoundError: 'No time zone found with key America/New_York'

The normal fix is `pip install tzdata`, and that's now in requirements.txt. But
"normal fix" isn't good enough for the one clock this whole thing runs on. If
that install is ever missed — new PC, fresh Python, a reinstall that didn't
finish — the bridge would refuse to start, and it'd do it at 9:25am.

So: use the real timezone database when it's there, and when it isn't, fall
back to the US Eastern rule written out by hand below. The rule has been the
same since 2007 and is set by law, not by a file on your disk. Worst case the
fallback is running and Congress changes daylight saving; then the clock is an
hour out for a few weeks and the fix is `pip install tzdata`.

Nothing here can raise. This module is imported before anything else works.
"""

from datetime import datetime, timedelta, timezone, tzinfo

__all__ = ["ET", "now", "source"]

_HAVE_TZDATA = False
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
    _HAVE_TZDATA = True
except Exception:                                    # noqa: BLE001
    ET = None


def _nth_weekday(year, month, weekday, n):
    """The n-th <weekday> of a month. weekday: Monday=0 … Sunday=6."""
    d = datetime(year, month, 1)
    shift = (weekday - d.weekday()) % 7
    return d + timedelta(days=shift + 7 * (n - 1))


class _USEastern(tzinfo):
    """US Eastern by the rule, for when the timezone database isn't installed.

    Since 2007: daylight time starts 2am local on the second Sunday in March and
    ends 2am local on the first Sunday in November.
    """

    def _is_dst(self, dt):
        y = dt.year
        start = _nth_weekday(y, 3, 6, 2).replace(hour=2)     # 2nd Sunday, March
        end = _nth_weekday(y, 11, 6, 1).replace(hour=2)      # 1st Sunday, Nov
        naive = dt.replace(tzinfo=None)
        return start <= naive < end

    def utcoffset(self, dt):
        if dt is None:
            return timedelta(hours=-5)
        return timedelta(hours=-4 if self._is_dst(dt) else -5)

    def dst(self, dt):
        if dt is None:
            return timedelta(0)
        return timedelta(hours=1) if self._is_dst(dt) else timedelta(0)

    def tzname(self, dt):
        return "EDT" if (dt is not None and self._is_dst(dt)) else "EST"

    def fromutc(self, dt):
        """Convert a UTC instant to New York time.

        This is the path every clock reading in the project actually takes
        (`datetime.now(ET)` and `.astimezone(ET)` both land here), so it's done
        in UTC rather than in wall-clock time. Wall-clock is ambiguous for one
        hour every November — 1:30am happens twice — and comparing UTC instants
        sidesteps that instead of guessing. Checked against the real timezone
        database minute-by-minute over five years: the clock time is identical
        at every single point. (The EST/EDT *label* differs for the one repeated
        hour at 1am on the November Sunday, where "EST or EDT" genuinely has two
        answers. The time is right, and nothing here trades at 1am.)
        """
        y = dt.year
        # 2am EST is 07:00 UTC; 2am EDT is 06:00 UTC.
        start = _nth_weekday(y, 3, 6, 2).replace(hour=7)
        end = _nth_weekday(y, 11, 6, 1).replace(hour=6)
        naive = dt.replace(tzinfo=None)
        hours = -4 if start <= naive < end else -5
        return (dt + timedelta(hours=hours)).replace(tzinfo=self)


if ET is None:
    ET = _USEastern()


def now():
    """The current time in New York. Use this instead of datetime.now(ET)."""
    return datetime.now(timezone.utc).astimezone(ET)


def source():
    """Plain-language note about which clock is in use, for startup messages."""
    if _HAVE_TZDATA:
        return "system timezone database"
    return ("built-in US Eastern rule — the tzdata package isn't installed. "
            "That's fine, but 'pip install tzdata' is the tidier fix")
