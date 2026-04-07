# Experiment Journal

## Summary
- **Best score**: -1.0 (no valid strategy yet)
- **Best approach**: None yet
- **Iterations completed**: 2 / 30
- **Consecutive regressions**: 2
- **Current tier**: Tier 1 (Foundations)
- **What works**: Nothing validated yet
- **What doesn't work**: BuyAndHold (5 trades); MACrossover 10/50 (0 trades); Momentum 10d (whipsaw, -1.8%); Momentum 20d + trend filter (worse, -2.8%)

## Key Observations from Baselines
- BuyAndHold returned +5.8% in 2024 for SBIN/INFY/TCS/RELIANCE/HDFCBANK
- MACrossover 10/50 never fired a single signal — market stayed in single trend per symbol
- Momentum strategies generate too many false signals → negative Sharpe
- Risk monitor fires warnings about >10% position size (in warn mode, trades still execute)
- Target: beat both baselines (both scored -1.0, so any valid strategy with sharpe>0 and >10 trades wins)

## Approach Registry
| ID | Approach Family | Key Params | Best Score | Status |
|----|----------------|------------|------------|--------|
| B1 | BuyAndHold | position_pct=0.19 | -1.0 | baseline (too few trades) |
| B2 | SMA Crossover | fast=10, slow=50 | -1.0 | baseline (0 crossovers) |
| A1 | Momentum | period=10, threshold=0.01 | -1.0 | discarded (neg sharpe, whipsaw) |
| A2 | Momentum + Trend Filter | mom=20, trend=50, threshold=0.02 | -1.0 | discarded (neg sharpe, worse) |

## Detailed Log

### Iteration 0 (Baseline: BuyAndHold)
- sharpe=0.476, return_pct=5.80%, max_dd=7.44%, win_rate=0.0, pf=inf, trades=5
- Fails hard constraint: total_trades < 10 → score = -1.0
- Note: buy-and-hold returns ~5.8% in 2024 for these 5 stocks

### Iteration 0 (Baseline: MovingAverageCrossover 10/50)
- sharpe=0.0, return_pct=0.0%, max_dd=0.0%, win_rate=0.0, pf=inf, trades=0
- Fails hard constraint: total_trades < 10 → score = -1.0
- Note: zero crossovers in entire 2024 — market never reversed MA trend

### Iteration 1

#### Pre-Experiment
- **Thesis**: Short-term 10-day price momentum captures persistent trends
- **Mechanism**: Buy when 10d return > 1%, close when < -1%
- **Change**: New strategy from scratch
- **Expected impact**: 15+ trades, Sharpe > 0.5
- **Risk**: Whipsaw in range-bound periods

#### Post-Experiment
- **Result**: score=-1.0 (hard constraint: negative sharpe)
- **Metrics**: sharpe=-0.345, return_pct=-1.81%, max_dd=4.99%, win_rate=32.7%, pf=0.74, trades=99
- **Expected vs Actual**: Expected positive Sharpe; got negative. 99 trades but only 32.7% win rate — massive whipsaw.
- **Insight**: 10-day momentum generates far too many false signals in 2024 Indian equities. Stocks are choppy at short horizons.
- **Decision**: discard

### Iteration 2

#### Pre-Experiment
- **Thesis**: 20-day momentum with 50-day trend filter reduces whipsaw by only trading in uptrends
- **Mechanism**: Require price > 50 SMA (uptrend) AND 20d momentum > 2%
- **Change**: Longer momentum (20d), added trend filter (50 SMA), raised threshold (2%)
- **Expected impact**: Fewer but higher-quality trades, positive Sharpe, win rate > 45%
- **Risk**: Too few trades if filter is too restrictive

#### Post-Experiment
- **Result**: score=-1.0 (hard constraint: negative sharpe)
- **Metrics**: sharpe=-0.639, return_pct=-2.78%, max_dd=3.52%, win_rate=20.8%, pf=0.36, trades=49
- **Expected vs Actual**: Halved trades (99→49) but win rate collapsed (32.7%→20.8%). The trend filter made entries even later, buying at local tops.
- **Insight**: Momentum-based entries are buying too late in moves. Adding a trend filter makes it worse because we wait even longer. Need a fundamentally different entry: buy weakness, not strength.
- **Decision**: discard
