# Momentum Rider — cbBTC/USDC trading bot

Entry for the make.fun competition `btc-race-24h-20261118-1444`: a long-only
trend-following bot that trades Coinbase Wrapped BTC (CBBTC) against USDC on
1-minute bars, starting with $1,000 of paper money.

## Strategy

1-minute bars are noisy (~7 bps per minute) next to a round trip's ~26 bps
cost, so fast signals whipsaw. This bot waits for a real multi-hour trend:

- **Buy** (full equity) when the 60-bar momentum is ≥ +50 bps **and** the
  30-bar momentum is ≥ +30 bps — both windows must agree.
- **Sell** the whole position when the 60-bar momentum falls below −50 bps
  (trend reversed), or on a 150 bps trailing stop from the peak value, or on
  a 200 bps hard stop below cost.
- Orders cap slippage at 100 bps past the close they were decided on.

## Files

- `main.py` — the bot (Python 3.13, standard library only).
- `vendor/makefun_bars.py` — byte-identical copy of the kit's Python SDK shim
  (`sdk/makefun_bars.py`), kept under `vendor/` as the kit instructs.

## Grade it locally

From the kit directory:

```sh
node cli/makefun.mjs grade-local \
  --kit <path-to-kit> \
  --bot <path-to-this-entry>/main.py \
  --driver process
```

The bot runs twice on the frozen 24-hour dev window; the two action logs must
match (it is deterministic: integer arithmetic on closes only, no clock,
no network, no randomness). The dev gate requires net PnL > $0.
