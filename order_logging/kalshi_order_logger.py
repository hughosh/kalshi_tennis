"""
Kalshi Order Logging System

This module provides comprehensive logging for all Kalshi order operations,
including order placement, responses, fills, and cancellations.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import os

logger = logging.getLogger(__name__)


class OrderLogLevel:
    """Log levels for order operations"""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"


@dataclass
class OrderLogEntry:
    """Represents a single order log entry"""
    timestamp: str
    level: str
    operation: str  # "PLACE_ORDER", "ORDER_RESPONSE", "ORDER_FILL", "ORDER_CANCEL", etc.
    order_id: Optional[str] = None
    position_id: Optional[str] = None
    market_ticker: Optional[str] = None
    player_name: Optional[str] = None
    direction: Optional[str] = None  # "BUY_YES", "SELL_YES", etc.
    price: Optional[float] = None
    quantity: Optional[int] = None
    status: Optional[str] = None  # "PENDING", "FILLED", "CANCELLED", etc.
    message: Optional[str] = None
    kalshi_response: Optional[Dict[str, Any]] = None
    error_details: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


class KalshiOrderLogger:
    """
    Comprehensive logging system for Kalshi order operations.
    
    Logs all order-related activities to both console and file.
    """
    
    def __init__(self, log_file_path: str = "kalshi_orders.log"):
        """
        Initialize the order logger.
        
        Args:
            log_file_path: Path to the log file
        """
        self.log_file_path = Path(log_file_path)
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Setup file handler
        self.file_handler = logging.FileHandler(self.log_file_path)
        self.file_handler.setLevel(logging.INFO)
        
        # Setup formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        self.file_handler.setFormatter(formatter)
        
        # Add handler to logger
        logger.addHandler(self.file_handler)
        
        logger.info("Kalshi Order Logger initialized")
    
    def log_order_placement(self, 
                           order_id: str,
                           position_id: str,
                           market_ticker: str,
                           player_name: str,
                           direction: str,
                           price: float,
                           quantity: int,
                           message: str = None) -> None:
        """Log order placement attempt"""
        entry = OrderLogEntry(
            timestamp=datetime.now().isoformat(),
            level=OrderLogLevel.INFO,
            operation="PLACE_ORDER",
            order_id=order_id,
            position_id=position_id,
            market_ticker=market_ticker,
            player_name=player_name,
            direction=direction,
            price=price,
            quantity=quantity,
            message=message or f"Placing {direction} order for {player_name}"
        )
        
        self._write_log_entry(entry)
        logger.info(f"ORDER_PLACEMENT: {direction} {quantity} shares of {player_name} at {price:.3f} (Order: {order_id})")
    
    def log_order_response(self,
                          order_id: str,
                          position_id: str,
                          status: str,
                          kalshi_response: Dict[str, Any],
                          message: str = None) -> None:
        """Log Kalshi API response to order placement"""
        level = OrderLogLevel.SUCCESS if status in ["FILLED", "PENDING"] else OrderLogLevel.WARNING
        
        entry = OrderLogEntry(
            timestamp=datetime.now().isoformat(),
            level=level,
            operation="ORDER_RESPONSE",
            order_id=order_id,
            position_id=position_id,
            status=status,
            kalshi_response=kalshi_response,
            message=message or f"Order {order_id} received status: {status}"
        )
        
        self._write_log_entry(entry)
        logger.info(f"ORDER_RESPONSE: Order {order_id} status: {status}")
        
        if kalshi_response:
            logger.debug(f"Kalshi Response: {json.dumps(kalshi_response, indent=2)}")
    
    def log_order_fill(self,
                      order_id: str,
                      position_id: str,
                      fill_price: float,
                      fill_quantity: int,
                      message: str = None) -> None:
        """Log order fill"""
        entry = OrderLogEntry(
            timestamp=datetime.now().isoformat(),
            level=OrderLogLevel.SUCCESS,
            operation="ORDER_FILL",
            order_id=order_id,
            position_id=position_id,
            price=fill_price,
            quantity=fill_quantity,
            status="FILLED",
            message=message or f"Order {order_id} filled at {fill_price:.3f}"
        )
        
        self._write_log_entry(entry)
        logger.info(f"ORDER_FILL: Order {order_id} filled {fill_quantity} shares at {fill_price:.3f}")
    
    def log_order_cancel(self,
                        order_id: str,
                        position_id: str,
                        reason: str,
                        message: str = None) -> None:
        """Log order cancellation"""
        entry = OrderLogEntry(
            timestamp=datetime.now().isoformat(),
            level=OrderLogLevel.WARNING,
            operation="ORDER_CANCEL",
            order_id=order_id,
            position_id=position_id,
            status="CANCELLED",
            message=message or f"Order {order_id} cancelled: {reason}"
        )
        
        self._write_log_entry(entry)
        logger.warning(f"ORDER_CANCEL: Order {order_id} cancelled - {reason}")
    
    def log_order_error(self,
                       order_id: str,
                       position_id: str,
                       error_message: str,
                       error_details: str = None,
                       kalshi_response: Dict[str, Any] = None) -> None:
        """Log order error"""
        entry = OrderLogEntry(
            timestamp=datetime.now().isoformat(),
            level=OrderLogLevel.ERROR,
            operation="ORDER_ERROR",
            order_id=order_id,
            position_id=position_id,
            message=error_message,
            error_details=error_details,
            kalshi_response=kalshi_response
        )
        
        self._write_log_entry(entry)
        logger.error(f"ORDER_ERROR: Order {order_id} failed - {error_message}")
        
        if error_details:
            logger.error(f"Error Details: {error_details}")
        
        if kalshi_response:
            logger.error(f"Kalshi Error Response: {json.dumps(kalshi_response, indent=2)}")
    
    def log_position_update(self,
                           position_id: str,
                           player_name: str,
                           current_price: float,
                           pnl_pct: float,
                           pnl_absolute: float,
                           message: str = None) -> None:
        """Log position price update"""
        entry = OrderLogEntry(
            timestamp=datetime.now().isoformat(),
            level=OrderLogLevel.INFO,
            operation="POSITION_UPDATE",
            position_id=position_id,
            player_name=player_name,
            price=current_price,
            message=message or f"Position {position_id} updated: {pnl_pct:.2%} P&L"
        )
        
        self._write_log_entry(entry)
        logger.info(f"POSITION_UPDATE: {player_name} - Price: {current_price:.3f}, P&L: {pnl_pct:.2%} ({pnl_absolute:.2f})")
    
    def log_position_close(self,
                          position_id: str,
                          player_name: str,
                          exit_price: float,
                          exit_reason: str,
                          final_pnl_pct: float,
                          final_pnl_absolute: float,
                          message: str = None) -> None:
        """Log position closure"""
        level = OrderLogLevel.SUCCESS if final_pnl_pct > 0 else OrderLogLevel.WARNING
        
        entry = OrderLogEntry(
            timestamp=datetime.now().isoformat(),
            level=level,
            operation="POSITION_CLOSE",
            position_id=position_id,
            player_name=player_name,
            price=exit_price,
            message=message or f"Position {position_id} closed: {exit_reason}"
        )
        
        self._write_log_entry(entry)
        logger.info(f"POSITION_CLOSE: {player_name} - Exit: {exit_price:.3f}, Final P&L: {final_pnl_pct:.2%} ({final_pnl_absolute:.2f}) - {exit_reason}")
    
    def log_portfolio_update(self,
                           balance_dollars: float,
                           available_cash_dollars: float,
                           position_count: int,
                           total_exposure_dollars: float) -> None:
        """Log portfolio balance update"""
        entry = OrderLogEntry(
            timestamp=datetime.now().isoformat(),
            level=OrderLogLevel.INFO,
            operation="PORTFOLIO_UPDATE",
            message=f"Portfolio updated - Balance: ${balance_dollars:.2f}, Available: ${available_cash_dollars:.2f}, Positions: {position_count}, Exposure: ${total_exposure_dollars:.2f}"
        )
        
        self._write_log_entry(entry)
        logger.info(f"PORTFOLIO_UPDATE: Balance: ${balance_dollars:.2f}, Available: ${available_cash_dollars:.2f}, Positions: {position_count}, Exposure: ${total_exposure_dollars:.2f}")
    
    def log_api_call(self,
                     endpoint: str,
                     method: str,
                     request_data: Dict[str, Any] = None,
                     response_data: Dict[str, Any] = None,
                     status_code: int = None,
                     error: str = None) -> None:
        """Log Kalshi API calls"""
        level = OrderLogLevel.ERROR if error else OrderLogLevel.INFO
        
        entry = OrderLogEntry(
            timestamp=datetime.now().isoformat(),
            level=level,
            operation="API_CALL",
            message=f"{method} {endpoint}",
            kalshi_response=response_data,
            error_details=error
        )
        
        self._write_log_entry(entry)
        
        if error:
            logger.error(f"API_ERROR: {method} {endpoint} - {error}")
        else:
            logger.info(f"API_CALL: {method} {endpoint} - Status: {status_code}")
    
    def _write_log_entry(self, entry: OrderLogEntry) -> None:
        """Write log entry to file"""
        try:
            with open(self.log_file_path, 'a') as f:
                f.write(json.dumps(entry.to_dict()) + '\n')
        except Exception as e:
            logger.error(f"Failed to write log entry: {e}")
    
    def get_recent_orders(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent order log entries"""
        try:
            entries = []
            with open(self.log_file_path, 'r') as f:
                lines = f.readlines()
                for line in lines[-limit:]:
                    try:
                        entry = json.loads(line.strip())
                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue
            return entries
        except FileNotFoundError:
            return []
        except Exception as e:
            logger.error(f"Failed to read log entries: {e}")
            return []
    
    def get_orders_by_position(self, position_id: str) -> List[Dict[str, Any]]:
        """Get all log entries for a specific position"""
        try:
            entries = []
            with open(self.log_file_path, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if entry.get('position_id') == position_id:
                            entries.append(entry)
                    except json.JSONDecodeError:
                        continue
            return entries
        except FileNotFoundError:
            return []
        except Exception as e:
            logger.error(f"Failed to read log entries for position {position_id}: {e}")
            return []


# Global logger instance
order_logger = KalshiOrderLogger()
