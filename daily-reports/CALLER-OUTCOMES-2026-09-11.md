# Caller outcome evidence — 2026-09-11

Caller claims are separate from broker results and ratchet simulations. Partial trims remain partial; percentages imply a price only when the caller's entry is known.

| Entry | Event | Contract | Entry | Caller event | Exit/claim | Calculated | Evidence |
|---|---|---|---:|---|---:|---:|---|
| 09:42:00 | 09:52:44 | NVDA 220C 9/16 @ 3.06 | $3.06 | partial trim | +12.0% | implied $3.43 | caller-stated |
| 09:50:39 | 09:53:40 | HPE 62C 0DTE | — | partial trim | +70.0% | unavailable | caller-stated |
| 09:42:00 | 09:53:54 | NVDA 220C 9/16 @ 3.06 | $3.06 | partial trim | +16.0% | implied $3.55 | caller-stated |
| 09:42:00 | 09:54:21 | NVDA 220C 9/16 @ 3.06 | $3.06 | partial trim | +18.0% | implied $3.61 | caller-stated |
| 09:42:00 | 09:55:02 | NVDA 220C 9/16 @ 3.06 | $3.06 | partial trim | +25.0% | implied $3.83 | caller-stated |
| 09:42:00 | 09:55:29 | DELL 560C @ 1.05 | $1.05 | partial trim | +185.0% | implied $2.99 | caller-stated |
| 09:42:00 | 09:56:17 | NVDA 220C 9/16 @ 3.06 | $3.06 | partial trim | +32.0% | implied $4.04 | caller-stated |
| 09:50:39 | 09:59:45 | HPE 62C 0DTE | — | partial trim | +92.0% | unavailable | caller-stated |
| 09:42:00 | 10:00:11 | NVDA 220C 9/16 @ 3.06 | $3.06 | partial trim | +35.0% | implied $4.13 | caller-stated |
| 10:00:14 | 10:04:40 | MU 990C 0DTE @ 2.86 | $2.86 | partial trim | $2.40 | -16.1% | caller-stated |
| 09:42:00 | 10:05:11 | NVDA 220C 9/16 @ 3.06 | $3.06 | partial trim | +50.0% | implied $4.59 | caller-stated |
| 10:01:47 | 10:06:49 | NVDA 220C @ 2.15 | $2.15 | full exit | price unavailable | unavailable | caller exit; price unavailable |
| 10:12:27 | 10:14:49 | TSLA 360P 9/16 @ 5.15 | $5.15 | partial trim | +8.0% | implied $5.56 | caller-stated |
| 10:12:27 | 10:16:22 | TSLA 360P 9/16 @ 5.15 | $5.15 | partial trim | +11.0% | implied $5.72 | caller-stated |
| 10:12:27 | 10:17:18 | TSLA 360P 9/16 @ 5.15 | $5.15 | partial trim | +18.0% | implied $6.08 | caller-stated |
| 10:12:27 | 10:25:31 | TSLA 360P 9/16 @ 5.15 | $5.15 | partial trim | +20.0% | implied $6.18 | caller-stated |
| 10:25:31 | 10:27:37 | TSLA 362.5P @ 1.79 | $1.79 | full exit | $1.24 | -30.7% | market bid at caller exit |
| 10:23:13 | 10:27:43 | AAPL 335C 9/11 @ 0.65 | $0.65 | partial trim | $1.05 | +61.5% | caller-stated |
| 10:12:27 | 10:29:45 | TSLA 360P 9/16 @ 5.15 | $5.15 | full exit | price unavailable | unavailable | caller exit; price unavailable |
| 09:42:00 | 10:35:33 | NVDA 220C 9/16 @ 3.06 | $3.06 | full exit | price unavailable | unavailable | caller exit; price unavailable |
| 10:37:42 | 10:40:35 | NVDA 220C @ 0.97 | $0.97 | full exit | $0.98 | +1.0% | market bid at caller exit |
| 10:39:56 | 10:49:02 | AMZN 255C 9/14 @ 2.05 | $2.05 | full exit | price unavailable | unavailable | caller exit; price unavailable |
| 10:50:04 | 11:03:21 | HOOD 118C 9/18 @ 2.50 | $2.50 | partial trim | +10.0% | implied $2.75 | caller-stated |
| 10:54:00 | 11:12:46 | AAPL 335C 0DTE @ 1.46 | $1.46 | partial trim | +22.0% | implied $1.78 | caller-stated |
| 11:13:20 | 11:13:36 | MU 980C 0DTE @ 3.00 | $3.00 | partial trim | +40.0% | implied $4.20 | caller-stated |
| 10:35:00 | 11:28:10 | SPX 7700C @ 1.05 | $1.05 | partial trim | $500/contract | unavailable | caller-stated |
| 12:01:49 | 12:31:05 | HOOD 118C | — | full exit | -6.0% | unavailable | caller-stated |
| 15:40:12 | 15:46:18 | QQQ 716C 9/11 @ 0.15 | $0.15 | partial trim | $0.24 | +60.0% | caller-stated |
| 15:22:16 | 15:59:59 | IBM 250C 9/18 @ 1.70 | $1.70 | partial trim | $2.20 | +29.4% | caller-stated |

- Claim events paired: **29**.
- Full exits with calculable results: **3**.
- Quantity-weighted caller P&L stays unavailable when trim size or the final runner exit is missing.
