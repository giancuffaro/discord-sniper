/* whop-awake.js — runs in the PAGE's world (world: "MAIN"), not the
 * extension's. It does one thing: convince Whop the tab is visible.
 *
 * MEASURED 9/18 (two Trading Chat tabs side by side, both hidden, 4 min):
 * the plain tab was still showing a 1:42 PM message while a tab with this
 * spoof showed 1:49 PM — and a fresh load confirmed 1:49 PM was the newest.
 * Whop's app only refetches / renders new posts while it believes the tab
 * is visible (document.visibilityState !== "hidden"). Every Sniper Whop
 * tab is a background tab all day, so the feed FROZE at load and the only
 * thing the reader ever saw was the 30-minute backstop reload — which is
 * why every Whop capture on 9/18 (and most of 9/17) was <history> and not
 * one Whop call was traded.
 *
 * This lies to the page, not to Chrome: timers stay throttled, nothing is
 * kept awake that Chrome would otherwise sleep. Idempotent — a second
 * inject is a no-op. */
(function () {
  if (window.__SNIPER_AWAKE__) return;
  window.__SNIPER_AWAKE__ = true;
  try {
    Object.defineProperty(document, "visibilityState",
                          { get: function () { return "visible"; }, configurable: true });
    Object.defineProperty(document, "hidden",
                          { get: function () { return false; }, configurable: true });
    try { document.hasFocus = function () { return true; }; } catch (e) {}
    // Tell whatever already subscribed (react-query's focusManager listens to
    // these) that the tab just became visible, so a feed that already froze
    // refetches now instead of at the next real focus.
    document.dispatchEvent(new Event("visibilitychange"));
    window.dispatchEvent(new Event("focus"));
    window.dispatchEvent(new Event("pageshow"));
  } catch (e) { /* a locked-down document; the reload path still works */ }
})();
