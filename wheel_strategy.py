#!/usr/bin/env python3
"""
Wheel Strategy Portfolio Manager

Core logic for managing a wheel strategy on a single ticker (Ford F).
Maintains 50/50 cash/equity balance through systematic options selling:
- Cash-heavy: Sell cash-secured puts more aggressively
- Equity-heavy: Sell covered calls more aggressively

Target: 1000 shares equivalent allocation over 5-week rolling window
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from ib_insync import *

@dataclass
class PortfolioBalance:
    """Current portfolio balance assessment."""
    cash_value: float
    equity_value: float
    total_value: float
    equity_ratio: float  # 0.0 = all cash, 1.0 = all equity
    cash_ratio: float    # 0.0 = no cash, 1.0 = all cash
    imbalance_ratio: float  # -1.0 = heavily cash, +1.0 = heavily equity, 0.0 = balanced

    @property
    def is_cash_heavy(self) -> bool:
        """Portfolio has excess cash (< 40% equity)."""
        return self.equity_ratio < 0.40

    @property
    def is_equity_heavy(self) -> bool:
        """Portfolio has excess equity (> 60% equity)."""
        return self.equity_ratio > 0.60

    @property
    def is_balanced(self) -> bool:
        """Portfolio is reasonably balanced (40-60% equity)."""
        return 0.40 <= self.equity_ratio <= 0.60

@dataclass
class DeltaTargets:
    """Delta targeting based on portfolio imbalance."""
    put_delta_min: float  # Minimum delta for cash-secured puts
    put_delta_max: float  # Maximum delta for cash-secured puts
    call_delta_min: float # Minimum delta for covered calls
    call_delta_max: float # Maximum delta for covered calls

    def get_put_target_delta(self) -> float:
        """Get target delta for puts (midpoint of range)."""
        return (self.put_delta_min + self.put_delta_max) / 2

    def get_call_target_delta(self) -> float:
        """Get target delta for calls (midpoint of range)."""
        return (self.call_delta_min + self.call_delta_max) / 2

@dataclass
class StrategyConfig:
    """Strategy configuration from user input."""
    symbol: str
    funding_amount: float
    target_shares: int
    confirmed: bool = False

class WheelStrategy:
    """Main wheel strategy implementation."""

    def __init__(self):
        self.config = None
        self.ib = IB()
        self.stock_contract = None

    async def connect(self, host: str = '127.0.0.1', port: int = 4002, client_id: int = 3):
        """Connect to IB Gateway."""
        await self.ib.connectAsync(host, port, client_id)
        print("✓ Connected to IB Gateway")

    async def setup_strategy(self) -> StrategyConfig:
        """Interactive setup flow for strategy configuration."""

        print("\n=== Wheel Strategy Setup ===")

        # Get ticker symbol
        while True:
            symbol = input("Enter ticker symbol (e.g., F, GLD, SPY): ").strip().upper()
            if symbol and len(symbol) <= 5:
                break
            print("Please enter a valid ticker symbol.")

        # Validate the ticker by qualifying contract
        print(f"Validating {symbol}...")
        temp_contract = Stock(symbol, 'SMART', 'USD')
        qualified = await self.ib.qualifyContractsAsync(temp_contract)

        if not qualified:
            print(f"❌ Could not find ticker {symbol}. Please check the symbol and try again.")
            return await self.setup_strategy()

        self.stock_contract = qualified[0]
        print(f"✓ Found {symbol} (Contract ID: {self.stock_contract.conId})")

        # Get current stock price
        current_price = await self.get_current_stock_price()
        print(f"✓ Current price: ${current_price:.2f}")

        # Get funding amount
        while True:
            try:
                funding_input = input(f"\nEnter funding amount for {symbol} wheel strategy (e.g., 50000): $")
                funding_amount = float(funding_input.replace(',', ''))
                if funding_amount > 0:
                    break
                print("Please enter a positive amount.")
            except ValueError:
                print("Please enter a valid number.")

        # Calculate target shares (aim for ~50% initial equity allocation)
        import math
        if math.isnan(current_price):
            print(f"⚠️  Warning: Invalid stock price, using default target of 100 shares")
            target_shares = 100
        else:
            target_shares = int((funding_amount * 0.5) / current_price)
            target_shares = max(100, (target_shares // 100) * 100)  # Round to nearest 100 shares, minimum 100

        # Show current account balance
        account_summary = await self.ib.accountSummaryAsync()
        available_cash = 0.0
        total_net_liq = 0.0

        for item in account_summary:
            if item.tag == 'TotalCashValue':
                available_cash = float(item.value)
            elif item.tag == 'NetLiquidation':
                total_net_liq = float(item.value)

        # Show confirmation
        print(f"\n=== Strategy Configuration ===")
        print(f"Ticker: {symbol}")
        print(f"Current Price: ${current_price:.2f}")
        print(f"Strategy Funding: ${funding_amount:,.2f}")
        print(f"Target Shares: {target_shares:,} shares (${target_shares * current_price:,.2f} equity value)")
        print(f"Planned Allocation: ~50% equity / ~50% cash")

        print(f"\n=== Account Status ===")
        print(f"Available Cash: ${available_cash:,.2f}")
        print(f"Total Net Liquidation: ${total_net_liq:,.2f}")

        if funding_amount > available_cash:
            print(f"⚠️  WARNING: Strategy funding (${funding_amount:,.2f}) exceeds available cash (${available_cash:,.2f})")

        # Get confirmation
        while True:
            confirm = input(f"\nConfirm setup for {symbol} wheel strategy with ${funding_amount:,.2f} funding? (y/n): ").strip().lower()
            if confirm in ['y', 'yes']:
                confirmed = True
                break
            elif confirm in ['n', 'no']:
                print("Setup cancelled.")
                return None
            else:
                print("Please enter 'y' or 'n'")

        config = StrategyConfig(
            symbol=symbol,
            funding_amount=funding_amount,
            target_shares=target_shares,
            confirmed=True
        )

        self.config = config
        print(f"✅ {symbol} wheel strategy configured!")
        return config

    async def get_current_stock_price(self) -> float:
        """Get current stock price."""
        self.ib.reqMktData(self.stock_contract, '', False, False)
        await asyncio.sleep(1)
        ticker = self.ib.ticker(self.stock_contract)

        import math

        # Try last price first
        if ticker.last and not math.isnan(ticker.last) and ticker.last > 0:
            return ticker.last
        # Try close price if last not available
        elif ticker.close and not math.isnan(ticker.close) and ticker.close > 0:
            return ticker.close
        # Try bid/ask midpoint
        elif (ticker.bid and ticker.ask and
              not math.isnan(ticker.bid) and not math.isnan(ticker.ask) and
              ticker.bid > 0 and ticker.ask > 0):
            return (ticker.bid + ticker.ask) / 2
        else:
            # Fallback - this shouldn't happen but prevents crashes
            print(f"⚠️  Warning: Could not get valid price for {self.config.symbol}, using $10.00 as fallback")
            return 10.0

    async def assess_portfolio_balance(self) -> PortfolioBalance:
        """Assess current portfolio balance between cash and equity."""

        # Get account summary
        account_summary = await self.ib.accountSummaryAsync()
        cash_value = 0.0
        total_value = 0.0

        for item in account_summary:
            if item.tag == 'TotalCashValue':
                cash_value = float(item.value)
            elif item.tag == 'NetLiquidation':
                total_value = float(item.value)

        # Get current stock position
        positions = await self.ib.reqPositionsAsync()
        equity_shares = 0

        for pos in positions:
            if (hasattr(pos.contract, 'symbol') and
                pos.contract.symbol == self.config.symbol and
                pos.contract.secType == 'STK'):
                equity_shares = pos.position
                break

        # Calculate equity value
        current_price = await self.get_current_stock_price()
        equity_value = equity_shares * current_price

        # Calculate ratios
        if total_value > 0:
            equity_ratio = equity_value / total_value
            cash_ratio = cash_value / total_value
        else:
            equity_ratio = 0.0
            cash_ratio = 1.0

        # Calculate imbalance (-1 = cash heavy, +1 = equity heavy, 0 = balanced)
        target_equity_ratio = 0.5
        imbalance_ratio = (equity_ratio - target_equity_ratio) * 2

        return PortfolioBalance(
            cash_value=cash_value,
            equity_value=equity_value,
            total_value=total_value,
            equity_ratio=equity_ratio,
            cash_ratio=cash_ratio,
            imbalance_ratio=imbalance_ratio
        )

    def calculate_delta_targets(self, balance: PortfolioBalance) -> DeltaTargets:
        """Calculate delta targets based on portfolio imbalance."""

        # Base delta ranges (conservative)
        base_put_delta = 0.20  # ~20 delta puts
        base_call_delta = 0.20  # ~20 delta calls

        # Adjust aggressiveness based on imbalance
        # More imbalanced = more aggressive (higher deltas)
        aggressiveness = abs(balance.imbalance_ratio)

        if balance.is_cash_heavy:
            # Cash heavy: be more aggressive on puts to acquire equity
            put_delta_adjustment = aggressiveness * 0.15  # Up to 15 delta more aggressive
            call_delta_adjustment = -aggressiveness * 0.05  # Slightly less aggressive on calls

            put_delta_target = base_put_delta + put_delta_adjustment
            call_delta_target = base_call_delta + call_delta_adjustment

        elif balance.is_equity_heavy:
            # Equity heavy: be more aggressive on calls to reduce equity
            put_delta_adjustment = -aggressiveness * 0.05  # Less aggressive on puts
            call_delta_adjustment = aggressiveness * 0.15  # More aggressive on calls

            put_delta_target = base_put_delta + put_delta_adjustment
            call_delta_target = base_call_delta + call_delta_adjustment

        else:
            # Balanced: maintain base deltas
            put_delta_target = base_put_delta
            call_delta_target = base_call_delta

        # Set ranges (±5 delta around target)
        delta_range = 0.05

        return DeltaTargets(
            put_delta_min=max(0.10, put_delta_target - delta_range),
            put_delta_max=min(0.45, put_delta_target + delta_range),
            call_delta_min=max(0.10, call_delta_target - delta_range),
            call_delta_max=min(0.45, call_delta_target + delta_range)
        )

    async def analyze_portfolio(self) -> Tuple[PortfolioBalance, DeltaTargets]:
        """Analyze current portfolio and return balance + delta targets."""

        balance = await self.assess_portfolio_balance()
        targets = self.calculate_delta_targets(balance)

        print(f"\n=== Portfolio Analysis ===")
        print(f"Cash Value: ${balance.cash_value:,.2f}")
        print(f"Equity Value: ${balance.equity_value:,.2f}")
        print(f"Total Value: ${balance.total_value:,.2f}")
        print(f"Equity Ratio: {balance.equity_ratio:.1%}")
        print(f"Imbalance: {balance.imbalance_ratio:.2f} ({'Cash Heavy' if balance.is_cash_heavy else 'Equity Heavy' if balance.is_equity_heavy else 'Balanced'})")

        print(f"\n=== Delta Targets ===")
        print(f"Put Deltas: {targets.put_delta_min:.2f} - {targets.put_delta_max:.2f} (target: {targets.get_put_target_delta():.2f})")
        print(f"Call Deltas: {targets.call_delta_min:.2f} - {targets.call_delta_max:.2f} (target: {targets.get_call_target_delta():.2f})")

        return balance, targets

    async def get_put_recommendations(self, targets: DeltaTargets, max_contracts: int = 5) -> List[Dict]:
        """Get specific cash-secured put recommendations."""

        if not self.config:
            return []

        print(f"\n🔍 Searching for cash-secured puts for {self.config.symbol}...")

        # Check if we're during market hours (rough check)
        from datetime import datetime, time
        now = datetime.now()
        market_hours = time(9, 30) <= now.time() <= time(16, 0) and now.weekday() < 5
        if not market_hours:
            print("⚠️  Warning: Market appears to be closed. Greeks may not be available.")
            print("   For live bid/ask data and Greeks, run during market hours (9:30 AM - 4:00 PM ET).")

        # Get options chain
        chains = await self.ib.reqSecDefOptParamsAsync(
            self.stock_contract.symbol, '', self.stock_contract.secType, self.stock_contract.conId
        )

        if not chains:
            print("❌ No options chains found")
            return []

        chain = chains[0]
        current_price = await self.get_current_stock_price()

        # Get next 5 weeks of expirations
        all_expirations = sorted(chain.expirations)
        next_5_weeks = []

        for exp_str in all_expirations:
            exp_date = datetime.strptime(exp_str, '%Y%m%d')
            days_out = (exp_date - datetime.now()).days
            if 7 <= days_out <= 35:  # 1-5 weeks out
                next_5_weeks.append(exp_str)
            if len(next_5_weeks) >= 5:
                break

        # Get strikes below current price (for puts)
        strikes = sorted([float(s) for s in chain.strikes])
        # Filter to strikes that are reasonable put candidates (not too far OTM)
        put_strikes = [s for s in strikes if s < current_price and s >= current_price * 0.85]  # 15% below to current price
        # Only use "clean" strikes (avoid weird decimals)
        clean_strikes = [s for s in put_strikes if s == int(s) or s == int(s) + 0.5]

        print(f"Current price: ${current_price:.2f}")
        print(f"All put strikes: {put_strikes}")
        print(f"Clean strikes: {clean_strikes}")
        print(f"Next 5 week expirations: {next_5_weeks}")

        recommendations = []

        for exp in next_5_weeks[:3]:  # Test first 3 expirations
            for strike in clean_strikes[-5:]:  # Test last 5 clean strikes (closest to current price)

                print(f"  Trying {self.config.symbol} {exp} ${strike}P...")

                # Create put contract - try CBOE first for better options data
                put_contract = Option(self.config.symbol, exp, strike, 'P', 'CBOE')

                try:
                    # Qualify the contract
                    qualified = await self.ib.qualifyContractsAsync(put_contract)
                    if not qualified:
                        # Try SMART exchange as fallback
                        print(f"    🔄 CBOE failed, trying SMART...")
                        put_contract = Option(self.config.symbol, exp, strike, 'P', 'SMART')
                        qualified = await self.ib.qualifyContractsAsync(put_contract)
                        if not qualified:
                            print(f"    ❌ Could not qualify contract on any exchange")
                            continue

                    put_contract = qualified[0]

                    # Get market data
                    self.ib.reqMktData(put_contract, '', False, False)
                    await asyncio.sleep(1)  # Longer pause for data

                    ticker = self.ib.ticker(put_contract)

                    print(f"    📊 Bid: {ticker.bid}, Ask: {ticker.ask}, Last: {ticker.last}")

                    # Handle NaN values (market closed)
                    import math
                    bid_valid = ticker.bid and not math.isnan(ticker.bid) and ticker.bid > 0
                    ask_valid = ticker.ask and not math.isnan(ticker.ask) and ticker.ask > 0
                    last_valid = ticker.last and not math.isnan(ticker.last) and ticker.last > 0

                    # Use last price if bid/ask not available (market closed)
                    if not bid_valid or not ask_valid:
                        if last_valid:
                            print(f"    📊 Using last price ${ticker.last:.3f} (market closed)")
                            # Estimate bid/ask from last price (typical spread ~$0.01 for cheap options)
                            estimated_mid = ticker.last
                            estimated_spread = max(0.01, estimated_mid * 0.1)  # 10% spread minimum $0.01
                            estimated_bid = estimated_mid - estimated_spread/2
                            estimated_ask = estimated_mid + estimated_spread/2
                            print(f"    📊 Estimated Bid: ${estimated_bid:.3f}, Ask: ${estimated_ask:.3f}")
                            ticker.bid = estimated_bid
                            ticker.ask = estimated_ask
                        else:
                            print(f"    ❌ No valid price data available")
                            continue

                    if ticker.ask < ticker.bid:
                        print(f"    ❌ Invalid spread (ask < bid)")
                        continue

                    # Check if we have Greeks
                    delta = None
                    if hasattr(ticker, 'modelGreeks') and ticker.modelGreeks:
                        delta = abs(ticker.modelGreeks.delta)  # Make positive for puts
                        print(f"    ✓ Delta: {delta:.3f} (target: {targets.put_delta_min:.2f}-{targets.put_delta_max:.2f})")
                    else:
                        print(f"    ❌ No Greeks available")

                    # Check if delta is in our target range (or if no Greeks, still show the contract)
                    in_delta_range = delta and targets.put_delta_min <= delta <= targets.put_delta_max

                    # For now, let's be more flexible with delta requirements for testing
                    should_include = False
                    if delta and delta >= 0.05:  # At least 5 delta to be meaningful
                        print(f"    ✓ Adding contract with delta {delta:.3f}")
                        should_include = True
                    elif not delta:  # No delta available, but contract exists
                        print(f"    ✓ Adding contract (no delta available)")
                        should_include = True

                    if should_include:
                        exp_date = datetime.strptime(exp, '%Y%m%d')
                        days_to_exp = (exp_date - datetime.now()).days

                        # Calculate premium and cash requirement
                        mid_price = (ticker.bid + ticker.ask) / 2
                        cash_required = strike * 100  # Cash secured put requirement
                        premium_income = mid_price * 100

                        # Validate calculated values
                        import math
                        if math.isnan(mid_price) or math.isnan(premium_income):
                            print(f"    ❌ Invalid pricing calculation")
                            continue

                        recommendations.append({
                            'contract': put_contract,
                            'type': 'CASH_SECURED_PUT',
                            'strike': strike,
                            'expiration': exp,
                            'days_to_exp': days_to_exp,
                            'delta': delta if delta else 0.0,
                            'bid': ticker.bid,
                            'ask': ticker.ask,
                            'mid_price': mid_price,
                            'premium_income': premium_income,
                            'cash_required': cash_required,
                            'description': f"Sell {self.config.symbol} {exp_date.strftime('%m/%d')} ${strike}P"
                        })

                        print(f"    💰 Premium: ${premium_income:.0f}, Cash req: ${cash_required:.0f}")

                except Exception as e:
                    continue  # Skip problematic contracts

                if len(recommendations) >= max_contracts:
                    break

            if len(recommendations) >= max_contracts:
                break

        # Sort by delta (closest to target first)
        target_delta = targets.get_put_target_delta()
        recommendations.sort(key=lambda x: abs(x['delta'] - target_delta))

        return recommendations[:max_contracts]

    def disconnect(self):
        """Disconnect from IB Gateway."""
        if self.ib.isConnected():
            self.ib.disconnect()

# Interactive strategy setup and analysis
async def main():
    """Interactive wheel strategy setup and analysis."""

    strategy = WheelStrategy()

    try:
        # Connect to IB Gateway
        await strategy.connect()

        # Interactive setup
        config = await strategy.setup_strategy()
        if not config:
            print("Setup cancelled.")
            return

        # Analyze current portfolio
        print(f"\n=== Analyzing Current Portfolio ===")
        balance, targets = await strategy.analyze_portfolio()

        # Show recommendations
        print(f"\n=== Strategy Recommendations ===")
        if balance.is_cash_heavy:
            print("📈 CASH HEAVY: Focus on selling cash-secured puts to acquire equity")
            print(f"   Target put delta: ~{targets.get_put_target_delta():.2f}")
            print(f"   This will help move toward the 50/50 target allocation")

            # Get specific put recommendations
            put_recommendations = await strategy.get_put_recommendations(targets)

            if put_recommendations:
                print(f"\n💰 RECOMMENDED CASH-SECURED PUT TRADES:")
                print(f"{'Trade':<25} {'Delta':<8} {'Premium':<10} {'Cash Req':<12} {'Days':<6}")
                print("-" * 70)

                for rec in put_recommendations:
                    print(f"{rec['description']:<25} "
                          f"{rec['delta']:.3f}    "
                          f"${rec['premium_income']:>7.0f}   "
                          f"${rec['cash_required']:>9.0f}   "
                          f"{rec['days_to_exp']:>3}d")

                total_premium = sum(r['premium_income'] for r in put_recommendations)
                total_cash_req = sum(r['cash_required'] for r in put_recommendations)
                print("-" * 70)
                print(f"{'TOTALS:':<25} {'':>8} ${total_premium:>7.0f}   ${total_cash_req:>9.0f}")

            else:
                print("❌ No suitable put options found in target delta range")

        elif balance.is_equity_heavy:
            print("📉 EQUITY HEAVY: Focus on selling covered calls to reduce equity")
            print(f"   Target call delta: ~{targets.get_call_target_delta():.2f}")
            print(f"   This will help move toward the 50/50 target allocation")
            print("   (Covered call selection not yet implemented)")

        else:
            print("⚖️  BALANCED: Maintain current allocation with both puts and calls")
            print(f"   Put delta: ~{targets.get_put_target_delta():.2f}")
            print(f"   Call delta: ~{targets.get_call_target_delta():.2f}")
            print("   (Options selection for balanced portfolio not yet implemented)")

        print(f"\nNext step: Review the recommended trades above and place orders in TWS/IB Gateway.")

    except KeyboardInterrupt:
        print("\nSetup interrupted by user.")
    except Exception as e:
        print(f"Error: {e}")

    finally:
        strategy.disconnect()

if __name__ == "__main__":
    asyncio.run(main())