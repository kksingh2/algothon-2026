# algothon 2026

my bot for the imperial college algothon, february to march 2026. finished top 10 in london.

the exchange had 8 products driven by live london data:

- thames tide level
- london weather
- heathrow arrivals and departures
- an etf basket of three of them
- an options-style product on the etf

## what the bot does

each loop:

1. pull the latest data for each product (cached so we dont hit the api rate limit)
2. work out a fair value for each product from the data
3. quote a buy and a sell around that fair value, with a small lean against my current position so it gets back to flat
4. if the etf price moves too far from the sum of its parts, trade both sides to close the gap

## run

```
python finalbot.py
```

needs your exchange credentials and the data feeds the bot was wired up to.
