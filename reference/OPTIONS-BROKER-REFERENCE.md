# US Options Mechanics and Broker API Reference (fact-checked 2026-09-02)

Scope: reference for a Python bot trading US equity options on the Webull OpenAPI, plus mechanics every option bot must respect and a survey of other broker APIs. Every factual claim carries an inline `(source: URL)`. Anything not confirmed from a primary page is marked **UNVERIFIED**. Times are US Eastern.

---

## A) WEBULL OPENAPI (live broker)

### A1. Rate limits
- Limits are per `app_key` (all requests sharing one key share one quota), per endpoint (independent counters), and expressed as `N/Ts` (source: https://developer.webull.com/apis/docs/rate-limits.md).
- Exceeding a limit returns HTTP **429 Too Many Requests**; the request is rejected with no partial processing; repeated abuse can cause temporary IP-level blocking (source: https://developer.webull.com/apis/docs/rate-limits.md).
- Trading endpoints, Production (Sandbox is 30/60s for all): Place Order 600/60s; Batch Place 150/60s; Replace 600/60s; Cancel 600/60s; Preview 150/10s; Open Orders 2/2s; Order Detail 2/2s; Order History 2/2s; Account Balance 2/2s; Positions 2/2s; Account List 10/30s; Get Option Contracts 60/60s (source: https://developer.webull.com/apis/docs/rate-limits.md).
- Market Data (non-display) Production: Option Snapshot 60/60s, Option Historical Bars 60/60s, Option Tick 60/60s, Streaming Subscribe/Unsubscribe 60/60s; Sandbox 30/60s (source: https://developer.webull.com/apis/docs/rate-limits.md). The Market Data FAQ separately states "300 requests per 60 seconds" for the Data API (HTTP) and no limit for MQTT subscribe/unsubscribe (source: https://developer.webull.com/apis/docs/market-data-api/faq.md). The two pages disagree; treat the per-endpoint 60/60s table as binding and the 300/60s as an aggregate. Which one the server actually enforces: **UNVERIFIED**.
- MQTT streaming: max 5 concurrent connections per App Key (error 105); server pushes at most 3 messages/sec per connection; state retained ~1 minute after disconnect (source: https://developer.webull.com/apis/docs/market-data-api/data-streaming-api.md).
- Bot rule: Open Orders / Order Detail / Positions at 2/2s means a polling loop cannot exceed ~1 req/s per endpoint per app key across ALL accounts and processes using that key.

### A2. Order types and TIF for options
- Options support only `LIMIT`, `STOP_LOSS` (stop-market), `STOP_LOSS_LIMIT`. `MARKET` and `TRAILING_STOP_LOSS` are NOT supported for options. Sides `BUY`/`SELL` only (no `SHORT`) (source: https://developer.webull.com/apis/docs/trade-api/options.md; source: https://developer.webull.com/apis/docs/trade-api/faq.md).
- Feature matrix: Options: Market X, Limit ✓, Stop Loss ✓, Stop Loss Limit ✓, Trailing X, Algo X, Extended Hours "-", Overnight "-" (source: https://developer.webull.com/apis/docs/trade-api/overview.md).
- TIF: `DAY` or `GTC`. **Options SELL-side orders support DAY only; GTC is buy-side only** (source: https://developer.webull.com/apis/docs/trade-api/options.md). So a protective sell stop on a long option is always DAY and dies at the close. GTC max duration "typically 60 days" (source: https://developer.webull.com/apis/docs/reference/common-order-place.md); retail help: all open GTC orders expire 60 calendar days after placement (source: https://www.webull.com/learn/rgpBdy/DbpPvC/GTC-for-Options-Trading).
- Extended hours: `support_trading_session` (`CORE`/`ALL`/`NIGHT`) is "Applicable to U.S. stock market orders only" (source: https://developer.webull.com/apis/docs/reference/common-order-place.md). Options extended hours = not applicable (source: https://developer.webull.com/apis/docs/trade-api/overview.md).
- `entrust_type` must be `QTY`; `position_intent` (`BUY_TO_OPEN`/`BUY_TO_CLOSE`/`SELL_TO_OPEN`/`SELL_TO_CLOSE`) was added to Place Order for option orders; for combos it may only be set on the MASTER (source: https://developer.webull.com/apis/docs/changelog.md).
- Legs: each `legs[]` item needs `side, quantity, symbol, strike_price, option_expire_date (YYYY-MM-DD), instrument_type=OPTION, option_type=CALL|PUT, market=US`; order-level `symbol` is the underlying (source: https://developer.webull.com/apis/docs/trade-api/options.md).

### A3. Combo / bracket orders for options
- `combo_type` values: `NORMAL`, `MASTER`, `STOP_PROFIT`, `STOP_LOSS`, `OTO`, `OCO`, `OTOCO` (source: https://developer.webull.com/apis/docs/reference/common-order-place.md).
- For options: MASTER / STOP_PROFIT / STOP_LOSS combos are supported ONLY when `option_strategy = SINGLE`; multi-leg strategies allow `NORMAL` only. **OTO, OCO and OTOCO are stock-only; option orders (even SINGLE) do not support them** (source: https://developer.webull.com/apis/docs/reference/common-order-place.md). Note the Trading API Overview feature matrix marks "Combo Orders (OTO/OCO/OTOCO)" ✓ for Options (source: https://developer.webull.com/apis/docs/trade-api/overview.md) — this contradicts the endpoint reference; trust the endpoint reference.
- Sub-order table: MASTER accepts `MARKET, LIMIT` (qty 1 order); STOP_PROFIT accepts `LIMIT` (0-1); STOP_LOSS accepts `STOP_LOSS` (0-1). Since options cannot use MARKET, an option MASTER must be LIMIT and the stop leg is stop-market `STOP_LOSS` (a `STOP_LOSS_LIMIT` leg is not listed for the TP/SL scenario) (source: https://developer.webull.com/apis/docs/reference/common-order-place.md).
- To attach TP/SL to an EXISTING position: submit only STOP_PROFIT/STOP_LOSS sub-orders (side=SELL) under one `client_combo_order_id`; no MASTER is required or supported in that case (source: https://developer.webull.com/apis/docs/reference/common-order-place.md).
- `client_combo_order_id`: not needed for NORMAL; if omitted for non-NORMAL the server generates one (source: https://developer.webull.com/apis/docs/reference/common-order-place.md). Combo orders need a `client_combo_order_id` plus a unique `client_order_id` per leg (source: https://developer.webull.com/apis/docs/trade-api/stock.md).
- Error envelope: business rejections come back as HTTP **417** with `{error_code, message}` (example `OPENAPI_NO_NIGHT_TRADING_TIME`); 401 `UNAUTHORIZED`; 500 `SYSTEM_ERROR` (source: https://developer.webull.com/apis/docs/reference/common-order-place.md).
- Specific codes `STOP_PRICE_MUST_BE_LESS_THAN_MARKET_PRICE`, `OPTION_PRICE_STEP_LT`, `OPTION_STRATEGY_NOT_MATCH_ANY`: **not published in the OpenAPI docs (UNVERIFIED officially)**. They are observed in this team's own logs: `OPTION_PRICE_STEP_LT` on off-tick limit prices; `STOP_PRICE_MUST_BE_LESS_THAN_MARKET_PRICE` when a SELL stop is validated against the live market (not your fill); `OPTION_STRATEGY_NOT_MATCH_ANY` on every options order sent to the SANDBOX (source: team files `C:\Users\Hulk\Desktop\discord-sniper\webull_options.py` lines 193, 1045, 1574 and `HANDOFF.md` line 321). The official FAQ lists only generic rejection causes (buying power, market closed, invalid params, missing agreements) (source: https://developer.webull.com/apis/docs/trade-api/faq.md).

### A4. Replace / modify order
- Endpoint `POST /trading/orders/replace` ("Replace Order"), body `{account_id, modify_orders:[...]}`; each item requires the ORIGINAL `client_order_id` (reused, not a new one) and may change `time_in_force, stop_price, limit_price, quantity, order_type, trailing_type, trailing_stop_step`; for option orders `legs[] {id, quantity}` is "Only required when modifying option orders" (source: https://developer.webull.com/apis/docs/reference/common-order-replace.md).
- Response returns `client_order_id`, `order_id` (NORMAL) or `client_combo_order_id`/`combo_order_id` (combos) (source: https://developer.webull.com/apis/docs/reference/common-order-replace.md).
- The doc only spells out field-change rules for FUTURES (e.g. limit -> only `order_type,time_in_force,quantity,limit_price`; stop -> `stop_price`). Equivalent constraints for options: **UNVERIFIED**; assume the same shape and test in production with 1 contract.
- Rate limit 600/60s prod (source: https://developer.webull.com/apis/docs/rate-limits.md).

### A5. Price step / tick rules
- No Webull page publishes an option tick table; the exchange rules apply (see B2). The `Get Option Contracts` endpoint returns a `ppind` "Penny Program Indicator: true = Penny Pilot contract" per contract, plus `style` (AMERICAN/EUROPEAN), `root_symbol` (e.g. SPXW), `status` (LISTING/DELISTING), strike bounds and a `pagination_key` (source: https://developer.webull.com/apis/docs/reference/option-contract-list.md). Use `ppind` to pick $0.01/$0.05 vs $0.05/$0.10.
- Team observation: off-tick limit price -> HTTP 417 `OPTION_PRICE_STEP_LT` (source: team file `webull_options.py` line 193; **UNVERIFIED in official docs**).

### A6. Market data for options
- Option Snapshot: `GET /market-data/options/snapshots/list?symbols=...&category=US_OPTION`; symbols are OCC compact form (`AAPL260522C00300000`), **maximum 20 symbols per query**; returns last `price`, OHLC, `pre_close`, `volume`, `open_interest`, greeks (`delta, gamma, theta, vega, rho, imp_vol`), and **`bid`, `ask`, `bid_size`, `ask_size`** (source: https://developer.webull.com/apis/docs/reference/option-snapshot.md).
- Option Historical Bars: `GET /market-data/options/bars/list`, category `US_OPTION` only, max 20 symbols, `timespan` M1/M5/M15/M30/M60/M120/M240/D/W/M/Y, `count` max 1200 (default 200), `real_time_required` flag (source: https://developer.webull.com/apis/docs/reference/option-historical-bars.md). Option Tick: one symbol, `count` max 1200 (source: https://developer.webull.com/apis/docs/reference/option-tick.md). These three endpoints were added under "Non-Display Solution" per the changelog (source: https://developer.webull.com/apis/docs/changelog.md).
- Streaming (MQTT): supported categories are Stocks, ETFs, Futures, Crypto, Event Contracts; the Subscribe endpoint `category` enum is `US_STOCK`, `US_ETF` (max 100 symbols per call; sub_types `QUOTE`, `SNAPSHOT`, `TICK`) (source: https://developer.webull.com/apis/docs/market-data-api/data-streaming-api.md; source: https://developer.webull.com/apis/docs/reference/subscribe.md). **No option streaming exists — option quotes must be polled via the snapshot endpoint (60/60s).**
- Entitlement: US options require "OPRA Real-Time Non-display for options last sale and quotation"; app/desktop subscriptions do NOT carry over — an OpenAPI-specific subscription is required; only one device may access LV1/LV2 at a time (source: https://developer.webull.com/apis/docs/market-data-api/overview.md; source: https://developer.webull.com/apis/docs/market-data-api/faq.md). Subscribe via webullapp.com -> Advanced Quotes -> OpenAPI Advanced Quotes (source: https://developer.webull.com/apis/docs/market-data-api/subscribe-quotes.md).
- MQTT payloads are protobuf (only `notice` is JSON); subscriptions are NOT restored after reconnect — resubscribe (source: https://developer.webull.com/apis/docs/market-data-api/faq.md).

### A7. Order fill events (gRPC trade events)
- "Subscribe Trade Events" is a gRPC server-streaming connection at `events-api.webull.com` (prod) / `events-api.sandbox.webull.com` (test); it pushes `scene_type` = `FILLED` (partial), `FINAL_FILLED`, `PLACE_FAILED`, `MODIFY_SUCCESS`, `MODIFY_FAILED`, `CANCEL_SUCCESS`, `CANCEL_FAILED`; `subscribeType` only supports 1 (source: https://developer.webull.com/apis/docs/reference/custom/subscribe-trade-events.md; source: https://developer.webull.com/apis/docs/sdk.md).
- Event types on the stream: `SubscribeSuccess, Ping, AuthError, NumOfConnExceed, SubscribeExpired` — handle `SubscribeExpired` by resubscribing (source: https://developer.webull.com/apis/docs/reference/custom/subscribe-trade-events.md).
- New SDK usage: `from webull.trade.trade_events_client import TradeEventsClient`, `do_subscribe([account_id])`, callback `on_events_message(event_type, subscribe_type, payload, raw)` (source: https://developer.webull.com/apis/docs/reference/custom/subscribe-trade-events.md). Position events also exist ("Subscribe Position Events") (source: https://developer.webull.com/apis/llms.txt).
- The PyPI package `webull-python-sdk-trade-events-core` (0.1.18, 2025-08-31) is the gRPC events module of the OLD SDK family, pinned to `grpcio==1.51.1`, `grpcio-tools==1.51.1`, `protobuf==4.21.12` (source: https://pypi.org/pypi/webull-python-sdk-trade-events-core/json).

### A8. Sandbox vs production (options)
- Hosts: prod `api.webull.com` (HTTP), `events-api.webull.com` (gRPC), `data-api.webull.com` (MQTT); test `api.sandbox.webull.com`, `events-api.sandbox.webull.com`, `data-api.sandbox.webull.com` (source: https://developer.webull.com/apis/docs/sdk.md). The llms.txt still lists older UAT hosts (`us-openapi-alb.uat.webullbroker.com`) (source: https://developer.webull.com/apis/llms.txt).
- Sandbox trading API application is auto-approved in minutes; production key review takes 1-2 business days; sandbox data does not sync to production (source: https://developer.webull.com/apis/docs/authentication/IndividualApplicationAPI.md).
- Sandbox market data that needs a subscription is **15-minute delayed** by default; it becomes real-time only if you hold the production real-time subscription (source: https://developer.webull.com/apis/docs/market-data-api/overview.md).
- Sandbox rate limits are 30/60s on every endpoint (source: https://developer.webull.com/apis/docs/rate-limits.md).
- Whether the sandbox accepts option ORDERS at all: **UNVERIFIED officially**; this team saw 100% of sandbox option orders rejected with `OPTION_STRATEGY_NOT_MATCH_ANY` on 2026-08-28 (source: team `HANDOFF.md` line 321). Do not use the sandbox to test option order flow.

### A9. The two Python SDK families
- NEW (official, current): `pip install webull-openapi-python-sdk`, import namespace `webull.*` (`from webull.core.client import ApiClient`, `from webull.trade.trade_client import TradeClient`), Python 3.8-3.14, repo github.com/webull-inc/webull-openapi-python-sdk (source: https://developer.webull.com/apis/docs/sdk.md). PyPI 2.0.19 (2026-08-31), requires `<3.15,>=3.8`, deps: `paho-mqtt<2,>=1.6.1`, `protobuf<5,>=4.21.12` (py<3.12) / `<6,>=4.25` (py>=3.12), `grpcio<1.60` (py<3.12) / `<1.70` (3.12-3.13) / `>=1.75.1,<2` (3.14), `cryptography<42` (py<3.12) / `<43` (3.12-3.13) / `<55` (3.14) (source: https://pypi.org/pypi/webull-openapi-python-sdk/json).
- OLD (deprecated): repo github.com/webull-inc/openapi-python-sdk — "DEPRECATED — This project is no longer maintained ... development has moved to webull-openapi-python-sdk" (source: https://raw.githubusercontent.com/webull-inc/openapi-python-sdk/main/README.md). Packages `webull-python-sdk-core`, `-trade`, `-mdata`, `-quotes-core`, `-trade-events-core` all at 0.1.18 (2025-08-31), import namespace `webullsdkcore` / `webullsdktrade` / `webullsdkmdata`, hard pins `paho-mqtt==1.6.1`, `grpcio==1.51.1`, `grpcio-tools==1.51.1`, `protobuf==4.21.12`, `cachetools==5.2.0` (source: https://pypi.org/pypi/webull-python-sdk-quotes-core/json; source: https://pypi.org/pypi/webull-python-sdk-core/json).
- Conflict: the old family's exact pins (`grpcio==1.51.1`, `protobuf==4.21.12`, `paho-mqtt==1.6.1`) collide with the new SDK's `grpcio>=1.60` on Python 3.12+ and with any modern protobuf 5.x/6.x or paho-mqtt 2.x in the same venv; `grpcio 1.51.1` has no wheels for Python 3.12+ (**UNVERIFIED** for 3.12 specifically; inferred from the new SDK's own per-version pins). Do not install both families in one environment.
- Unrelated: PyPI `webull` 0.6.1 (2023-01-10, "unofficial python interface", author ted chou) is a reverse-engineered app client, not the OpenAPI (source: https://pypi.org/pypi/webull/json).
- Auth gotcha: `INVALID_TOKEN` often means a signature mismatch (JSON body serialized differently than signed) rather than a bad token (source: https://developer.webull.com/apis/docs/trade-api/faq.md).

### A10. Retail-side facts relevant to the bot
- Webull retail stop/stop-limit for options: triggers "if the price hits $4.00 or below" (last-price wording; exact trigger source — trade vs bid/ask — **UNVERIFIED**) (source: https://www.webull.com/learn/GtulH5/f0J1g3/Protect-Your-Options-Positions-by-Using-Stop-Orders).
- Webull DOES offer index options (SPX, SPXW, VIX/VIXW, XSP, DJX, NDX, NDXP and others) with a $0.50/contract Webull fee plus exchange fees (source: https://www.webull.com/trading-investing/index-options). The OpenAPI contract list has a `root_symbol` filter "Mainly used for index options" (source: https://developer.webull.com/apis/docs/reference/option-contract-list.md). Placing index-option ORDERS through the OpenAPI: **UNVERIFIED** (team code reports a parameter error).

---

## B) GENERAL US OPTIONS MECHANICS

### B1. OCC/OSI symbol
- 21 chars: root left-justified padded with spaces to 6, `YYMMDD`, `C`/`P`, strike x1000 as 8 digits, e.g. `SPY   240119C00470000`; adjusted contracts add a digit to the root (`MSFT1`) (source: https://www.fidelity.com/research/options/osi.shtml; source: https://en.wikipedia.org/wiki/Option_symbol).
- Compact no-space form is used by Webull (`AAPL260522C00300000`) (source: https://developer.webull.com/apis/docs/reference/option-snapshot.md) and Alpaca (`AAPL231201P00175000`) (source: https://docs.alpaca.markets/reference/get-option-contract-symbol_or_id); tastytrade uses the padded form (`AAPL  230818C00197500`) (source: https://developer.tastytrade.com/docs/concepts/orders-and-order-types/).
- Index roots: `SPX` = AM-settled monthly, `SPXW` = PM-settled weeklies/dailies (source: https://www.cboe.com/tradable-products/sp-500/spx-options/spx-specifications).

### B2. Tick sizes
- Standard classes: $0.05 below $3.00, $0.10 at/above $3.00. Penny Interval Program classes: $0.01 below $3.00, $0.05 at/above (source: https://www.cboe.com/notices/content/?id=57916).
- QQQ, SPY, IWM quote in $0.01 at ALL price levels (source: https://www.sec.gov/files/rules/sro/cboe/2025/34-104157.pdf; source: https://help.firstrade.info/en/articles/9264852-in-what-price-increments-are-equity-and-index-options-quoted).
- Penny list rebalances: additions first trading day of January (top 300 most active classes with underlying < $200), removals first trading day of April (classes outside top 425); current CSVs: additions https://cdn.cboe.com/resources/membership/Penny-Additions_0102226.csv, removals https://cdn.cboe.com/resources/membership/Penny-Removals_040126.csv (source: https://www.cboe.com/notices/content/?id=57916).
- Bot rule: penny (or `ppind=true`) -> $0.01/$0.05; else $0.05/$0.10; SPY/QQQ/IWM -> $0.01 always. Rounding QQQ 4.66 up to 4.70 is legal but gives away 4 cents.

### B3. Trading hours
- Single-stock options 9:30-16:00 ET (source: https://www.nasdaqtrader.com/Trader.aspx?id=optionshours).
- Trade to 16:15 ET (Nasdaq list): DBA, DBB, DBC, DBO, DIA, DRAM, EEM, EFA, EWY, EWZ, FXI, GLD, HYG, IBIT, IEF, IVV, IWM, IWN, IWO, IYR, KBE, KRE, KWEB, LQD, MDY, MOO, NDX, NDXP, OEF, QQQ, RSP, SLV, SMH, SOXL, SOXX, SPY, SVIX, SVXY, TIP, TLT, UNG, UUP, UVIX, UVXY, VIXM, VIXY, VOO, VXX, VXZ, XHB, XLB, XLC, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY, XME, XND, XOP, XRT (source: https://www.nasdaqtrader.com/Trader.aspx?id=optionshours). Index options to 16:15: DJX, MRUT, OEX, RUT, RUTW, SPX, SPXW, VIX, VIXW, XEO, XSP (source: https://help.firstrade.info/en/articles/9264922-options-that-trade-until-4-15-pm-eastern-time-utc-5). Cboe underlying CSV carries per-symbol "Extended-Hours Eligible" flags (source: https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/cone-underlying.csv).
- SPX/XSP/RUT/VIX GTH 20:15-9:25 ET and Curb 16:15-17:00 ET (source: https://www.cboe.com/about/hours/us-options). Early closes 2026: Nov 27, Dec 24 at 13:00 ET (source: https://www.cboe.com/about/hours/us-options); ETF 13:15 half-day close: **UNVERIFIED** from a primary page.
- Cboe filing (Apr 2026) to add single-stock GTH/Curb sessions accepting limit orders only; live status **UNVERIFIED** (source: https://www.federalregister.gov/documents/2026/04/09/2026-06799/self-regulatory-organizations-cboe-exchange-inc-notice-of-filing-of-amendment-no-1-to-a-proposed).

### B4. 0DTE / expiration
- SPY, QQQ, IWM have Mon-Fri expirations (source: https://www.federalregister.gov/documents/2026/01/26/2026-01374/self-regulatory-organizations-cboe-exchange-inc-notice-of-filing-and-immediate-effectiveness-of-a).
- Equity/ETF options are PM-settled off the 16:00 ET close; OCC marks from the 16:00 NBBO (source: https://www.cboe.com/document/tech-spec/document/technical-specifications/equity-options-extended-trading-hours-faq).
- Exercise-by-exception: OCC auto-exercises anything ITM by $0.01 or more absent contrary instructions (source: https://www.optionseducation.org/referencelibrary/faq/options-exercise). FINRA Rule 2360 cut-off 17:30 ET; brokers may set earlier (source: https://www.finra.org/rules-guidance/notices/information-notice-020321). Schwab 17:30 ET (source: https://www.schwab.com/learn/story/options-expiration-definitions-checklist-more); Robinhood 17:00 ET and may force-close unfunded ITM longs in the last 30 minutes (source: https://robinhood.com/us/en/support/articles/expiration-exercise-and-assignment/). Webull cut-off: **UNVERIFIED**.
- After-hours moves can flip moneyness after the close; shorts OTM at 16:00 can still be assigned (source: https://www.schwab.com/learn/story/options-expiration-definitions-checklist-more). Bot rule: flatten 0DTE before 16:00 (16:15 products before 16:15).
- SPX monthly (3rd Friday) is AM-settled off component opening prints, last trade Thursday; SPXW is PM-settled, last trade 16:00 (13:00 half days) (source: https://www.cboe.com/tradable-products/sp-500/spx-options/spx-specifications).

### B5. Stop orders on options
- Exchanges reject stop orders in extended sessions; stops are broker-simulated (source: https://www.cboe.com/document/tech-spec/document/technical-specifications/equity-options-extended-trading-hours-faq).
- Trigger sources: Fidelity buy stop on bid>=stop or trade>=stop, sell stop on ask<=stop or trade<=stop; Day or GTC (180 days) (source: https://www.fidelity.com/trading/faqs-order-types). Robinhood sell stop-limit on ask<=stop or trade; buy stop must be above / sell stop below current price (source: https://robinhood.com/us/en/support/articles/stop-limit-order-options). IBKR default for US options = "double bid/ask", configurable `triggerMethod` (source: https://www.interactivebrokers.com/docs/tws-api/doc/orders/trigger-methods). Schwab thinkorswim STD/MARK/BID/ASK/LAST selectable (source: https://toslc.thinkorswim.com/center/howToTos/thinkManual/Trade/Order-Entry-Tools). E*TRADE "Stop on Quote": sell stop must be >= $0.01 below current bid, buy stop >= $0.01 above ask (source: https://apisb.etrade.com/docs/api/order/api-order-v1.html). Webull: last-price wording, exact source **UNVERIFIED** (source: https://www.webull.com/learn/GtulH5/f0J1g3/Protect-Your-Options-Positions-by-Using-Stop-Orders).
- Why stop-limit: a triggered stop-market has no fill-price floor and fills "far from your expected price" in a gap (source: https://www.webull.com/learn/GtulH5/f0J1g3/Protect-Your-Options-Positions-by-Using-Stop-Orders); set the limit meaningfully below the stop (source: https://robinhood.com/us/en/support/articles/stop-limit-order-options).
- GTC option stops: Webull API sell-side = DAY only (source: https://developer.webull.com/apis/docs/trade-api/options.md); Fidelity GTC allowed (source: https://www.fidelity.com/trading/faqs-order-types); Robinhood GTC stop-market can rest (90 days) (source: https://robinhood.com/us/en/support/articles/stop-market-order-options); Alpaca GTC x Stop = Yes (source: https://docs.alpaca.markets/us/docs/orders-at-alpaca.md); IBKR/Schwab/tastytrade/Tradier: not restricted in docs but explicit confirmation **UNVERIFIED**; E*TRADE error catalog has "GTC orders on stop/stop limits are not permitted" with undocumented scope (source: https://apisb.etrade.com/docs/api/order/api-order-v1.html); Public.com has no GTC at all (DAY/GTD<=90d) (source: https://public.com/api/docs/resources/order-placement/place-order).

### B6. Index vs ETF options
- SPX/XSP/NDX/RUT/VIX: European, cash-settled, no early assignment, $100 multiplier; XSP = 1/10 SPX (source: https://www.cboe.com/tradable-products/sp-500/spx-options/spx-specifications; source: https://www.tradestation.com/insights/2025/05/28/spy-vs-spx-options-explained/).
- Section 1256: 60% long-term / 40% short-term, mark-to-market year-end, Form 6781 (source: https://www.irs.gov/pub/irs-access/f6781_accessible.pdf). SPY/QQQ options are ordinary equity options (source: https://www.tradestation.com/insights/2025/05/28/spy-vs-spx-options-explained/).
- Availability: Webull retail YES (source: https://www.webull.com/trading-investing/index-options) — the brief's assumption that Webull cannot is wrong at the retail level; via OpenAPI **UNVERIFIED**. Robinhood SPX/VIX/XSP/RUT/NDX (source: https://robinhood.com/us/en/support/articles/index-options); IBKR (source: https://www.interactivebrokers.com/en/trading/cboe.php); tastytrade incl. overnight GTH (source: https://www.businesswire.com/news/home/20260810878035/en/tastytrade-Launches-Global-Trading-Hours-Overnight-Index-Options-Trading-Built-for-Active-Traders); Tradier SPX/VIX/XSP (source: https://trade.tradier.com/tbi/); Alpaca paper-only since July 2026 (source: https://alpaca.markets/blog/alpaca-introduces-index-options-paper-trading/); Public.com yes (source: https://public.com/api/docs/additional-info/order-limits).

### B7. Circuit breakers and halts
- MWCB on S&P 500: L1 7% and L2 13% -> 15-min halt if before 15:25 ET; L3 20% -> rest of day; options exchanges halt in coordination (source: https://www.nasdaqtrader.com/trader.aspx?id=CircuitBreaker).
- LULD: Tier 1 >$3 = 5% band, Tier 2 = 10%, doubled in last 25 min; Limit State unresolved 15 s -> 5-min pause (source: https://www.luldplan.com/).
- When the primary market halts a stock, its options halt too; exercise instructions still accepted (source: https://www.optionseducation.org/referencelibrary/faq/options-exercise). Whether resting option orders survive a halt is exchange/broker specific: **UNVERIFIED**; re-query open orders after any halt.

### B8. OPRA data
- OPRA is the options SIP; feed = last-sale reports (trades) + quotations (bid/ask); quotes dominate volume (source: https://www.opraplan.com/faqs). "Real-time" = within 15 minutes of transmission; older = delayed (source: https://www.opraplan.com/faqs).
- Non-Professional = individual, personal non-business use, not a securities professional; fees via vendor ~ $1.25/user/month non-pro vs $31.50 pro (source: https://www.opraplan.com/faqs; source: https://www.marketdata.app/education/options/opra-fees/).
- Quote vs trade: thin 0DTE strikes may not print for minutes while the bid collapses; a bid-watching stop must consume quote (NBBO) data — bars/ticks (trade-based) are not the bid (source: https://www.opraplan.com/faqs). On Webull the only option bid/ask source is the polled snapshot `bid`/`ask` (source: https://developer.webull.com/apis/docs/reference/option-snapshot.md).
- Volume: ~13.6 billion msgs/day projected Jul 2026 (source: https://cdn.opraplan.com/documents/notices/OPRA_Capacity_Projections_Update_0925.pdf).

---

## C) OTHER BROKER APIs

### C1. Charles Schwab Trader API
| Item | Finding |
|---|---|
| Options via API | Yes; assetType EQUITY and OPTION (source: https://archive.org/stream/schwabtraderapi/schwabapi_djvu.txt). Individual app approval takes days (source: https://medium.com/@carstensavage/the-unofficial-guide-to-charles-schwabs-trader-apis-14c1f5bc1d57) |
| Order types | MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP(_LIMIT), multi-leg via `orderLegCollection` (source: https://raw.githubusercontent.com/alexgolec/schwab-py/main/schwab/orders/common.py; https://archive.org/stream/schwabtraderapi/schwabapi_djvu.txt) |
| TIF | DAY, GOOD_TILL_CANCEL, FOK, IOC, END_OF_WEEK/MONTH; session NORMAL/AM/PM/SEAMLESS (same sources); option session support **UNVERIFIED** |
| GTC option stop | No documented restriction; **UNVERIFIED** |
| Trailing stop options | Schema supports; options-specific **UNVERIFIED** |
| Bracket/OCO/OTO | Yes: TRIGGER, OCO, TRIGGER-of-OCO (source: https://archive.org/stream/schwabtraderapi/schwabapi_djvu.txt) |
| Stop trigger | `stopType` STANDARD/BID/ASK/LAST/MARK (source: https://raw.githubusercontent.com/alexgolec/schwab-py/main/schwab/orders/common.py) |
| Streaming option quotes | Yes, Level-One Options WebSocket (source: https://github.com/alexgolec/schwab-py/blob/main/docs/streaming.rst) |
| Historical option bars | No (source: https://raw.githubusercontent.com/alexgolec/schwab-py/main/docs/client.rst) |
| Rate limits | Orders 0-120/min per account configurable; GETs unthrottled (source: https://archive.org/stream/schwabtraderapi/schwabapi_djvu.txt); market data ~120/min, 429-001/429-005 (secondary: https://grokipedia.com/page/Schwab_Trader_API) |
| Sandbox/paper | No paper trading (source: https://mylinedchart.com/resources/articles/schwab-api-for-technical-traders-workflow-fit-checklist); official status **UNVERIFIED** |
| Index options | **UNVERIFIED** officially |
| Python SDK | None official; community `schwab-py` (source: https://schwab-py.readthedocs.io/en/latest/) |
| Gotchas | Access token 30 min; refresh token 7 days then full browser OAuth again; use account hash not number (source: https://archive.org/stream/schwabtraderapi/schwabapi_djvu.txt) |

### C2. Tradier
| Item | Finding |
|---|---|
| Options via API | Yes; `class=option`, `multileg` (4 legs), `combo` (source: https://docs.tradier.com/docs/trading.md) |
| Order types | market, limit, stop, stop_limit; multileg market/debit/credit/even (source: https://docs.tradier.com/reference/brokerage-api-trading-place-order.md) |
| TIF | day, gtc, pre, post (same source) |
| GTC option stop | Not restricted in docs; **UNVERIFIED** |
| Trailing stop | No native type (source: https://docs.tradier.com/reference/brokerage-api-trading-place-order.md) |
| Bracket/OCO/OTO | Yes: oto, oco, otoco (source: https://docs.tradier.com/docs/trading.md) |
| Stop trigger | **UNVERIFIED** |
| Streaming option quotes | Yes, WebSocket `wss://ws.tradier.com/v1/` (source: https://docs.tradier.com/reference/websocket-market-data-streaming.md); not in sandbox (source: https://docs.tradier.com/docs/faq.md) |
| Historical option bars | Daily via `/markets/history` with OCC symbol (source: https://docs.tradier.com/reference/brokerage-api-markets-get-history.md); intraday via timesales **UNVERIFIED** for options |
| Chain/snapshot | `/markets/options/chains` with greeks (source: https://docs.tradier.com/reference/brokerage-api-markets-get-options-chains.md) |
| Rate limits | 120/min standard & market data (60 sandbox); trading 60/min; `X-Ratelimit-*` headers (source: https://docs.tradier.com/docs/rate-limiting) |
| Sandbox | Yes, 15-min delayed, no streaming (source: https://docs.tradier.com/docs/faq.md) |
| Index options | SPX, VIX, XSP; index quotes delayed even in prod (source: https://docs.tradier.com/docs/faq.md) |
| Python SDK | None official (source: https://docs.tradier.com/docs/libraries.md) |
| Gotchas | 200 OK = received, not accepted — poll status (source: https://docs.tradier.com/docs/trading.md) |

### C3. Alpaca
| Item | Finding |
|---|---|
| Options via API | Yes, levels 0-3 (source: https://docs.alpaca.markets/us/docs/options-trading) |
| Order types | market, limit, stop, stop_limit single-leg; mleg (4 legs) market/limit only (source: https://docs.alpaca.markets/us/reference/postorder.md) |
| TIF | day, gtc; no extended hours (source: https://docs.alpaca.markets/us/docs/orders-at-alpaca.md) |
| GTC option stop | Yes (GTC auto-cancel 90 days) (source: https://docs.alpaca.markets/us/docs/orders-at-alpaca.md) |
| Trailing stop | No for options (source: https://docs.alpaca.markets/us/reference/postorder.md) |
| Bracket/OCO/OTO | No for options (simple, mleg only) (same source) |
| Stop trigger | **UNVERIFIED** |
| Streaming option quotes | Yes, msgpack WebSocket; 200 subs Basic (indicative) / 1,000 Algo Trader Plus (OPRA) (source: https://docs.alpaca.markets/us/docs/about-market-data-api.md) |
| Historical option bars | Yes `/v1beta1/options/bars`, 100 symbols/request, since Feb 2024 (source: https://docs.alpaca.markets/us/reference/optionbars.md) |
| Chain/snapshot | Chain snapshots max 1000/page; snapshots 100 symbols (source: https://docs.alpaca.markets/us/reference/optionsnapshots.md) |
| Rate limits | Trading 200/min; data 200/min Basic, 10,000/min ATP (source: https://alpaca.markets/support/usage-limit-api-calls; https://docs.alpaca.markets/us/docs/about-market-data-api.md) |
| Sandbox | Paper with options on by default (source: https://docs.alpaca.markets/us/docs/paper-trading.md) |
| Index options | Paper only (source: https://alpaca.markets/blog/alpaca-introduces-index-options-paper-trading/) |
| Python SDK | `alpaca-py` official (source: https://github.com/alpacahq/alpaca-py) |
| Gotchas | Basic feed is indicative and missing last 15 min; assignments not pushed via websocket (source: https://docs.alpaca.markets/us/docs/options-trading) |

### C4. Interactive Brokers (TWS API / Web API)
| Item | Finding |
|---|---|
| Options via API | Yes both; TWS/Gateway must run (source: https://interactivebrokers.github.io/tws-api/introduction.html); Web API needs funded IBKR Pro account (source: https://www.interactivebrokers.com/campus/ibkr-api-page/webapi-doc/) |
| Order types | Market, Limit, Stop, Stop-Limit, Trailing Stop(-Limit), MIT all list OPT (source: https://interactivebrokers.github.io/tws-api/basic_orders.html) |
| TIF | DAY, GTC, IOC, GTD, OPG, FOK, DTC (source: https://interactivebrokers.github.io/tws-api/classIBApi_1_1Order.html); Web API DAY/IOC/GTC/OPG/PAX (source: https://www.interactivebrokers.com/docs/web-api/api-reference/trading/trading-orders/submit-new-order) |
| GTC option stop | Not restricted; explicit **UNVERIFIED** |
| Trailing stop options | Yes (source: https://interactivebrokers.github.io/tws-api/basic_orders.html) |
| Bracket/OCO | Yes, parentId brackets and OCA groups (source: https://interactivebrokers.github.io/tws-api/bracket_order.html) |
| Stop trigger | Configurable; US options default double bid/ask (source: https://www.interactivebrokers.com/docs/tws-api/doc/orders/trigger-methods) |
| Streaming option quotes | Yes, 100 market data lines default (source: https://www.interactivebrokers.com/docs/tws-api/doc/pacing-limitations/introduction) |
| Historical option bars | Live contracts only, not expired; no EOD for options (source: https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-data-limitations/unavailable-historical-data) |
| Rate limits | TWS 50 msg/s; Web API 10 req/s, `/iserver/orders` 1 per 5 s, 429 + 10-min penalty (source: https://www.interactivebrokers.com/campus/ibkr-api-page/webapi-doc/) |
| Sandbox | Paper account (source: https://www.interactivebrokers.com/docs/tws-api/doc/notes-limitations/limitations/paper-trading) |
| Index options | Yes, SPX suite (source: https://www.interactivebrokers.com/en/trading/cboe.php) |
| Python SDK | `ibapi` from IBKR installer only, not PyPI-endorsed (source: https://www.interactivebrokers.com/docs/tws-api/doc/download-the-tws-api/introduction) |
| Gotchas | Weekly Monday re-login; monotonic order IDs; one brokerage session per username (sources above) |

### C5. tastytrade
| Item | Finding |
|---|---|
| Options via API | Yes, OAuth client required (source: https://developer.tastytrade.com/docs/get-started/) |
| Order types | Limit, Market, Marketable Limit, Stop, Stop Limit, Notional Market; 4 legs (source: https://developer.tastytrade.com/reference/orders/postAccountsAccountNumberOrders/) |
| TIF | Day, GTC, GTD, IOC, Ext variants (same source); option-specific set **UNVERIFIED** |
| GTC option stop | Examples show Stop+GTC; options explicit **UNVERIFIED** (source: https://developer.tastytrade.com/docs/concepts/orders-and-order-types/) |
| Trailing stop | No (no enum value) |
| Bracket/OCO/OTO | Yes: OTOCO, OCO, OTO, PAIRS (same source) |
| Stop trigger | Buy stop off ask/trade, sell off bid/trade at resting exchange (source: https://support.tastytrade.com/support/s/solutions/articles/43000435317 — snippet only, partially UNVERIFIED) |
| Streaming option quotes | Yes, DXLink WebSocket (source: https://developer.tastytrade.com/docs/concepts/streaming/) |
| Historical option bars | Only DXLink Candle events, no REST (source: https://developer.tastytrade.com/llms.txt) |
| Chain/snapshot | `/option-chains/{symbol}`; `market-data/by-type` 100 symbols (source: https://developer.tastytrade.com/docs/concepts/market-data/) |
| Rate limits | Unpublished, 429 without headers (source: https://developer.tastytrade.com/docs/guides/rate-limits-and-backoff/) |
| Sandbox | cert env, resets every 24 h, quotes always 15-min delayed (source: https://developer.tastytrade.com/sandbox/) |
| Index options | SPX/XSP/NDX at brokerage; API order confirmation **UNVERIFIED** |
| Python SDK | Official SDK archived (source: https://raw.githubusercontent.com/tastytrade/tastytrade-sdk-python/master/README.md) |
| Gotchas | 15-min JWTs; mandatory User-Agent; no idempotency (source: https://developer.tastytrade.com/docs/faq/) |

### C6. Robinhood
| Item | Finding |
|---|---|
| Options via API | Only documented REST API is Crypto (source: https://robinhood.com/us/en/newsroom/robinhood-crypto-trading-api/). Official "Agentic Trading" MCP server at `agent.robinhood.com/mcp/trading` places option orders in a dedicated Agentic account (source: https://robinhood.com/us/en/support/articles/agentic-trading-overview/). `robin_stocks` is unofficial, last release May 2025 (source: https://pypi.org/project/robin-stocks/) |
| Order types | market, limit, stop limit, stop market (sell-to-close only) (source: https://robinhood.com/us/en/support/articles/stop-market-order-options) |
| TIF | GTC (90 days) or GFD; no extended hours (source: https://robinhood.com/us/en/support/articles/placing-an-options-trade/) |
| GTC option stop | Yes (source: https://robinhood.com/us/en/support/articles/stop-market-order-options) |
| Trailing / Bracket | No / No (source: https://robinhood.com/us/en/support/articles/order-types/) |
| Stop trigger | Bid/ask or trade (source: https://robinhood.com/us/en/support/articles/stop-limit-order-options/) |
| Streaming | No; MCP request/response (source: https://robinhood.com/us/en/support/articles/trading-with-your-agent/) |
| Historical option bars | MCP `get_option_historicals` (same source) |
| Rate limits / sandbox | **UNVERIFIED** / none found |
| Index options | SPX, VIX, XSP, RUT, NDX in-app (source: https://robinhood.com/us/en/support/articles/index-options/) |
| Gotchas | Stop-market options blocked 9:30-9:45; desktop-only onboarding (sources above) |

### C7. E*TRADE
| Item | Finding |
|---|---|
| Options via API | Yes, OAuth 1.0a, orderType OPTN/SPREADS/etc. (source: https://apisb.etrade.com/docs/api/order/api-order-v1.html) |
| Order types | MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP_CNST/PRCT, NET_DEBIT/CREDIT (same source) |
| TIF | GOOD_UNTIL_CANCEL, GOOD_FOR_DAY, GOOD_TILL_DATE, IOC, FOK (same source) |
| GTC option stop | Conflicting: error 3025 "GTC orders on stop/stop limits are not permitted", scope undocumented — **UNVERIFIED** |
| Trailing stop options | Yes; not allowed if bid <= $0.10 (same source) |
| Bracket/OCO | No via API (same source) |
| Stop trigger | "Stop on Quote": sell stop >= $0.01 below bid (same source) |
| Streaming | None for quotes (source: https://developer.etrade.com/support/frequently-asked-questions) |
| Historical option bars | No (source: https://apisb.etrade.com/docs/api/market/api-quote-v1.html) |
| Rate limits | **UNVERIFIED** |
| Sandbox | Static sample data (source: https://developer.etrade.com/getting-started/developer-guides) |
| Python SDK | None official |
| Gotchas | Token expires midnight ET; preview-then-place within 3 min (sources above) |

### C8. Public.com
| Item | Finding |
|---|---|
| Options via API | Yes since June 2025 (source: https://public.com/api/docs/changelog) |
| Order types | MARKET, LIMIT, STOP, STOP_LIMIT; multi-leg LIMIT only, 2-6 legs (source: https://public.com/api/docs/resources/order-placement/place-order; https://public.com/api/docs/resources/order-placement/place-multileg-order) |
| TIF | DAY, GTD (<=90 days); no GTC (source: https://public.com/api/docs/resources/order-placement/place-order) |
| GTC option stop | No GTC exists; STOP+GTD **UNVERIFIED** |
| Trailing / Bracket | No / No (same source) |
| Stop trigger | **UNVERIFIED** |
| Streaming | No; REST quotes (source: https://public.com/api/docs/resources/market-data/get-quotes) |
| Historical option bars | Yes, bars v2 type OPTION (source: https://public.com/api/docs/resources/market-data/get-bars-v2) |
| Rate limits | 10 req/s global per account (source: https://public.com/api/docs/changelog) |
| Sandbox | None; live only (source: https://public.com/api/docs/resources/order-placement/place-order) |
| Index options | Yes (source: https://public.com/api/docs/additional-info/order-limits) |
| Python SDK | `publicdotcom-py` official (source: https://github.com/PublicDotCom/publicdotcom-py) |

### C9. Moomoo OpenAPI
| Item | Finding |
|---|---|
| Options via API | Yes via OpenD gateway + `unlock_trade` (source: https://openapi.moomoo.com/moomoo-api-doc/en/trade/place-order.html) |
| Order types | Limit, Market, Stop, Stop Limit, MIT, LIT, Trailing Stop(-Limit) for US options (source: https://openapi.moomoo.com/moomoo-api-doc/en/qa/trade.html) |
| TIF | DAY, GTC, GTD (source: https://openapi.moomoo.com/moomoo-api-doc/en/trade/trade.html) |
| GTC option stop | **UNVERIFIED** |
| Trailing stop options | Yes; close-only, RTH only (source: https://www.moomoo.com/us/support/topic4_108) |
| Bracket/OCO | Not in API (**UNVERIFIED**) |
| Streaming | Yes, quota 20/60/200/400 option chains by tier (source: https://openapi.moomoo.com/moomoo-api-doc/en/intro/authority.html) |
| Historical option bars | 1m/5m/15m/60m/1d (source: https://openapi.moomoo.com/moomoo-api-doc/en/quote/request-history-kline.html) |
| Rate limits | place_order 15/30s; snapshots 60/30s, 400 codes (source: https://openapi.moomoo.com/moomoo-api-doc/en/trade/place-order.html; https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-market-snapshot.html) |
| Sandbox | Paper: limit+market only, DAY only — cannot test stops (source: https://openapi.moomoo.com/moomoo-api-doc/en/qa/trade.html) |
| Python SDK | `moomoo-api` official (source: https://pypi.org/project/moomoo-api/) |

### C10. TradeStation WebAPI v3
| Item | Finding |
|---|---|
| Options via API | Yes; key issued by email (source: https://api.tradestation.com/docs/faq) |
| Order types | Limit, StopMarket, Market, StopLimit + TrailingStop advanced option; Legs[] (source: https://api.tradestation.com/docs/specification/) |
| TIF | DAY, GTC, GTD, OPG, CLO, IOC, FOK (GTC max 90 days) (same source) |
| GTC option stop / trailing | **UNVERIFIED** / not restricted |
| Bracket/OCO | Yes: BRK/OCO groups, OSO (source: https://api.tradestation.com/docs/specification/#tag/Order-Execution/operation/PlaceGroupOrder) |
| Stop trigger | Activation triggers STT/SBA/DBA etc. (source: https://api.tradestation.com/docs/specification/#tag/Order-Execution/operation/GetActivationTriggers) |
| Streaming | HTTP chunked streams, 10 concurrent option streams (source: https://api.tradestation.com/docs/fundamentals/rate-limiting/rate-limiting-overview) |
| Rate limits | Option endpoints 90/min; quotes 500/5 min (same source) |
| Sandbox | SIM `sim-api.tradestation.com` (source: https://api.tradestation.com/docs/fundamentals/sim-vs-live) |
| Python SDK | None official (source: https://github.com/tradestation) |

### C11. Tradovate
- Futures and options on futures only; no equity options (source: https://www.tradovate.com/trading-products/). API access needs >$1,000 live balance, CME ILA and paid add-on (source: https://tradovate.zendesk.com/hc/en-us/articles/4403105829523-How-Do-I-Get-Access-to-the-Tradovate-API). Order types incl. TrailingStop, OCO/OSO; penalty tickets `p-ticket`/`p-time` on rate abuse (source: https://api.tradovate.com/). Not a porting target for this bot.

---

## D) COMMON PITFALLS
- Wrong tick: rounding every option to $0.05/$0.10 is legal but overpays on penny classes (SPY/QQQ/IWM are $0.01 everywhere); off-tick prices are rejected (Webull `OPTION_PRICE_STEP_LT`, team-observed). Use `ppind` from Get Option Contracts (sources: https://www.cboe.com/notices/content/?id=57916; https://developer.webull.com/apis/docs/reference/option-contract-list.md).
- DAY stops die at the close: Webull option SELL orders are DAY only, so every protective stop is gone overnight and must be re-armed at 9:30 (source: https://developer.webull.com/apis/docs/trade-api/options.md).
- Stop above market rejected: brokers validate sell stops against the LIVE bid/last, not your fill; right after buying at the ask the bid may already be under a fill-based stop (E*TRADE codes 1509/1510; Webull `STOP_PRICE_MUST_BE_LESS_THAN_MARKET_PRICE` team-observed) (source: https://apisb.etrade.com/docs/api/order/api-order-v1.html).
- No MARKET orders for options on Webull: a "market" exit must be an aggressive LIMIT (source: https://developer.webull.com/apis/docs/trade-api/faq.md).
- OTO/OCO/OTOCO do not exist for options on Webull despite the feature matrix; only MASTER + STOP_PROFIT/STOP_LOSS on SINGLE strategies (source: https://developer.webull.com/apis/docs/reference/common-order-place.md).
- Sandbox lacks options: Webull sandbox is 15-min delayed for subscribed data and rejected every option order in this team's testing; Tradier/tastytrade sandboxes are delayed; Moomoo paper cannot test stops; Public.com has no sandbox (sources: A8, C2, C5, C8, C9).
- Treating trade bars/ticks as the bid: bars are trades; thin strikes go minutes without a print while the bid collapses. Poll snapshot `bid`/`ask` for stops (source: https://developer.webull.com/apis/docs/reference/option-snapshot.md).
- Webull has no option streaming; snapshot polling is capped at 60/60s with 20 symbols per call = 1,200 contract-quotes/min per app key, shared across all accounts/processes (source: https://developer.webull.com/apis/docs/rate-limits.md).
- Rate limit is per app key, not per account: multi-account fan-out multiplies calls against one quota; Open Orders/Order Detail/Positions are 2/2s (source: https://developer.webull.com/apis/docs/rate-limits.md).
- 429 and 417 are different: 429 = throttle (retry with backoff); 417 = business rejection (do NOT retry blindly) (source: https://developer.webull.com/apis/docs/rate-limits.md; https://developer.webull.com/apis/docs/reference/common-order-place.md).
- Expired-contract lookups: IBKR returns no history for expired options; Webull contract list defaults to `status=LISTING`; store OCC symbols at entry time (sources: https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-data-limitations/unavailable-historical-data; https://developer.webull.com/apis/docs/reference/option-contract-list.md).
- PM vs AM settlement: SPX monthlies settle AM off Thursday's close of trading; SPXW/equity options settle PM at 16:00 (source: https://www.cboe.com/tradable-products/sp-500/spx-options/spx-specifications).
- 16:15 products: SPY/QQQ/IWM/DIA and index options trade 15 minutes past the stock close; a 16:00 "close-out" job leaves them open (source: https://www.nasdaqtrader.com/Trader.aspx?id=optionshours).
- 0DTE auto-exercise at $0.01 ITM: an un-flattened long turns into stock (or a margin call) over the weekend (source: https://www.optionseducation.org/referencelibrary/faq/options-exercise).
- MQTT subscriptions vanish on reconnect; same `session_id` twice kicks the first connection; max 5 connections per key (source: https://developer.webull.com/apis/docs/market-data-api/data-streaming-api.md).
- gRPC events: handle `SubscribeExpired`/`NumOfConnExceed` and reconcile with Order Detail polling; do not treat the stream as the only source of fills (source: https://developer.webull.com/apis/docs/reference/custom/subscribe-trade-events.md).
- Replace uses the ORIGINAL `client_order_id`; option replaces need `legs[].id`; never send parallel replaces for one order (Public.com warns ordering is not guaranteed) (sources: https://developer.webull.com/apis/docs/reference/common-order-replace.md; https://public.com/api/docs/resources/order-placement/place-order).
- `INVALID_TOKEN` on Webull is usually a signature/serialization bug, not an expired token (source: https://developer.webull.com/apis/docs/trade-api/faq.md).
- SDK family mixing: old `webullsdkcore` pins (`grpcio==1.51.1`, `protobuf==4.21.12`, `paho-mqtt==1.6.1`) conflict with the new `webull` package on Python 3.12+; keep one family per venv (source: https://pypi.org/pypi/webull-openapi-python-sdk/json; https://pypi.org/pypi/webull-python-sdk-quotes-core/json).
- Assuming Webull cannot trade index options: retail Webull lists SPX/SPXW/XSP/NDX/VIX; API order support is the open question (source: https://www.webull.com/trading-investing/index-options).

---

## Sources
- https://developer.webull.com/apis/docs/rate-limits.md
- https://developer.webull.com/apis/docs/trade-api/options.md
- https://developer.webull.com/apis/docs/trade-api/faq.md
- https://developer.webull.com/apis/docs/trade-api/overview.md
- https://developer.webull.com/apis/docs/trade-api/stock.md
- https://developer.webull.com/apis/docs/reference/common-order-place.md
- https://developer.webull.com/apis/docs/reference/common-order-replace.md
- https://developer.webull.com/apis/docs/reference/option-snapshot.md
- https://developer.webull.com/apis/docs/reference/option-historical-bars.md
- https://developer.webull.com/apis/docs/reference/option-tick.md
- https://developer.webull.com/apis/docs/reference/option-contract-list.md
- https://developer.webull.com/apis/docs/reference/subscribe.md
- https://developer.webull.com/apis/docs/reference/custom/subscribe-trade-events.md
- https://developer.webull.com/apis/docs/market-data-api/overview.md
- https://developer.webull.com/apis/docs/market-data-api/data-streaming-api.md
- https://developer.webull.com/apis/docs/market-data-api/faq.md
- https://developer.webull.com/apis/docs/market-data-api/subscribe-quotes.md
- https://developer.webull.com/apis/docs/sdk.md
- https://developer.webull.com/apis/docs/changelog.md
- https://developer.webull.com/apis/docs/authentication/IndividualApplicationAPI.md
- https://developer.webull.com/apis/llms.txt
- https://raw.githubusercontent.com/webull-inc/openapi-python-sdk/main/README.md
- https://pypi.org/pypi/webull-openapi-python-sdk/json
- https://pypi.org/pypi/webull-python-sdk-core/json
- https://pypi.org/pypi/webull-python-sdk-quotes-core/json
- https://pypi.org/pypi/webull-python-sdk-trade-events-core/json
- https://pypi.org/pypi/webull/json
- https://www.webull.com/learn/GtulH5/f0J1g3/Protect-Your-Options-Positions-by-Using-Stop-Orders
- https://www.webull.com/learn/rgpBdy/DbpPvC/GTC-for-Options-Trading
- https://www.webull.com/trading-investing/index-options
- https://www.fidelity.com/research/options/osi.shtml
- https://en.wikipedia.org/wiki/Option_symbol
- https://www.cboe.com/notices/content/?id=57916
- https://www.sec.gov/files/rules/sro/cboe/2025/34-104157.pdf
- https://help.firstrade.info/en/articles/9264852-in-what-price-increments-are-equity-and-index-options-quoted
- https://help.firstrade.info/en/articles/9264922-options-that-trade-until-4-15-pm-eastern-time-utc-5
- https://www.nasdaqtrader.com/Trader.aspx?id=optionshours
- https://www.cboe.com/about/hours/us-options
- https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/cone-underlying.csv
- https://www.cboe.com/document/tech-spec/document/technical-specifications/equity-options-extended-trading-hours-faq
- https://www.federalregister.gov/documents/2026/04/09/2026-06799/self-regulatory-organizations-cboe-exchange-inc-notice-of-filing-of-amendment-no-1-to-a-proposed
- https://www.federalregister.gov/documents/2026/01/26/2026-01374/self-regulatory-organizations-cboe-exchange-inc-notice-of-filing-and-immediate-effectiveness-of-a
- https://www.cboe.com/tradable-products/sp-500/spx-options/spx-specifications
- https://www.optionseducation.org/referencelibrary/faq/options-exercise
- https://www.finra.org/rules-guidance/notices/information-notice-020321
- https://www.schwab.com/learn/story/options-expiration-definitions-checklist-more
- https://robinhood.com/us/en/support/articles/expiration-exercise-and-assignment/
- https://robinhood.com/us/en/support/articles/stop-limit-order-options
- https://robinhood.com/us/en/support/articles/stop-market-order-options
- https://robinhood.com/us/en/support/articles/index-options
- https://robinhood.com/us/en/support/articles/order-types/
- https://robinhood.com/us/en/support/articles/placing-an-options-trade/
- https://robinhood.com/us/en/support/articles/agentic-trading-overview/
- https://robinhood.com/us/en/support/articles/trading-with-your-agent/
- https://robinhood.com/us/en/newsroom/robinhood-crypto-trading-api/
- https://pypi.org/project/robin-stocks/
- https://www.fidelity.com/trading/faqs-order-types
- https://www.interactivebrokers.com/docs/tws-api/doc/orders/trigger-methods
- https://www.interactivebrokers.com/en/trading/cboe.php
- https://toslc.thinkorswim.com/center/howToTos/thinkManual/Trade/Order-Entry-Tools
- https://support.tastytrade.com/support/s/solutions/articles/43000435317
- https://www.businesswire.com/news/home/20260810878035/en/tastytrade-Launches-Global-Trading-Hours-Overnight-Index-Options-Trading-Built-for-Active-Traders
- https://trade.tradier.com/tbi/
- https://www.tradestation.com/insights/2025/05/28/spy-vs-spx-options-explained/
- https://alpaca.markets/blog/alpaca-introduces-index-options-paper-trading/
- https://www.irs.gov/pub/irs-access/f6781_accessible.pdf
- https://www.nasdaqtrader.com/trader.aspx?id=CircuitBreaker
- https://www.luldplan.com/
- https://www.opraplan.com/faqs
- https://cdn.opraplan.com/documents/notices/OPRA_Capacity_Projections_Update_0925.pdf
- https://www.marketdata.app/education/options/opra-fees/
- https://archive.org/stream/schwabtraderapi/schwabapi_djvu.txt
- https://medium.com/@carstensavage/the-unofficial-guide-to-charles-schwabs-trader-apis-14c1f5bc1d57
- https://raw.githubusercontent.com/alexgolec/schwab-py/main/schwab/orders/common.py
- https://raw.githubusercontent.com/alexgolec/schwab-py/main/docs/client.rst
- https://github.com/alexgolec/schwab-py/blob/main/docs/streaming.rst
- https://schwab-py.readthedocs.io/en/latest/
- https://mylinedchart.com/resources/articles/schwab-api-for-technical-traders-workflow-fit-checklist
- https://grokipedia.com/page/Schwab_Trader_API
- https://docs.tradier.com/docs/rate-limiting
- https://docs.tradier.com/docs/trading.md
- https://docs.tradier.com/docs/faq.md
- https://docs.tradier.com/docs/libraries.md
- https://docs.tradier.com/reference/brokerage-api-trading-place-order.md
- https://docs.tradier.com/reference/websocket-market-data-streaming.md
- https://docs.tradier.com/reference/brokerage-api-markets-get-history.md
- https://docs.tradier.com/reference/brokerage-api-markets-get-options-chains.md
- https://docs.alpaca.markets/us/docs/options-trading
- https://docs.alpaca.markets/us/reference/postorder.md
- https://docs.alpaca.markets/us/docs/orders-at-alpaca.md
- https://docs.alpaca.markets/us/docs/about-market-data-api.md
- https://docs.alpaca.markets/us/docs/paper-trading.md
- https://docs.alpaca.markets/us/reference/optionbars.md
- https://docs.alpaca.markets/us/reference/optionsnapshots.md
- https://docs.alpaca.markets/reference/get-option-contract-symbol_or_id
- https://alpaca.markets/support/usage-limit-api-calls
- https://github.com/alpacahq/alpaca-py
- https://interactivebrokers.github.io/tws-api/introduction.html
- https://interactivebrokers.github.io/tws-api/basic_orders.html
- https://interactivebrokers.github.io/tws-api/bracket_order.html
- https://interactivebrokers.github.io/tws-api/classIBApi_1_1Order.html
- https://www.interactivebrokers.com/docs/tws-api/doc/pacing-limitations/introduction
- https://www.interactivebrokers.com/docs/tws-api/doc/notes-limitations/limitations/paper-trading
- https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-data-limitations/unavailable-historical-data
- https://www.interactivebrokers.com/docs/tws-api/doc/download-the-tws-api/introduction
- https://www.interactivebrokers.com/campus/ibkr-api-page/webapi-doc/
- https://www.interactivebrokers.com/docs/web-api/api-reference/trading/trading-orders/submit-new-order
- https://developer.tastytrade.com/docs/get-started/
- https://developer.tastytrade.com/reference/orders/postAccountsAccountNumberOrders/
- https://developer.tastytrade.com/docs/concepts/orders-and-order-types/
- https://developer.tastytrade.com/docs/concepts/streaming/
- https://developer.tastytrade.com/docs/concepts/market-data/
- https://developer.tastytrade.com/docs/guides/rate-limits-and-backoff/
- https://developer.tastytrade.com/sandbox/
- https://developer.tastytrade.com/docs/faq/
- https://developer.tastytrade.com/llms.txt
- https://raw.githubusercontent.com/tastytrade/tastytrade-sdk-python/master/README.md
- https://apisb.etrade.com/docs/api/order/api-order-v1.html
- https://apisb.etrade.com/docs/api/market/api-quote-v1.html
- https://developer.etrade.com/support/frequently-asked-questions
- https://developer.etrade.com/getting-started/developer-guides
- https://public.com/api/docs/changelog
- https://public.com/api/docs/resources/order-placement/place-order
- https://public.com/api/docs/resources/order-placement/place-multileg-order
- https://public.com/api/docs/resources/market-data/get-quotes
- https://public.com/api/docs/resources/market-data/get-bars-v2
- https://public.com/api/docs/additional-info/order-limits
- https://github.com/PublicDotCom/publicdotcom-py
- https://openapi.moomoo.com/moomoo-api-doc/en/trade/place-order.html
- https://openapi.moomoo.com/moomoo-api-doc/en/trade/trade.html
- https://openapi.moomoo.com/moomoo-api-doc/en/qa/trade.html
- https://openapi.moomoo.com/moomoo-api-doc/en/intro/authority.html
- https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-market-snapshot.html
- https://openapi.moomoo.com/moomoo-api-doc/en/quote/request-history-kline.html
- https://www.moomoo.com/us/support/topic4_108
- https://pypi.org/project/moomoo-api/
- https://api.tradestation.com/docs/specification/
- https://api.tradestation.com/docs/faq
- https://api.tradestation.com/docs/fundamentals/rate-limiting/rate-limiting-overview
- https://api.tradestation.com/docs/fundamentals/sim-vs-live
- https://github.com/tradestation
- https://api.tradovate.com/
- https://www.tradovate.com/trading-products/
- https://tradovate.zendesk.com/hc/en-us/articles/4403105829523-How-Do-I-Get-Access-to-the-Tradovate-API
- Team files (non-public observations): `C:\Users\Hulk\Desktop\discord-sniper\webull_options.py` (lines 193, 1045, 1574), `C:\Users\Hulk\Desktop\discord-sniper\HANDOFF.md` (line 321)
