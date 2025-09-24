#!/usr/bin/env python3
"""
Test script to connect to IB Gateway and retrieve GLD market price.
"""

import asyncio
from ib_insync import *

async def test_connection():
    """Test connection to IB Gateway and get GLD price."""

    # Create IB connection
    ib = IB()

    try:
        # Connect to IB Gateway (paper trading port 4002)
        print("Connecting to IB Gateway...")
        await ib.connectAsync('127.0.0.1', 4002, clientId=1)
        print("✓ Connected successfully!")

        # Create GLD contract
        gld_contract = Stock('GLD', 'ARCA', 'USD')

        # Request market data
        print("Requesting GLD market data...")
        ib.reqMktData(gld_contract, '', False, False)

        # Wait a moment for data to arrive
        await asyncio.sleep(2)

        # Get the ticker data
        ticker = ib.ticker(gld_contract)

        if ticker.last and ticker.last > 0:
            print(f"✓ GLD Last Price: ${ticker.last}")
            print(f"  Bid: ${ticker.bid}")
            print(f"  Ask: ${ticker.ask}")
            print(f"  Volume: {ticker.volume}")
        else:
            print("⚠ No price data received - market may be closed")

        # Get account summary
        print("\nAccount information:")
        account_summary = ib.accountSummary()
        for item in account_summary:
            if item.tag in ['TotalCashValue', 'NetLiquidation', 'BuyingPower']:
                print(f"  {item.tag}: {item.value} {item.currency}")

    except Exception as e:
        print(f"✗ Connection failed: {e}")
        print("Make sure IB Gateway is running on port 4002 (paper trading)")

    finally:
        # Disconnect
        if ib.isConnected():
            ib.disconnect()
            print("Disconnected from IB Gateway")

if __name__ == "__main__":
    # Run the async function
    asyncio.run(test_connection())