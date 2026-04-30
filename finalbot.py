"""
Imperial Algothon 2026 - FinalBot v2
====================================

Market-making and ETF-component arbitrage bot for the CMI Exchange,
written for the Imperial College Algothon competition (Feb/Mar 2026).

The bot trades 8 products driven by real-world London data:

    Thames tidal levels   : TIDE_SPOT, TIDE_SWING
    London weather        : WX_SPOT,   WX_SUM
    Heathrow flights      : LHR_COUNT, LHR_INDEX
    Derived               : LON_ETF (basket of TIDE_SPOT + WX_SPOT + LHR_COUNT)
                            LON_FLY (options structure on LON_ETF)

Strategy
--------
1. Cache every external API call behind a TTL (the flight API only
   permits ~150 requests per month, so this is non-negotiable).
2. Compute a data-driven fair value (theo) for each product using the
   competition settlement formulas.
3. Quote a two-sided market around theo with an inventory lean that
   pushes prices to flatten any built-up position.
4. Run an ETF-vs-components arbitrage on every cycle, taking liquidity
   when the basket trades through fair value by more than 20 ticks.

Usage
-----
    my_bot = FinalBot(EXCHANGE_URL, USERNAME, PASSWORD)
    my_bot.run_session()
"""

import math
import time

import numpy as np

from bot_template import (
    BaseBot,
    OrderRequest,
    Trade,
    Side,
)


# =================================================================
# Caching layer
# =================================================================
# External APIs are rate limited. Every fetch goes through one of
# these wrappers, which return a cached copy if the most recent call
# is still within its TTL window.

_cache = {
    "tide": None,    "tide_ts": 0,
    "wx": None,      "wx_ts": 0,
    "flights": None, "flights_ts": 0,
}


def cached_thames(ttl=60):
    """Return Thames tidal data, refreshed at most every `ttl` seconds."""
    if time.time() - _cache["tide_ts"] < ttl and _cache["tide"] is not None:
        return _cache["tide"]
    try:
        df = get_thames(limit=200)
        _cache["tide"], _cache["tide_ts"] = df, time.time()
        return df
    except Exception:
        return _cache["tide"]


def cached_weather(ttl=60):
    """Return London weather data, refreshed at most every `ttl` seconds."""
    if time.time() - _cache["wx_ts"] < ttl and _cache["wx"] is not None:
        return _cache["wx"]
    try:
        df = get_weather()
        _cache["wx"], _cache["wx_ts"] = df, time.time()
        return df
    except Exception:
        return _cache["wx"]


def cached_flights(ttl=600):
    """Return Heathrow flight data with a 10-minute TTL to preserve API quota."""
    if time.time() - _cache["flights_ts"] < ttl and _cache["flights"] is not None:
        return _cache["flights"]
    try:
        data = fetch_flights(offset_minutes=-720, duration_minutes=720)
        _cache["flights"], _cache["flights_ts"] = data, time.time()
        return data
    except Exception:
        return _cache["flights"]


# =================================================================
# Helpers
# =================================================================
def _bba(bot, sym):
    """Best bid and best ask, excluding the bot's own resting volume."""
    ob = bot.get_orderbook(sym)
    bids = [o.price for o in ob.buy_orders if o.volume - o.own_volume > 0]
    asks = [o.price for o in ob.sell_orders if o.volume - o.own_volume > 0]
    return (max(bids) if bids else None,
            min(asks) if asks else None)


