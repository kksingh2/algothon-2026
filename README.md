# algothon 2026

a trading bot i wrote for the imperial college algothon, a 24 hour algorithmic trading competition. finished top 10 in london.

the cool thing about this exchange was that instead of stock prices, the 8 things you could trade were tied to real london data:

- thames tide level
- london temperature and humidity
- arrivals and departures at heathrow
- an etf which was just a basket of three of the above
- an options-style product on top of the etf

how the bot trades:

1. every loop it fetches the latest london data. the apis have rate limits so it caches each response for a short time instead of asking again every second.
2. for each product, it works out what i think the fair price should be from the data.
3. it puts in a price to buy slightly below the fair price and a price to sell slightly above. this is called market making, you make a tiny bit each time the other side trades with you.
4. if i build up too much of one product, the bot nudges its prices down a bit so it sells some back. this keeps me from sitting on a big risky position.
5. the etf is just a basket of three other products, so if the etf trades too far away from the sum of those three, the bot trades both sides at once to close the gap. this is called arbitrage.

## run

```
python finalbot.py
```

needs the exchange credentials and the data feeds the bot was wired up to during the competition.
