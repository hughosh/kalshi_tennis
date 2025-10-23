#!/usr/bin/env python3
"""
Simple script to run the live signals generator with configurable settings.
"""

import sys
import os
import asyncio

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.updated_live_signals import UpdatedLiveSignalGenerator

def main():
    """Run the live signals generator"""
    print("🚀 LIVE TENNIS TRADING SIGNAL GENERATOR")
    print("=" * 70)
    print("This uses API-Tennis.com for live tennis data")
    print("NO TRADES WILL BE EXECUTED - signals only!")
    print("=" * 70)
    
    # Get user input for interval time
    try:
        print("\nEnter check interval in seconds (default: 30):")
        interval_input = input().strip()
        if interval_input:
            interval = int(interval_input)
            if interval < 5:
                print("Warning: Interval less than 5 seconds may cause rate limiting issues")
        else:
            interval = 30
    except KeyboardInterrupt:
        print("\nExiting...")
        return
    except ValueError:
        print("Invalid input, using default interval of 30 seconds")
        interval = 30
    
    output_file = "api_live_trading_signals.txt"
    
    print(f"\nStarting live monitoring:")
    print(f"  Mode: Indefinite (press Ctrl+C to stop)")
    print(f"  Check interval: {interval} seconds")
    print(f"  Output file: {output_file}")
    print(f"  Data source: API-Tennis.com")
    print(f"  NO TRADES WILL BE EXECUTED")
    print(f"\nPress Ctrl+C to stop monitoring at any time...")
    
    # Create and run signal generator
    generator = UpdatedLiveSignalGenerator(output_file)
    
    try:
        asyncio.run(generator.run_live_monitoring(interval, run_indefinitely=True))
    except KeyboardInterrupt:
        print("\nMonitoring interrupted by user")
        generator.write_final_summary()
    except Exception as e:
        print(f"Error during monitoring: {e}")
        generator.write_final_summary()

if __name__ == "__main__":
    main()
