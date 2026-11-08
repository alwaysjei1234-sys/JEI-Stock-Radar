# Technical candidate under evaluation (not adopted)

Source hypothesis supplied by user: MACD histogram negative-to-positive, expanding Bollinger width, close above rising MA20; KD crossover after trend confirmation; RSI bearish divergence plus MA20 break as risk exit.

Implemented **research-only**: EMA12/26 MACD histogram vs EMA9 signal, Bollinger width 20 bars / 2 standard deviations, MA20 rising and close above, and a conservative RSI14 high-divergence *proxy warning*. The proxy is **not** validated swing-pivot divergence. KD entry and exit execution are intentionally deferred until historical price data, transaction costs, trading-day alignment and out-of-sample comparison are available.

Do not assume MACD implies institutional accumulation or RSI divergence proves selling by institutions. Need benchmark against simple MA20, MACD-only, buy-and-hold, and walk-forward splits, with fees, tax and slippage; track win rate, expectancy, drawdown, turnover and false signals.
