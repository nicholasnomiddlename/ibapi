# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an automated wheel options trading system using Interactive Brokers Gateway. The system implements a "wheel strategy" on Ford (F) stock, managing a balanced cash vs. equity position through systematic selling of cash-secured puts and covered calls.

## Wheel Strategy Specifics

**Target**: Ford (F) stock with allocation equivalent to 1000 shares
**Structure**: 5-week rolling options strategy with 1 contract per week
**Position Management**:
- **Cash-heavy periods**: Sell cash-secured puts more aggressively (closer strikes, nearer expirations)
- **Stock-heavy periods**: Sell covered calls more aggressively (closer strikes, nearer expirations)
**Goal**: Maintain long equity exposure while generating premium income

## System Architecture

- **Connection Management**: IB Gateway integration using ib_insync
- **Options Chain Monitoring**: Real-time tracking of available strikes and expirations
- **Delta Management**: Continuous monitoring of option deltas with rolling logic
- **Position Rebalancing**: Automated cash/stock balance management
- **Schedule Management**: 5-week rolling window with weekly contract management
- **Market Data Processing**: Price movements, premium changes, and delta shifts

## Development Commands

```bash
# Install dependencies
pip install ib_insync

# Connect to IB Gateway (paper trading)
# Gateway runs on port 4002 (paper) or 4001 (live)

# Run the trading system
python wheel_trader.py

# Monitor positions and delta
python monitor_positions.py
```

## Key Implementation Areas

**Options Chain Management**: Query and filter available options contracts within the 5-week window
**Delta Monitoring**: Track delta changes and trigger rolling decisions
**Order Management**: Place, modify, and cancel cash-secured puts and covered calls
**Position Tracking**: Monitor current stock holdings vs. target allocation
**Rolling Logic**: Manage when to close current positions and open new ones based on delta targets

## IB Gateway Setup

- Paper trading account configured
- Market data permissions enabled for options
- Gateway connection on port 4002 (paper trading)
- Options trading permissions required