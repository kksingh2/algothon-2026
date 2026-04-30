# Imperial Algothon 2026 - London Markets Bot

A trading bot built for the Imperial College **Algothon 2026** competition
(February to March 2026), run on the CMI Exchange. The bot quotes a
two-sided market across eight products and runs an ETF-vs-components
arbitrage on top.

> **Note on timing:** the competition ran in February and March 2026.
> I'm uploading this repository now (April 2026) to keep a clean record
> of the work for future reference.

## What the products are

The exchange listed eight products driven by **real-world London data
feeds**, which made the problem more interesting than a pure synthetic
order-book simulation:

| Product      | Underlying                                            |
| ------------ | ----------------------------------------------------- |
| `TIDE_SPOT`  | Thames tidal level at a fixed settlement time         |
| `TIDE_SWING` | Sum of penalty payouts on Thames level changes        |
| `WX_SPOT`    | London temperature times humidity (Sun 12:00)         |
| `WX_SUM`     | Aggregate weather index over the forecast window      |
| `LHR_COUNT`  | Total Heathrow arrivals + departures over 24h         |
| `LHR_INDEX`  | Imbalance index between arrivals and departures       |
| `LON_ETF`    | Basket: `TIDE_SPOT + WX_SPOT + LHR_COUNT`             |
| `LON_FLY`    | Piecewise-linear options structure on `LON_ETF`       |

## Strategy

The bot runs three things in a tight loop:

1. **Fair-value pricing.** For each product, compute a theoretical
   price (`theo`) from the live data feeds using the published
   settlement formulas. Where data is unavailable, fall back to the
   market mid (excluding the bot's own resting volume).

2. **Two-sided market making.** Quote a bid and ask around `theo` with:
   - a width set to ~1.5% of `theo` (with a sensible floor)
   - an **inventory lean** that biases quotes against the current
     position so it naturally flattens
   - dynamic order sizing that shrinks as the position approaches the
     90-unit risk limit

3. **ETF arbitrage.** Every cycle, compare the live `LON_ETF` book to
   the sum of best bids/asks across its three components:
   - if the ETF is rich, sell the ETF and buy the basket
   - if the ETF is cheap, buy the ETF and sell the basket
   - both legs are submitted together in a single batch to minimise
     the time the position spends unhedged (leg risk is reduced, not
     eliminated, since fills are not guaranteed)

## Engineering notes

A few things in the code were driven by practical constraints rather
than by elegance:

- **Caching with TTLs.** The Heathrow flights API is capped at roughly
  150 calls per month, so every external fetch goes through a TTL cache
  (`cached_thames`, `cached_weather`, `cached_flights`). The flight cache
  uses a 10-minute TTL; the others use 60 seconds.
- **Own-volume filtering.** Best bid/ask helpers subtract the bot's own
  resting volume so it doesn't trade against itself or compute fair
  values from its own quotes.
- **Cancel-and-requote loop.** Every cycle cancels open orders and
  re-sends a fresh set. This keeps the logic simple and avoids stale
  quotes after position changes; the cost is more API calls.
- **`LON_FLY` is held, not quoted.** Once the position was profitable
  on a mark-to-market basis, the bot deliberately stops quoting it and
  lets it settle, rather than churning the position and giving back
  edge through the spread.

## Files

- [`finalbot.py`](finalbot.py) - the full bot in one file: cache layer,
  fair-value model, market making logic, ETF arbitrage, and the main
  trading loop.
- [`requirements.txt`](requirements.txt) - Python dependencies.

## Dependencies not included

The bot relies on three pieces of code that came from the competition
harness and are intentionally not vendored into this repository:

- `bot_template` - exposes `BaseBot`, `OrderRequest`, `Trade`, `Side`,
  etc. Provided by the organisers.
- `get_thames`, `get_weather`, `fetch_flights` - helpers that wrap the
  Thames, weather, and Heathrow APIs. They were defined in the team's
  notebook setup cells against the competition's API keys.

These imports will be unresolved if you clone this repository on its
own; the file is published here as a record of the strategy, not as a
runnable artefact. Anything you'd want to drop into a new exchange
shim is in [`finalbot.py`](finalbot.py).

## Running it

```python
from finalbot import FinalBot

EXCHANGE_URL = "http://<exchange-host>"
USERNAME     = "<team-username>"
PASSWORD     = "<team-password>"

bot = FinalBot(EXCHANGE_URL, USERNAME, PASSWORD)
bot.run_session()
```

`Ctrl+C` stops the bot cleanly: it cancels open orders, closes the
session, and exits.

## What I'd do next

If I revisited this, the highest-value changes would be:

- Replace the cancel-and-requote loop with a proper diff-based
  order management layer to preserve queue position.
- Add a small Kalman-style filter on the tide and weather feeds so
  `theo` reacts smoothly to noisy readings instead of jumping with the
  latest data point.
- Hedge `LON_FLY` dynamically against `LON_ETF` rather than holding a
  static position, so the strategy is robust to a wider range of
  settlement levels.
