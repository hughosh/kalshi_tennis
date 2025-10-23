"""
Simple Limit Order Executor for Kalshi

This module implements a straightforward limit order strategy:
1. Place buy order at current market price
2. Immediately place limit sell order at 5-10% profit
3. Let Kalshi handle the execution automatically
"""

import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from simple_kalshi_client import SimpleKalshiClient
from cryptography.hazmat.primitives import serialization
from order_logging.kalshi_order_logger import order_logger

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    """Order side enumeration"""
    YES = "yes"
    NO = "no"


@dataclass
class LimitOrder:
    """Limit order with execution tracking"""
    order_id: str
    position_id: str
    market_ticker: str
    side: OrderSide
    quantity: int
    price_cents: int
    order_type: str  # "market" or "limit"
    status: str
    created_at: datetime
    filled_at: Optional[datetime] = None
    fill_price_cents: Optional[int] = None


class SimpleLimitOrderExecutor:
    """Simple executor that places buy + limit sell orders"""
    
    def __init__(self, 
                 profit_target_pct: float = 0.05,  # 5% default profit target (more conservative)
                 position_size: int = 5,  # 5 shares default
                 environment: str = "prod"):  # "prod" or "demo"
        """
        Initialize the limit order executor.
        
        Args:
            profit_target_pct: Profit target percentage (default 5%)
            position_size: Number of shares per position (default 5)
            environment: Kalshi environment (PROD or DEMO)
        """
        self.profit_target_pct = profit_target_pct
        self.position_size = position_size
        self.environment = environment
        
        # Initialize Kalshi client
        self.kalshi_client = self._create_kalshi_client()
        
        # Track orders
        self.active_orders: Dict[str, LimitOrder] = {}
        self.completed_orders: List[LimitOrder] = []
        
        logger.info(f"SimpleLimitOrderExecutor initialized - Profit target: {profit_target_pct:.1%}, Position size: {position_size}")
    
    def _create_kalshi_client(self) -> Optional[SimpleKalshiClient]:
        """Create Kalshi HTTP client"""
        try:
            # Create the actual SimpleKalshiClient instance
            client = SimpleKalshiClient()
            
            # Check if client has proper credentials
            if not client.private_key or not client.key_id:
                logger.warning("Kalshi client created but missing credentials - trading disabled")
                return None
            
            logger.info("Kalshi client created successfully with credentials")
            return client
            
        except Exception as e:
            logger.error(f"Failed to create Kalshi client: {e}")
            return None
    
    def place_buy_and_limit_sell(self, 
                                market_ticker: str, 
                                current_price: float,
                                position_id: str) -> bool:
        """
        Place buy order and immediate limit sell order using actual Kalshi API.
        
        Args:
            market_ticker: Kalshi market ticker
            current_price: Current market price (0.0 to 1.0) - this is the signal price
            position_id: Unique position identifier
            
        Returns:
            True if orders placed successfully
        """
        if not self.kalshi_client:
            error_msg = "Kalshi client not available"
            logger.error(error_msg)
            order_logger.log_order_error(
                order_id="N/A",
                position_id=position_id,
                error_message=error_msg
            )
            return False
        
        try:
            # Use the signal's market price with a small buffer to ensure fill
            # Add 1-2 cents to ensure the market order fills at current market price
            current_ask_price = min(0.99, current_price + 0.02)  # Add 2% buffer, cap at 99¢
            
            logger.info(f"Using market price with buffer: {current_ask_price:.3f} (original: {current_price:.3f}) for {market_ticker}")
            
            # Convert prices to cents with proper rounding
            buy_price_cents = round(current_ask_price * 100)  # Use price with buffer
            profit_price_cents = round(current_ask_price * (1 + self.profit_target_pct) * 100)
            
            # Ensure prices are within valid range
            buy_price_cents = max(1, min(99, buy_price_cents))
            profit_price_cents = max(1, min(99, profit_price_cents))
            
            logger.info(f"Placing orders for {market_ticker}: Buy at {buy_price_cents}¢ (with buffer), Sell at {profit_price_cents}¢")
            
            # Place buy order (market order for immediate fill)
            buy_order_id = f"buy_{position_id}_{int(datetime.now().timestamp())}"
            
            # Log buy order placement
            order_logger.log_order_placement(
                order_id=buy_order_id,
                position_id=position_id,
                market_ticker=market_ticker,
                player_name="Unknown",  # Will be updated by caller
                direction="BUY_YES",
                price=current_ask_price,
                quantity=self.position_size,
                message=f"Placing market buy order for {market_ticker}"
            )
            
            # Place actual market buy order via Kalshi API (use ask price as max price)
            buy_response = self.kalshi_client.place_order(
                ticker=market_ticker,
                side="yes",
                count=self.position_size,
                price_cents=buy_price_cents,  # Use actual ask price
                order_type="market"
            )
            
            if buy_response and 'order' in buy_response:
                logger.info(f"Buy order placed successfully: {buy_response}")
                order_logger.log_order_response(
                    order_id=buy_order_id,
                    position_id=position_id,
                    status="SUBMITTED",
                    kalshi_response=buy_response,
                    message=f"Buy order {buy_order_id} submitted successfully"
                )
            else:
                logger.error(f"Failed to place buy order for {market_ticker}")
                order_logger.log_order_error(
                    order_id=buy_order_id,
                    position_id=position_id,
                    error_message=f"Failed to place buy order for {market_ticker}",
                    error_details="Kalshi API returned empty response"
                )
                return False
            
            # Place limit sell order
            sell_order_id = f"sell_{position_id}_{int(datetime.now().timestamp())}"
            
            # Log sell order placement
            order_logger.log_order_placement(
                order_id=sell_order_id,
                position_id=position_id,
                market_ticker=market_ticker,
                player_name="Unknown",  # Will be updated by caller
                direction="SELL_YES",
                price=current_ask_price * (1 + self.profit_target_pct),
                quantity=self.position_size,
                message=f"Placing limit sell order for {market_ticker} at {self.profit_target_pct:.1%} profit"
            )
            
            # Place actual limit sell order via Kalshi API
            sell_response = self.kalshi_client.place_order(
                ticker=market_ticker,
                side="yes",
                count=self.position_size,
                price_cents=profit_price_cents,
                order_type="limit"
            )
            
            if sell_response and 'order' in sell_response:
                logger.info(f"Sell order placed successfully: {sell_response}")
                order_logger.log_order_response(
                    order_id=sell_order_id,
                    position_id=position_id,
                    status="SUBMITTED",
                    kalshi_response=sell_response,
                    message=f"Sell order {sell_order_id} submitted successfully"
                )
            else:
                logger.error(f"Failed to place sell order for {market_ticker}")
                order_logger.log_order_error(
                    order_id=sell_order_id,
                    position_id=position_id,
                    error_message=f"Failed to place sell order for {market_ticker}",
                    error_details="Kalshi API returned empty response"
                )
                return False
            
            # Store orders for tracking
            buy_order = LimitOrder(
                order_id=buy_order_id,
                position_id=position_id,
                market_ticker=market_ticker,
                side=OrderSide.YES,
                quantity=self.position_size,
                price_cents=current_price_cents,
                order_type="market",
                status="submitted",
                created_at=datetime.now()
            )
            
            sell_order = LimitOrder(
                order_id=sell_order_id,
                position_id=position_id,
                market_ticker=market_ticker,
                side=OrderSide.YES,
                quantity=self.position_size,
                price_cents=profit_price_cents,
                order_type="limit",
                status="submitted",
                created_at=datetime.now()
            )
            
            self.active_orders[buy_order_id] = buy_order
            self.active_orders[sell_order_id] = sell_order
            
            logger.info(f"Orders placed successfully: {buy_order_id} (buy), {sell_order_id} (sell)")
            return True
            
        except Exception as e:
            error_msg = f"Error placing orders for {market_ticker}: {e}"
            logger.error(error_msg)
            order_logger.log_order_error(
                order_id="N/A",
                position_id=position_id,
                error_message=error_msg,
                error_details=str(e)
            )
            return False
    
    def get_order_status(self, order_id: str) -> Optional[str]:
        """Get status of an order"""
        if order_id in self.active_orders:
            return self.active_orders[order_id].status
        return None
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        if order_id not in self.active_orders:
            logger.warning(f"Order {order_id} not found")
            order_logger.log_order_error(
                order_id=order_id,
                position_id="Unknown",
                error_message=f"Order {order_id} not found for cancellation"
            )
            return False
        
        try:
            # In a real implementation, you'd call the Kalshi API to cancel
            # For now, just mark as cancelled
            self.active_orders[order_id].status = "cancelled"
            
            # Log order cancellation
            order_logger.log_order_cancel(
                order_id=order_id,
                position_id=self.active_orders[order_id].position_id,
                reason="Manual cancellation",
                message=f"Order {order_id} cancelled successfully"
            )
            
            logger.info(f"Order {order_id} cancelled")
            return True
            
        except Exception as e:
            error_msg = f"Error cancelling order {order_id}: {e}"
            logger.error(error_msg)
            order_logger.log_order_error(
                order_id=order_id,
                position_id=self.active_orders.get(order_id, {}).get('position_id', 'Unknown'),
                error_message=error_msg,
                error_details=str(e)
            )
            return False
    
    def get_active_orders(self) -> List[LimitOrder]:
        """Get all active orders"""
        return list(self.active_orders.values())
    
    def get_completed_orders(self) -> List[LimitOrder]:
        """Get all completed orders"""
        return self.completed_orders


def create_simple_executor() -> SimpleLimitOrderExecutor:
    """Create a simple limit order executor"""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Get position size from environment variable
    position_size = int(os.getenv('POSITION_SIZE', '5'))
    
    return SimpleLimitOrderExecutor(position_size=position_size)