# =================================================================
# FinalBot
# =================================================================
class FinalBot(BaseBot):
    """Two-sided market maker with ETF arbitrage overlay."""

    SKIP = {"LON_FLY"}                   # held for settlement, do not requote
    QUOTE_PRODUCTS = {
        "TIDE_SPOT", "TIDE_SWING",
        "WX_SPOT",   "WX_SUM",
        "LHR_COUNT", "LHR_INDEX",
    }

    # Class-level defaults so attributes exist even if __init__ is bypassed
    max_pos = 90
    cycle = 0
    _last_etf_arb = 0

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.max_pos = 90
        self.cycle = 0
        self._last_etf_arb = 0

    # SSE callbacks --------------------------------------------------
    def on_orderbook(self, ob):
        pass

    def on_trades(self, t: Trade):
        side = "BOT" if t.buyer == self.username else "SLD"
        print(f"  {side} {t.volume}x {t.product} @ {t.price}")

    # Theo pricing ---------------------------------------------------
    def get_theo(self, symbol, info):
        """Fair value from the competition settlement formulas."""
        try:
            if symbol == "TIDE_SPOT":
                df = cached_thames()
                if df is not None and not df.empty:
                    v = df["level"].values
                    recent = v[-5:] if len(v) >= 5 else v
                    return abs(np.mean(recent)) * 1000

            if symbol == "WX_SPOT":
                df = cached_weather()
                if df is not None and not df.empty:
                    sun = df[df["time"].dt.strftime("%Y-%m-%d %H") == "2026-03-01 12"]
                    if not sun.empty:
                        r = sun.iloc[0]
                        return round((r["temperature"] * 9 / 5) + 32) * r["humidity"]
                    r = df.iloc[-1]
                    return round((r["temperature"] * 9 / 5) + 32) * r["humidity"]

            if symbol == "LHR_COUNT":
                data = cached_flights()
                if data:
                    arr = len(data.get("arrivals", []))
                    dep = len(data.get("departures", []))
                    # API returns a 12 hour window; scale to a 24 hour estimate
                    return int((arr + dep) * 1.35)

            if symbol == "LON_ETF":
                m1 = self.get_theo("TIDE_SPOT", info)
                m3 = self.get_theo("WX_SPOT", info)
                m5 = self.get_theo("LHR_COUNT", info)
                if m1 and m3 and m5:
                    return m1 + m3 + m5

            if symbol == "LON_FLY":
                e = self.get_theo("LON_ETF", info)
                if e:
                    return (
                        2 * max(0, 6200 - e)
                        + max(0, e - 6200)
                        - 2 * max(0, e - 6600)
                        + 3 * max(0, e - 7000)
                    )

            if symbol == "TIDE_SWING":
                df = cached_thames()
                if df is not None and len(df) > 1:
                    v = df["level"].values
                    total = sum(
                        max(0, 20 - abs(v[i] - v[i - 1]) * 100)
                        + max(0, abs(v[i] - v[i - 1]) * 100 - 25)
                        for i in range(1, len(v))
                    )
                    n = len(v) - 1
                    return total / n * 96 if n > 0 else 500

            if symbol == "WX_SUM":
                df = cached_weather()
                if df is not None and not df.empty:
                    return sum(
                        ((r["temperature"] * 9 / 5) + 32) * r["humidity"] / 100
                        for _, r in df.iterrows()
                    )

            if symbol == "LHR_INDEX":
                data = cached_flights()
                if data:
                    a = len(data.get("arrivals", []))
                    d = len(data.get("departures", []))
                    if a + d > 0:
                        return abs(a - d) / (a + d) * 100 * 48
                    return 60
        except Exception as e:
            print(f"  [THEO] {symbol}: {e}")

        # Fallback: market mid (excluding own quotes), else starting price
        ob = self.get_orderbook(symbol)
        b = [o.price for o in ob.buy_orders if o.volume - o.own_volume > 0]
        a = [o.price for o in ob.sell_orders if o.volume - o.own_volume > 0]
        return (max(b) + min(a)) / 2 if b and a else info.startingPrice

    # ETF arbitrage --------------------------------------------------
    def run_etf_arb(self, pos):
        """
        Cross-product arbitrage between LON_ETF and its components.

        If the ETF trades cheap to the basket of components, we buy ETF
        and sell components. If it trades rich, we do the reverse. Both
        legs are sent simultaneously so the position is always hedged.
        """
        try:
            tb, ta = _bba(self, "TIDE_SPOT")
            wb, wa = _bba(self, "WX_SPOT")
            lb, la = _bba(self, "LHR_COUNT")
            eb, ea = _bba(self, "LON_ETF")
            if None in [tb, ta, wb, wa, lb, la, eb, ea]:
                return

            comp_ask = ta + wa + la   # cost to buy the full basket
            comp_bid = tb + wb + lb   # proceeds from selling the full basket
            etf_pos = pos.get("LON_ETF", 0)
            orders = []

            edge_sell = eb - comp_ask
            if edge_sell > 20 and etf_pos > -self.max_pos:
                sz = min(3, self.max_pos + etf_pos)
                if sz > 0:
                    print(f"  ARB SELL ETF: eb={eb} > comp_ask={comp_ask} edge={edge_sell}")
                    orders.append(OrderRequest("LON_ETF",   eb, Side.SELL, sz))
                    orders.append(OrderRequest("TIDE_SPOT", ta, Side.BUY,  sz))
                    orders.append(OrderRequest("WX_SPOT",   wa, Side.BUY,  sz))
                    orders.append(OrderRequest("LHR_COUNT", la, Side.BUY,  sz))

            edge_buy = comp_bid - ea
            if edge_buy > 20 and etf_pos < self.max_pos:
                sz = min(3, self.max_pos - etf_pos)
                if sz > 0:
                    print(f"  ARB BUY ETF: ea={ea} < comp_bid={comp_bid} edge={edge_buy}")
                    orders.append(OrderRequest("LON_ETF",   ea, Side.BUY,  sz))
                    orders.append(OrderRequest("TIDE_SPOT", tb, Side.SELL, sz))
                    orders.append(OrderRequest("WX_SPOT",   wb, Side.SELL, sz))
                    orders.append(OrderRequest("LHR_COUNT", lb, Side.SELL, sz))

            if orders:
                self.send_orders(orders)
        except Exception as e:
            print(f"  [ETF ARB] {e}")

    # ETF quoting ----------------------------------------------------
    def quote_etf(self, pos, products):
        """
        Quote LON_ETF using a fair value implied by the components.

        Uses a tighter spread than the individual products because the
        component-implied price is a more reliable signal than any
        single product's data feed.
        """
        try:
            tb, ta = _bba(self, "TIDE_SPOT")
            wb, wa = _bba(self, "WX_SPOT")
            lb, la = _bba(self, "LHR_COUNT")
            if None in [tb, ta, wb, wa, lb, la]:
                return []

            comp_mid = ((tb + ta) / 2 + (wb + wa) / 2 + (lb + la) / 2)

            # Blend 70% component-implied with 30% data-driven
            info = products.get("LON_ETF")
            theo = comp_mid
            if info:
                data_theo = self.get_theo("LON_ETF", info)
                if data_theo and data_theo > 0:
                    theo = 0.7 * comp_mid + 0.3 * data_theo

            cur = pos.get("LON_ETF", 0)
            w = max(40, int(theo * 0.01))
            lean = -(cur / self.max_pos) * w * 1.5
            bid_p = max(1, math.floor(theo + lean - w / 2))
            ask_p = math.ceil(theo + lean + w / 2)
            sz = max(1, int(5 * (1 - abs(cur) / self.max_pos)))

            orders = []
            if cur < self.max_pos:
                orders.append(OrderRequest("LON_ETF", bid_p, Side.BUY,  sz))
            if cur > -self.max_pos:
                orders.append(OrderRequest("LON_ETF", ask_p, Side.SELL, sz))
            return orders
        except Exception as e:
            print(f"  [ETF QUOTE] {e}")
            return []

    # Main loop ------------------------------------------------------
    def run_session(self):
        self.start()
        print(f"FinalBot v2 ACTIVE on {self._cmi_url}")

        try:
            while True:
                self.cycle += 1
                pos = self.get_positions()
                products = {p.symbol: p for p in self.get_products()}

                if self.cycle % 15 == 0:
                    print(f"\n  === Cycle {self.cycle} | Pos: {dict(pos)} ===")
                    try:
                        pnl = self.get_pnl()
                        print(f"  PnL: {pnl}")
                    except Exception:
                        pass

                self.cancel_all_orders()
                all_orders = []

                # 1) Quote individual products (skip LON_FLY and LON_ETF)
                for symbol, info in products.items():
                    if symbol in self.SKIP or symbol == "LON_ETF":
                        continue

                    cur = pos.get(symbol, 0)
                    theo = self.get_theo(symbol, info)
                    if theo is None or theo <= 0:
                        continue

                    w = max(30, int(theo * 0.015))                # 1.5% of theo, min 30
                    lean = -(cur / self.max_pos) * w
                    bid_p = max(1, math.floor(theo + lean - w / 2))
                    ask_p = math.ceil(theo + lean + w / 2)
                    sz = max(1, int(5 * (1 - abs(cur) / self.max_pos)))

                    if cur < self.max_pos:
                        all_orders.append(OrderRequest(symbol, bid_p, Side.BUY,  sz))
                    if cur > -self.max_pos:
                        all_orders.append(OrderRequest(symbol, ask_p, Side.SELL, sz))

                # 2) Quote LON_ETF using component-implied fair value
                all_orders.extend(self.quote_etf(pos, products))

                if all_orders:
                    self.send_orders(all_orders)
                    if self.cycle % 15 == 0:
                        print(f"  Placed {len(all_orders)} orders")

                # 3) Cross-product arbitrage
                self.run_etf_arb(pos)

                time.sleep(3)
        except KeyboardInterrupt:
            self.cancel_all_orders()
            self.stop()
            print("FinalBot v2 stopped.")


# =================================================================
# Launcher
# =================================================================
if __name__ == "__main__":
    # EXCHANGE_URL, USERNAME, PASSWORD are provided by the competition harness.
    my_bot = FinalBot(EXCHANGE_URL, USERNAME, PASSWORD)
    print("Starting FinalBot...")
    try:
        my_bot.run_session()
    except KeyboardInterrupt:
        my_bot.cancel_all_orders()
        my_bot.stop()
        print("Bot stopped safely.")
