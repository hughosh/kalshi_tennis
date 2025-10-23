"""
Improved Order Executor - Buy First, Sell Only If Filled
"""
import os
import logging
from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass

from simple_kalshi_client import SimpleKalshiClient
from order_logging.kalshi_order_logger import order_logger
from trading.portfolio_manager import PortfolioManager

logger = logging.getLogger(__name__)

@dataclass
class Order:
    """Simple order tracking"""
    order_id: str
    position_id: str
    ticker: str
    side: str
    count: int
    price_cents: int
    order_type: str
    status: str
    created_at: datetime
    kalshi_order_id: Optional[str] = None

class ImprovedOrderExecutor:
    """Improved executor that places buy orders first, then sell orders only if buy fills"""
    
    def __init__(self, 
                 profit_target_pct: float = 0.05,  # 5% default profit target
                 position_size: int = 10,  # 10 shares default
                 fill_timeout_seconds: int = 30):  # Cancel buy orders after 30 seconds if not filled
        """
        Initialize the improved order executor.
        
        Args:
            profit_target_pct: Profit target percentage (default 5%)
            position_size: Number of shares per position (default 10)
            fill_timeout_seconds: Timeout for buy order fills before cancellation
        """
        self.profit_target_pct = profit_target_pct
        self.position_size = position_size
        self.fill_timeout_seconds = fill_timeout_seconds
        
        # Initialize Kalshi client
        self.kalshi_client = self._create_kalshi_client()
        
        # Initialize portfolio manager for cash management
        self.portfolio_manager = PortfolioManager(self.kalshi_client)
        
        # Track orders
        self.active_orders: Dict[str, Order] = {}
        self.completed_orders: List[Order] = []
        
        logger.info(f"ImprovedOrderExecutor initialized - Profit target: {profit_target_pct:.1%}, Position size: {position_size}")
    
    def _create_kalshi_client(self) -> Optional[SimpleKalshiClient]:
        """Create Kalshi client with proper credentials"""
        try:
            key_id = os.getenv('KALSHI_KEY_ID')
            private_key_file = os.getenv('KALSHI_PRIVATE_KEY_FILE')
            
            if not key_id or not private_key_file:
                logger.error("Missing Kalshi credentials in environment variables")
                return None
            
            client = SimpleKalshiClient()
            logger.info("Kalshi client created successfully with credentials")
            return client
            
        except Exception as e:
            logger.error(f"Failed to create Kalshi client: {e}")
            return None
    
    def place_buy_order(self, 
                       market_ticker: str, 
                       current_price: float,
                       position_id: str) -> bool:
        """
        Place buy order first. Sell order will be placed later if buy fills.
        
        Args:
            market_ticker: Kalshi market ticker
            current_price: Current market price (0.0 to 1.0)
            position_id: Unique position identifier
            
        Returns:
            True if buy order placed successfully
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
            # Update portfolio data first
            if not self.portfolio_manager.update_portfolio_data():
                logger.warning("Failed to update portfolio data, proceeding with order")
            
            # Calculate appropriate position size based on available cash
            recommended_shares = self.portfolio_manager.calculate_position_size(current_price, self.position_size)
            
            if recommended_shares == 0:
                error_msg = "Insufficient cash for position"
                logger.error(error_msg)
                order_logger.log_order_error(
                    order_id="N/A",
                    position_id=position_id,
                    error_message=error_msg
                )
                return False
            
            # Use market price with small buffer to ensure fill
            current_ask_price = min(0.99, current_price + 0.02)  # Add 2% buffer
            buy_price_cents = round(current_ask_price * 100)
            buy_price_cents = max(1, min(99, buy_price_cents))
            
            # Check if we can place the order
            order_value = recommended_shares * current_ask_price
            can_place, reason = self.portfolio_manager.can_place_order(order_value)
            
            if not can_place:
                logger.error(f"Cannot place order: {reason}")
                order_logger.log_order_error(
                    order_id="N/A",
                    position_id=position_id,
                    error_message=f"Cannot place order: {reason}"
                )
                return False
            
            logger.info(f"Placing buy order for {market_ticker}: {recommended_shares} shares @ {buy_price_cents}¢ (original: {current_price:.3f})")
            
            # Place buy order
            buy_order_id = f"buy_{position_id}_{int(datetime.now().timestamp())}"
            
            # Log buy order placement
            order_logger.log_order_placement(
                order_id=buy_order_id,
                position_id=position_id,
                market_ticker=market_ticker,
                player_name="Unknown",
                direction="BUY_YES",
                price=current_ask_price,
                quantity=recommended_shares,
                message=f"Placing buy order for {market_ticker}"
            )
            
            # Place actual buy order via Kalshi API
            buy_response = self.kalshi_client.place_order(
                ticker=market_ticker,
                side="yes",
                count=recommended_shares,
                price_cents=buy_price_cents,
                order_type="market"
            )
            
            if buy_response and 'order' in buy_response:
                kalshi_order_id = buy_response['order'].get('order_id')
                logger.info(f"Buy order placed successfully: {kalshi_order_id}")
                
                order_logger.log_order_response(
                    order_id=buy_order_id,
                    position_id=position_id,
                    status="SUBMITTED",
                    kalshi_response=buy_response,
                    message=f"Buy order {buy_order_id} submitted successfully"
                )
                
                # Store order for tracking
                order = Order(
                    order_id=buy_order_id,
                    position_id=position_id,
                    ticker=market_ticker,
                    side="yes",
                    count=recommended_shares,
                    price_cents=buy_price_cents,
                    order_type="market",
                    status="submitted",
                    created_at=datetime.now(),
                    kalshi_order_id=kalshi_order_id
                )
                
                self.active_orders[buy_order_id] = order
                
                # Check if order filled immediately
                if kalshi_order_id:
                    immediate_status = self._get_order_status(kalshi_order_id)
                    if immediate_status == "filled":
                        logger.info(f"Buy order {buy_order_id} filled immediately! Placing sell order...")
                        self._place_sell_order(order)
                        # Remove from active orders since it's completed
                        del self.active_orders[buy_order_id]
                        self.completed_orders.append(order)
                
                logger.info(f"Buy order placed for {market_ticker}. Will check fill status and place sell order if filled.")
                return True
            else:
                logger.error(f"Failed to place buy order for {market_ticker}")
                order_logger.log_order_error(
                    order_id=buy_order_id,
                    position_id=position_id,
                    error_message=f"Failed to place buy order for {market_ticker}",
                    error_details="Kalshi API returned empty response"
                )
                return False
            
        except Exception as e:
            logger.error(f"Error placing buy order for {market_ticker}: {e}")
            order_logger.log_order_error(
                order_id="N/A",
                position_id=position_id,
                error_message=f"Failed to place buy order for position {position_id}",
                error_details=str(e)
            )
            return False
    
    def check_and_manage_orders(self) -> None:
        """Check order status and manage fills/cancellations"""
        if not self.kalshi_client:
            return
        
        orders_to_remove = []
        
        for order_id, order in self.active_orders.items():
            try:
                # Check if order is too old and should be cancelled
                age_seconds = (datetime.now() - order.created_at).total_seconds()
                
                if age_seconds > self.fill_timeout_seconds and order.status == "submitted":
                    logger.info(f"Cancelling old buy order {order_id} (age: {age_seconds:.1f}s)")
                    self._cancel_order(order)
                    orders_to_remove.append(order_id)
                    continue
                
                # Check order status via Kalshi API
                if order.kalshi_order_id:
                    order_status = self._get_order_status(order.kalshi_order_id)
                    
                    if order_status == "filled":
                        logger.info(f"Buy order {order_id} filled! Placing sell order...")
                        self._place_sell_order(order)
                        orders_to_remove.append(order_id)
                    elif order_status == "canceled":
                        logger.info(f"Order {order_id} was cancelled")
                        orders_to_remove.append(order_id)
                    elif order_status == "rejected":
                        logger.warning(f"Order {order_id} was rejected")
                        orders_to_remove.append(order_id)
                    elif order_status == "submitted":
                        # Order is still pending, check if it's too old
                        if age_seconds > self.fill_timeout_seconds:
                            logger.info(f"Cancelling old buy order {order_id} (age: {age_seconds:.1f}s)")
                            self._cancel_order(order)
                            orders_to_remove.append(order_id)
                
            except Exception as e:
                logger.error(f"Error checking order {order_id}: {e}")
        
        # Remove processed orders
        for order_id in orders_to_remove:
            if order_id in self.active_orders:
                self.completed_orders.append(self.active_orders[order_id])
                del self.active_orders[order_id]
    
    def _get_order_status(self, kalshi_order_id: str) -> Optional[str]:
        """Get order status from Kalshi API"""
        try:
            if not self.kalshi_client:
                return None
            
            # Get order details from Kalshi API
            response = self.kalshi_client._make_request('GET', f'/trade-api/v2/portfolio/orders/{kalshi_order_id}')
            
            if response and 'order' in response:
                order_data = response['order']
                status = order_data.get('status', 'unknown')
                
                # Map Kalshi statuses to our internal statuses
                if status == 'executed':
                    return 'filled'
                elif status == 'canceled':
                    return 'canceled'
                elif status == 'rejected':
                    return 'rejected'
                elif status in ['resting', 'submitted']:
                    return 'submitted'
                else:
                    return status
                    
            return None
        except Exception as e:
            logger.error(f"Error getting order status for {kalshi_order_id}: {e}")
            return None
    
    def _cancel_order(self, order: Order) -> None:
        """Cancel an order"""
        try:
            if order.kalshi_order_id and self.kalshi_client:
                logger.info(f"Cancelling order {order.kalshi_order_id}")
                
                # Cancel order via Kalshi API
                response = self.kalshi_client._make_request('POST', f'/trade-api/v2/portfolio/orders/{order.kalshi_order_id}/cancel')
                
                if response:
                    logger.info(f"Order {order.kalshi_order_id} cancelled successfully")
                else:
                    logger.warning(f"Failed to cancel order {order.kalshi_order_id}")
                
                order_logger.log_order_error(
                    order_id=order.order_id,
                    position_id=order.position_id,
                    error_message=f"Order cancelled due to timeout",
                    error_details=f"Order {order.kalshi_order_id} cancelled after {self.fill_timeout_seconds}s"
                )
        except Exception as e:
            logger.error(f"Error cancelling order {order.order_id}: {e}")
    
    def _place_sell_order(self, buy_order: Order) -> None:
        """Place sell order after buy order fills"""
        try:
            # Calculate sell price
            sell_price_cents = round(buy_order.price_cents * (1 + self.profit_target_pct))
            sell_price_cents = max(1, min(99, sell_price_cents))
            
            logger.info(f"Placing sell order for {buy_order.ticker}: {sell_price_cents}¢ (profit target: {self.profit_target_pct:.1%})")
            
            sell_order_id = f"sell_{buy_order.position_id}_{int(datetime.now().timestamp())}"
            
            # Log sell order placement
            order_logger.log_order_placement(
                order_id=sell_order_id,
                position_id=buy_order.position_id,
                market_ticker=buy_order.ticker,
                player_name="Unknown",
                direction="SELL_YES",
                price=sell_price_cents / 100.0,
                quantity=self.position_size,
                message=f"Placing sell order for {buy_order.ticker} at {self.profit_target_pct:.1%} profit"
            )
            
            # Place actual sell order via Kalshi API
            sell_response = self.kalshi_client.place_order(
                ticker=buy_order.ticker,
                side="yes",
                count=self.position_size,
                price_cents=sell_price_cents,
                order_type="limit"
            )
            
            if sell_response and 'order' in sell_response:
                kalshi_order_id = sell_response['order'].get('order_id')
                logger.info(f"Sell order placed successfully: {kalshi_order_id}")
                
                order_logger.log_order_response(
                    order_id=sell_order_id,
                    position_id=buy_order.position_id,
                    status="SUBMITTED",
                    kalshi_response=sell_response,
                    message=f"Sell order {sell_order_id} submitted successfully"
                )
                
                # Store sell order for tracking
                sell_order = Order(
                    order_id=sell_order_id,
                    position_id=buy_order.position_id,
                    ticker=buy_order.ticker,
                    side="yes",
                    count=self.position_size,
                    price_cents=sell_price_cents,
                    order_type="limit",
                    status="submitted",
                    created_at=datetime.now(),
                    kalshi_order_id=kalshi_order_id
                )
                
                self.active_orders[sell_order_id] = sell_order
                
            else:
                logger.error(f"Failed to place sell order for {buy_order.ticker}")
                order_logger.log_order_error(
                    order_id=sell_order_id,
                    position_id=buy_order.position_id,
                    error_message=f"Failed to place sell order for {buy_order.ticker}",
                    error_details="Kalshi API returned empty response"
                )
        
        except Exception as e:
            logger.error(f"Error placing sell order for {buy_order.ticker}: {e}")
            order_logger.log_order_error(
                order_id="N/A",
                position_id=buy_order.position_id,
                error_message=f"Failed to place sell order for position {buy_order.position_id}",
                error_details=str(e)
            )

def create_improved_executor() -> ImprovedOrderExecutor:
    """Create improved order executor with environment configuration"""
    profit_target = float(os.getenv('PROFIT_TARGET_PERCENT', '5.0')) / 100.0
    position_size = int(os.getenv('POSITION_SIZE', '10'))
    
    return ImprovedOrderExecutor(
        profit_target_pct=profit_target,
        position_size=position_size,
        fill_timeout_seconds=30
    )
