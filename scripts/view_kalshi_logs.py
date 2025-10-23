#!/usr/bin/env python3
"""
Kalshi Order Log Viewer

This script provides a simple interface to view recent Kalshi order logs
and analyze order placement and execution.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

sys.path.append(str(Path(__file__).parent.parent))
from order_logging.kalshi_order_logger import KalshiOrderLogger


def format_timestamp(timestamp_str: str) -> str:
    """Format timestamp for display"""
    try:
        dt = datetime.fromisoformat(timestamp_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return timestamp_str


def print_order_entry(entry: Dict[str, Any]) -> None:
    """Print a formatted order log entry"""
    timestamp = format_timestamp(entry.get('timestamp', 'Unknown'))
    level = entry.get('level', 'INFO')
    operation = entry.get('operation', 'Unknown')
    message = entry.get('message', 'No message')
    
    # Color coding based on level
    color_codes = {
        'SUCCESS': '\033[92m',  # Green
        'ERROR': '\033[91m',    # Red
        'WARNING': '\033[93m',  # Yellow
        'INFO': '\033[94m'      # Blue
    }
    reset_code = '\033[0m'
    
    color = color_codes.get(level, '')
    
    print(f"{color}[{timestamp}] {level}{reset_code}")
    print(f"  Operation: {operation}")
    print(f"  Message: {message}")
    
    # Show additional details if available
    if entry.get('order_id'):
        print(f"  Order ID: {entry['order_id']}")
    if entry.get('position_id'):
        print(f"  Position ID: {entry['position_id']}")
    if entry.get('player_name'):
        print(f"  Player: {entry['player_name']}")
    if entry.get('direction'):
        print(f"  Direction: {entry['direction']}")
    if entry.get('price') is not None:
        print(f"  Price: {entry['price']:.3f}")
    if entry.get('quantity'):
        print(f"  Quantity: {entry['quantity']}")
    if entry.get('status'):
        print(f"  Status: {entry['status']}")
    if entry.get('error_details'):
        print(f"  Error Details: {entry['error_details']}")
    
    # Show Kalshi response if available
    if entry.get('kalshi_response'):
        print(f"  Kalshi Response: {json.dumps(entry['kalshi_response'], indent=4)}")
    
    print()


def show_recent_orders(limit: int = 50) -> None:
    """Show recent order log entries"""
    logger = KalshiOrderLogger()
    entries = logger.get_recent_orders(limit)
    
    if not entries:
        print("No order log entries found.")
        return
    
    print(f"📊 Recent Kalshi Order Logs ({len(entries)} entries)")
    print("=" * 60)
    
    for entry in entries:
        print_order_entry(entry)


def show_orders_by_position(position_id: str) -> None:
    """Show all order log entries for a specific position"""
    logger = KalshiOrderLogger()
    entries = logger.get_orders_by_position(position_id)
    
    if not entries:
        print(f"No order log entries found for position {position_id}")
        return
    
    print(f"📊 Order Logs for Position: {position_id}")
    print("=" * 60)
    
    for entry in entries:
        print_order_entry(entry)


def show_order_summary() -> None:
    """Show a summary of order operations"""
    logger = KalshiOrderLogger()
    entries = logger.get_recent_orders(1000)  # Get more entries for summary
    
    if not entries:
        print("No order log entries found.")
        return
    
    # Count operations
    operation_counts = {}
    error_count = 0
    success_count = 0
    
    for entry in entries:
        operation = entry.get('operation', 'Unknown')
        level = entry.get('level', 'INFO')
        
        operation_counts[operation] = operation_counts.get(operation, 0) + 1
        
        if level == 'ERROR':
            error_count += 1
        elif level == 'SUCCESS':
            success_count += 1
    
    print("📊 Order Log Summary")
    print("=" * 40)
    print(f"Total Entries: {len(entries)}")
    print(f"Success Operations: {success_count}")
    print(f"Error Operations: {error_count}")
    print()
    print("Operation Breakdown:")
    for operation, count in sorted(operation_counts.items()):
        print(f"  {operation}: {count}")


def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python view_kalshi_logs.py recent [limit]")
        print("  python view_kalshi_logs.py position <position_id>")
        print("  python view_kalshi_logs.py summary")
        return
    
    command = sys.argv[1].lower()
    
    if command == "recent":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        show_recent_orders(limit)
    elif command == "position":
        if len(sys.argv) < 3:
            print("Please provide a position ID")
            return
        position_id = sys.argv[2]
        show_orders_by_position(position_id)
    elif command == "summary":
        show_order_summary()
    else:
        print(f"Unknown command: {command}")
        print("Available commands: recent, position, summary")


if __name__ == "__main__":
    main()
