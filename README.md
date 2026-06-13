# Algothon 2026

My bot for the Imperial College Algothon, a 24-hour algorithmic trading competition. It finished top 10 in London.

## What made this competition unusual

Instead of trading company shares, the eight things you could trade were tied to real London data feeds:

- The Thames tide level
- London temperature and humidity
- Arrivals and departures at Heathrow
- An ETF, which was simply a basket of three of the above added together
- An options-style product built on that ETF

## How the bot works

Each loop, the bot does four things:

1. **Fetch the data.** It pulls the latest reading for each product. The flight API only allows a limited number of requests, so every reading is cached for a short time and reused instead of asking again every second.
2. **Work out a fair price.** For each product it calculates what the price should be from the underlying data, using the competition's settlement formulas.
3. **Quote both sides.** It offers to buy slightly below that fair price and sell slightly above it. This is called market making: you earn the small gap each time someone trades with you. If the bot has built up a large position, it nudges its prices to sell some back, which keeps risk under control.
4. **Arbitrage the basket.** The ETF should equal the sum of its three parts. When it drifts too far from that sum, the bot buys the cheap side and sells the dear side at the same time to lock in the difference.

## Files

- `finalbot.py` is the competition bot.
- `bot_template.py` (provided by the organisers) handles the connection to the exchange.

## Run it

```
python finalbot.py
```

It needs the exchange credentials and the live data feeds from the competition.
