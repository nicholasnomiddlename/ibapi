#!/usr/bin/env python3
"""
Test script to retrieve GLD options chain data from IB Gateway.
This will help us understand the available strikes, expirations, and Greeks
needed for the wheel trading strategy.
"""

import asyncio
from datetime import datetime, timedelta
from ib_insync import *

async def test_options_chain():
    """Test retrieving options chain for GLD."""

    # Create IB connection
    ib = IB()

    try:
        # Connect to IB Gateway (paper trading port 4002)
        print("Connecting to IB Gateway...")
        await ib.connectAsync('127.0.0.1', 4002, clientId=2)
        print("✓ Connected successfully!")

        # Create GLD stock contract
        gld_stock = Stock('GLD', 'ARCA', 'USD')

        # Qualify the contract to get the contract ID
        print("\nQualifying GLD contract...")
        qualified_contracts = await ib.qualifyContractsAsync(gld_stock)
        if not qualified_contracts:
            print("✗ Could not qualify GLD contract")
            return

        gld_stock = qualified_contracts[0]
        print(f"✓ Qualified contract ID: {gld_stock.conId}")

        # Get current stock price first
        print("\nGetting GLD stock price...")
        ib.reqMktData(gld_stock, '', False, False)
        await asyncio.sleep(2)
        ticker = ib.ticker(gld_stock)
        current_price = ticker.last
        print(f"GLD Current Price: ${current_price}")

        # Request options chain
        print("\nRequesting options chain...")
        chains = await ib.reqSecDefOptParamsAsync(gld_stock.symbol, '', gld_stock.secType, gld_stock.conId)

        if not chains:
            print("✗ No options chains found")
            return

        print(f"✓ Found {len(chains)} options chains")

        # Look at the first chain (usually the main one)
        chain = chains[0]
        print(f"\nExchange: {chain.exchange}")
        print(f"Trading Class: {chain.tradingClass}")
        print(f"Multiplier: {chain.multiplier}")

        # Get available expirations (next 5 weeks for our wheel strategy)
        expirations = sorted(chain.expirations)[:10]  # First 10 expirations
        print(f"\nNext 10 expirations:")
        for i, exp in enumerate(expirations):
            exp_date = datetime.strptime(exp, '%Y%m%d')
            days_out = (exp_date - datetime.now()).days
            print(f"  {i+1}. {exp} ({exp_date.strftime('%Y-%m-%d')}) - {days_out} days out")

        # Get strikes around current price
        strikes = sorted([float(s) for s in chain.strikes])

        # Find strikes within +/- $10 of current price
        relevant_strikes = [s for s in strikes if abs(s - current_price) <= 10]
        print(f"\nStrikes within $10 of current price (${current_price}):")
        for strike in relevant_strikes[:15]:  # Show first 15
            print(f"  ${strike}")

        # Test getting specific option contracts
        print(f"\nTesting specific option contract requests...")

        # Try to get puts and calls for the nearest expiration
        if expirations and relevant_strikes:
            nearest_exp = expirations[0]
            test_strike = min(relevant_strikes, key=lambda x: abs(x - current_price))

            # Create put and call contracts
            put_contract = Option('GLD', nearest_exp, test_strike, 'P', 'SMART')
            call_contract = Option('GLD', nearest_exp, test_strike, 'C', 'SMART')

            print(f"\nTesting strike ${test_strike} expiring {nearest_exp}:")

            # Request market data for put
            try:
                ib.reqMktData(put_contract, '', False, False)
                await asyncio.sleep(2)
                put_ticker = ib.ticker(put_contract)

                print(f"PUT:")
                print(f"  Bid: ${put_ticker.bid}")
                print(f"  Ask: ${put_ticker.ask}")
                print(f"  Last: ${put_ticker.last}")

                # Get Greeks if available
                if hasattr(put_ticker, 'modelGreeks') and put_ticker.modelGreeks:
                    greeks = put_ticker.modelGreeks
                    print(f"  Delta: {greeks.delta:.4f}")
                    print(f"  Gamma: {greeks.gamma:.4f}")
                    print(f"  Theta: {greeks.theta:.4f}")
                    print(f"  Vega: {greeks.vega:.4f}")

            except Exception as e:
                print(f"  Error getting put data: {e}")

            # Request market data for call
            try:
                ib.reqMktData(call_contract, '', False, False)
                await asyncio.sleep(2)
                call_ticker = ib.ticker(call_contract)

                print(f"CALL:")
                print(f"  Bid: ${call_ticker.bid}")
                print(f"  Ask: ${call_ticker.ask}")
                print(f"  Last: ${call_ticker.last}")

                # Get Greeks if available
                if hasattr(call_ticker, 'modelGreeks') and call_ticker.modelGreeks:
                    greeks = call_ticker.modelGreeks
                    print(f"  Delta: {greeks.delta:.4f}")
                    print(f"  Gamma: {greeks.gamma:.4f}")
                    print(f"  Theta: {greeks.theta:.4f}")
                    print(f"  Vega: {greeks.vega:.4f}")

            except Exception as e:
                print(f"  Error getting call data: {e}")

    except Exception as e:
        print(f"✗ Error: {e}")
        print("Make sure IB Gateway is running on port 4002 (paper trading)")

    finally:
        # Disconnect
        if ib.isConnected():
            ib.disconnect()
            print("\nDisconnected from IB Gateway")

if __name__ == "__main__":
    asyncio.run(test_options_chain())