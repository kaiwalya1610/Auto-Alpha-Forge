# Research-Backtester

An event-driven backtesting framework for Indian equities (Zerodha Kite Connect) — paired with an **autonomous strategy research agent** that proposes, implements, and evaluates trading strategies in a loop.

The framework does the heavy lifting (data, portfolio, risk, metrics). The agent does the science (hypothesis → code → backtest → keep/discard).

---

## Table of Contents

- [What's in here](#whats-in-here)
- [How it works (high level)](#how-it-works-high-level)
- [Repository layout](#repository-layout)
- [Setup](#setup)
- [Running a manual backtest](#running-a-manual-backtest)
- [The autonomous research agent](#the-autonomous-research-agent)
  - [Running with Claude Code](#running-with-claude-code)
  - [Running with another AI agent (OpenCode, Aider, Cursor, etc.)](#running-with-another-ai-agent-opencode-aider-cursor-etc)
- [Outputs the agent produces](#outputs-the-agent-produces)
- [Safety rails](#safety-rails)
- [Further reading](#further-reading)

---

## What's in here

Two things, layered:

1. **`backtester/`** — a production-style backtesting engine: bar-by-bar event loop, portfolio manager, risk manager, position sizing (8 methods), Polars-backed data layer, results & metrics. Strategies subclass `Strategy` and emit `Signal` objects from `on_bar()`.
2. **`program.md`** — a self-contained spec for an autonomous *research agent*. It defines a fixed evaluation harness, a composite scoring function, a structured hypothesis log, an iteration budget, and an idea bank. Hand it to an LLM agent and it will iterate on `backtester/strategy/examples/agent_strategy.py` until it finds an edge (or honestly reports it didn't).

The framework also ships a Zerodha auth module (`auth/`) for fetching real historical data via Kite Connect.

---

## How it works (high level)

```
                  ┌─────────────────────────┐
                  │  AI Agent (Claude/etc.) │
                  │     reads program.md    │
                  └────────────┬────────────┘
                               │ proposes + edits
                               ▼
        ┌──────────────────────────────────────────┐
        │ backtester/strategy/examples/            │
        │   agent_strategy.py   ← the only file    │
        │                          the agent edits │
        └────────────┬─────────────────────────────┘
                     │ imported by
                     ▼
        ┌──────────────────────────────────────────┐
        │           BacktestOrchestrator           │
        │  ┌────────────┐   ┌──────────────────┐   │
        │  │ DataLoader │ → │  Event Loop      │   │
        │  └────────────┘   │  (bar by bar)    │   │
        │                   └────────┬─────────┘   │
        │                            ▼             │
        │   StrategyContext → Strategy.on_bar()    │
        │                            │             │
        │                            ▼             │
        │   Signals → PortfolioManager → RiskMgr   │
        │                            │             │
        │                            ▼             │
        │                    BacktestResults       │
        │             (sharpe, return, DD, ...)    │
        └────────────┬─────────────────────────────┘
                     │
                     ▼
        ┌──────────────────────────────────────────┐
        │ Score → results.csv + experiment_journal │
        │ Git commit on improvement, revert on     │
        │ regression. Loop.                        │
        └──────────────────────────────────────────┘
```

The core abstractions:

- **`Strategy`** — subclass it, implement `init()` and `on_bar(context)`, return a list of `Signal`s.
- **`StrategyContext`** — read-only facade giving the strategy market data, indicators, portfolio state.
- **`Signal`** — declarative intent (BUY / SELL / CLOSE / HOLD) with optional stop-loss, target, order type.
- **`BacktestOrchestrator`** — wires data, portfolio, risk, and strategy together; runs the event loop; returns `BacktestResults`.
- **`BacktestConfig.moderate()`** — the canonical config the research agent uses for every evaluation.

See `CLAUDE.md` for the in-depth architectural guide (modules, conventions, common tasks).

---

## Repository layout

```
Research-Backtester/
├── auth/                       # Zerodha auth (TOTP + OAuth, token cache)
├── backtester/
│   ├── backtest_orchestrator.py
│   ├── config.py               # BacktestConfig + presets
│   ├── results.py              # Metrics & analytics
│   ├── strategy/
│   │   ├── base_strategy.py
│   │   ├── signal.py
│   │   ├── strategy_context.py
│   │   └── examples/
│   │       ├── agent_strategy.py     ← the agent's workspace
│   │       ├── buy_and_hold.py       ← baseline
│   │       └── ma_crossover.py       ← baseline
│   ├── portfolio_manager/
│   ├── risk_manager/
│   ├── data_loader/            # Kite fetcher + parquet cache
│   └── visualization/
├── program.md                  # The autonomous-agent spec (read this!)
├── CLAUDE.md                   # In-depth architecture guide
├── results.csv                 # Append-only experiment log (created on first run)
├── experiment_journal.md       # Agent's persistent memory (created on first run)
└── requirements.txt
```

---

## Setup

```bash
# 1. Create env (example with conda)
conda create -n zerodhaAPI python=3.11 -y
conda activate zerodhaAPI

# 2. Install deps
pip install -r requirements.txt
pip install polars rich   # recommended

# 3. Patch program.md with this machine's python path + repo root
./setup.sh
# or pass an explicit interpreter:
# ./setup.sh /opt/venv/bin/python

# 4. (Optional, for live data) configure .env
cat > .env <<EOF
API_KEY=your_kite_api_key
API_SECRET=your_kite_api_secret
USER_ID=your_zerodha_user_id
USER_PASSWORD=your_zerodha_password
TOTP_KEY=your_totp_secret
EOF
```

Cached parquet data already lives under `backtester/data_loader/cache/` for SBIN, INFY, TCS, RELIANCE, HDFCBANK at daily resolution — enough to run the agent without any auth setup.

---

## Running a manual backtest

```python
from backtester.backtest_orchestrator import BacktestOrchestrator, BacktestConfig
from backtester.data_loader import Interval
from backtester.strategy.examples.ma_crossover import MovingAverageCrossover

config = BacktestConfig.moderate()
config.initial_capital = 1_000_000

orchestrator = BacktestOrchestrator([MovingAverageCrossover()], config)
results = orchestrator.run(
    symbols=['SBIN', 'INFY', 'TCS', 'RELIANCE', 'HDFCBANK'],
    start_date='2024-01-01',
    end_date='2024-12-31',
    interval=Interval.DAY,
    exchange='NSE',
)

print(results.summary())
```

---

## The autonomous research agent

The whole agent is specified in **`program.md`**. It is a single self-contained prompt covering:

- **Fixed evaluation harness** — exact symbols, date range, config. The agent is forbidden from changing it.
- **Composite score** — weighted combination of Sharpe, return, drawdown, win rate, profit factor; with hard constraints (DD > 25% → auto-discard) and a parameter-count penalty against overfitting.
- **Hypothesis logging** — every iteration must state thesis / mechanism / expected impact *before* writing code, and post-experiment insight *after*.
- **Iteration budget** — hard cap of 30 iterations + diminishing-returns early stop.
- **Approach registry & deduplication** — `experiment_journal.md` is the agent's persistent memory across conversations; it cannot retry approaches it already tried.
- **Git protocol** — commit on improvement, revert strategy file on regression, never touch framework code.
- **Idea bank** — 5 tiers of strategies from SMA crossovers up to ensemble / regime-adaptive systems.

### Running with Claude Code

```bash
cd /path/to/Research-Backtester
claude
```

Then in the Claude Code prompt:

```
Read program.md and execute the main loop. Run one iteration, then stop and show me
the result. I'll tell you when to continue.
```

For fully autonomous mode:

```
Read program.md and execute the main loop until you hit the 30-iteration budget,
the diminishing-returns early stop, or an unrecoverable error. Update results.csv
and experiment_journal.md after every iteration.
```

Tips:
- Use `/loop` (built-in skill) if you want it scheduled on an interval rather than one big run.
- The agent commits on its own — work on a dedicated branch (`agent-research` is the convention used in `program.md`).
- Watch `results.csv` and `experiment_journal.md` to follow progress without interrupting the agent.

### Running with another AI agent (OpenCode, Aider, Cursor, etc.)

`program.md` is plain Markdown and references absolute paths only in two places (the Python interpreter and the repo root). Any agent that can read files, write files, and execute shell commands can run it. The general recipe:

1. **Point the agent at the repo root** as its working directory.
2. **Run `./setup.sh`** to patch `program.md` with the correct Python interpreter and repo root for your machine (idempotent — re-run after switching envs).
3. **Feed `program.md` as the initial system / task prompt**. Examples:

   - **OpenCode / openclaw**: `opencode run "$(cat program.md)\n\nExecute the main loop."`
   - **Aider**: `aider --message "Read program.md in this repo and execute the main loop, one iteration at a time."` (Aider already has shell + edit + git tools, which is everything the agent needs.)
   - **Cursor**: open the repo, paste `program.md` into the chat with `Execute the main loop.` appended.
   - **Custom Agent SDK loop**: load `program.md` as the system prompt, give the agent `bash`, `read_file`, `write_file`, and `git` tools, and run until completion.

4. **Required tool surface** (any agent must have these to run the loop):
   - read & write files
   - run shell commands (to invoke Python and `git`)
   - persist context across turns (otherwise the journal must be re-read each turn — which `program.md` already mandates as step 1 of every iteration, so even stateless agents work)

5. **Stop conditions are encoded in the prompt itself** — the agent will stop at 30 iterations, on diminishing returns, or on repeated errors. You don't need an external orchestrator.

If your agent doesn't have git tools, remove the "Git Protocol" section and the agent will simply skip commits while still updating `results.csv` and `experiment_journal.md`.

---

## Outputs the agent produces

| File | Purpose |
|---|---|
| `backtester/strategy/examples/agent_strategy.py` | The current best strategy (overwritten each successful iteration). |
| `results.csv` | Append-only log: one row per iteration with score + metrics + status. |
| `experiment_journal.md` | The agent's persistent memory: summary, approach registry, per-iteration hypothesis & post-mortem. |
| Git commits on `agent-research` | One commit per kept/discarded iteration, message includes score. |

To inspect progress at any time:

```bash
tail -n 20 results.csv
sed -n '1,40p' experiment_journal.md
git log --oneline agent-research
```

---

## Safety rails

The agent operates under several constraints baked into `program.md`:

- **Sandbox**: it can only modify `agent_strategy.py`. The framework, baselines, and configs are off-limits.
- **No new dependencies**: it can import only `numpy`, `typing`, `logging`, and `backtester.strategy.*`.
- **Fixed evaluation**: it cannot change symbols, dates, or config to chase a better number.
- **Hard constraints in scoring**: drawdown > 25%, fewer than 10 trades, or negative Sharpe → automatic discard.
- **Parameter penalty**: every tunable parameter costs 0.02 of score, capping complexity at ~5 params.
- **Iteration budget**: 30 hard cap, plus a diminishing-returns early stop.
- **Hypothesis-first**: it must articulate *why* a strategy should work before coding it.

These exist to prevent the most common LLM failure mode in this kind of loop: random parameter twiddling that overfits to the eval window.

---

## Further reading

- **`program.md`** — the full agent spec (read this if you want to understand or modify the loop).
- **`CLAUDE.md`** — deep architectural guide to the framework: modules, design patterns, conventions, common tasks.
- **`backtester/strategy/examples/`** — reference strategies (`buy_and_hold.py`, `ma_crossover.py`, `mtf_trend_following.py`, ...) showing the `Strategy` API in practice.
