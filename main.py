"""Momentum rider for cbBTC/USDC (make.fun btc-race-24h-20261118-1444).

A long-only trend follower on 1-minute bars. It stays in cash most of the time
and only buys when the market shows a genuine multi-timescale uptrend; it rides
that trend until the trend reverses, with a trailing stop and a hard stop as
safety nets. It never shorts, never uses leverage, and never trades on noise.

Why this shape: on 1-minute bars BTC's per-minute noise (~7 bps) is large next
to a round trip's cost (~26 bps in fees, slippage and price impact), so fast
signals (1-minute EMA crosses, short breakouts) whipsaw and bleed. The only
moves worth paying 26 bps for are multi-hour trends. This bot therefore waits
for a 1-hour uptrend confirmed on a 30-minute window, then holds until the
1-hour trend itself reverses.

Rules (all in integer basis points, computed from closes only):
  Entry (flat): 60-bar momentum >= +50 bps AND 30-bar momentum >= +30 bps.
      Both windows must agree, so a one-hour bounce that is already fading on
      the 30-minute window does not trigger a buy.
  Exit (holding), sell the whole position when any of these holds:
      - 60-bar momentum < -50 bps (the 1-hour trend reversed);
      - position value <= 98.5% of its peak value (150 bps trailing stop);
      - position value <= 98% of its cost (200 bps hard stop, a safety net
        against a flash crash; the trend-reversal exit normally fires first).
  Size: the whole cash balance on entry (max 100% of equity, the one position
      allowed). Each order caps slippage at 100 bps past the close it was
      decided on, so a fill far from the close is refused and retried on the
      next bar while the (level-based) signal still holds.

Determinism: pure integer arithmetic on the closes the harness sends. No wall
clock, no network, no files, no randomness. The same bars always give the
same orders.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# --- Strategy parameters (basis points unless noted) ---
LONG_N = 60            # long momentum window, in bars (1 hour)
LONG_ENTRY_BPS = 50    # enter when the 60-bar rise is at least this
SHORT_N = 30           # confirmation window, in bars (30 minutes)
SHORT_ENTRY_BPS = 30   # ... and the 30-bar rise is at least this
EXIT_MOM_BPS = -50     # exit when the 60-bar momentum falls below this
TRAIL_BPS = 150        # trailing stop: sell 150 bps below the peak value
HARD_STOP_BPS = 200    # hard stop: sell 200 bps below cost
MAX_SLIPPAGE_BPS = 100  # 1% past the close an order was decided on

# Closes seen so far, oldest first (raw price units, as the harness sends them).
_closes = []
# Peak value (micro-USDC) of the open position since entry; 0 while flat.
_peak_value = 0


def _momentum_bps(closes, n):
    """Rise of the latest close over the close n bars ago, in bps (integer).

    Returns None until n + 1 closes have been seen.
    """
    if len(closes) < n + 1:
        return None
    now = closes[-1]
    then = closes[-n - 1]
    return (now - then) * 10_000 // then


def on_batch(state, batch):
    global _peak_value

    # Only decide on a fresh bar for our symbol; a batch without one carries
    # no new information and any order would be refused (no_bar) anyway.
    if not any(bar["symbol"] == SYMBOL for bar in batch["bars"]):
        return []
    close = state.close(SYMBOL)
    if close is None:
        return []
    _closes.append(close)

    # Warm-up bars build history but may not be traded on.
    if state.warming_up:
        return []

    held = state.positions.get(SYMBOL)
    mom_long = _momentum_bps(_closes, LONG_N)
    mom_short = _momentum_bps(_closes, SHORT_N)

    if held is not None and held.qty > 0:
        # --- Holding: watch the exits. ---
        value = state.value(SYMBOL, held.qty)
        if value > _peak_value:
            _peak_value = value

        # 1) The 1-hour trend reversed.
        if mom_long is not None and mom_long < EXIT_MOM_BPS:
            _peak_value = 0
            return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        # 2) Trailing stop: 150 bps below the peak value.
        if _peak_value > 0 and value * 10_000 <= _peak_value * (10_000 - TRAIL_BPS):
            _peak_value = 0
            return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        # 3) Hard stop: 200 bps below cost.
        if value * 10_000 <= held.cost * (10_000 - HARD_STOP_BPS):
            _peak_value = 0
            return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []

    # --- Flat: wait for a confirmed multi-timescale uptrend. ---
    _peak_value = 0
    if mom_long is None or mom_short is None:
        return []
    if mom_long < LONG_ENTRY_BPS or mom_short < SHORT_ENTRY_BPS:
        return []

    # Buy the whole cash balance (capped at 100% of equity by weight_room).
    notional = min(state.cash, state.weight_room(SYMBOL))
    if notional < int(state.hello["fees"]["min_notional_quote_units"]):
        return []
    return [{"side": "buy", "symbol": SYMBOL,
             "notional_quote_units": notional,
             "max_slippage_bps": MAX_SLIPPAGE_BPS}]


makefun_bars.run(on_batch)
