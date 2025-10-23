"""
Order Execution with Lifecycle Management

This module implements proper order execution with full lifecycle management,
including order tracking, fills, cancellations, and error handling.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import logging
import time
import uuid
from trading.multi_stage_trading import Position, TradeDirection, OrderStatus

logger = logging.getLogger(__name__)


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Order:
    """Order with full lifecycle tracking"""
    order_id: str
    position_id: str
    match_id: str
    player: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: Optional[float] = None  # None for market orders
    stop_price: Optional[float] = None  # For stop orders
    
    # Lifecycle tracking
    status: OrderStatus = OrderStatus.PENDING
    created_time: datetime = field(default_factory=datetime.now)
    submitted_time: Optional[datetime] = None
    filled_time: Optional[datetime] = None
    cancelled_time: Optional[datetime] = None
    
    # Execution details
    filled_quantity: int = 0
    filled_price: Optional[float] = None
    average_fill_price: Optional[float] = None
    remaining_quantity: int = 0
    
    # Error handling
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    # Metadata
    client_order_id: Optional[str] = None
    exchange_order_id: Optional[str] = None
    
    def __post_init__(self):
        self.remaining_quantity = self.quantity
        if not self.client_order_id:
            self.client_order_id = f"client_{self.order_id}"


@dataclass
class OrderExecution:
    """Individual order execution/fill"""
    execution_id: str
    order_id: str
    quantity: int
    price: float
    timestamp: datetime
    commission: float = 0.0


class OrderManager:
    """
    Manages order lifecycle from creation to completion.
    
    Features:
    - Order tracking and status updates
    - Fill management and partial fills
    - Error handling and retries
    - Performance monitoring
    """
    
    def __init__(self, kalshi_connector=None):
        self.kalshi_connector = kalshi_connector
        self.orders: Dict[str, Order] = {}
        self.executions: Dict[str, List[OrderExecution]] = {}
        
        # Statistics
        self.total_orders = 0
        self.successful_orders = 0
        self.failed_orders = 0
        self.cancelled_orders = 0
        self.total_volume = 0
        self.total_commission = 0.0
        
        # Performance tracking
        self.average_fill_time_ms = 0.0
        self.fill_time_samples: List[float] = []
        
        logger.info("OrderManager initialized")
    
    def create_order(self, position: Position, order_type: OrderType = OrderType.MARKET) -> Order:
        """
        Create a new order for a position.
        
        Args:
            position: Position to create order for
            order_type: Type of order to create
        
        Returns:
            Order object
        """
        order_id = str(uuid.uuid4())
        
        # Determine order side and price
        if position.direction in [TradeDirection.BUY_YES, TradeDirection.BUY_NO]:
            side = OrderSide.BUY
            price = position.entry_price
        else:
            side = OrderSide.SELL
            price = position.entry_price
        
        order = Order(
            order_id=order_id,
            position_id=position.position_id,
            match_id=position.match_id,
            player=position.player,
            side=side,
            order_type=order_type,
            quantity=position.quantity,
            price=price if order_type != OrderType.MARKET else None
        )
        
        self.orders[order_id] = order
        self.total_orders += 1
        
        logger.info(f"Created order {order_id} for position {position.position_id}")
        return order
    
    def submit_order(self, order: Order) -> bool:
        """
        Submit order to exchange.
        
        Args:
            order: Order to submit
        
        Returns:
            True if submission successful, False otherwise
        """
        try:
            if not self.kalshi_connector:
                # Mock submission for testing
                return self._mock_submit_order(order)
            
            # Real Kalshi submission
            return self._submit_to_kalshi(order)
            
        except Exception as e:
            logger.error(f"Failed to submit order {order.order_id}: {e}")
            order.error_message = str(e)
            order.retry_count += 1
            
            if order.retry_count < order.max_retries:
                logger.info(f"Retrying order {order.order_id} (attempt {order.retry_count + 1})")
                return False
            else:
                order.status = OrderStatus.REJECTED
                self.failed_orders += 1
                return False
    
    def _mock_submit_order(self, order: Order) -> bool:
        """Mock order submission for testing"""
        order.status = OrderStatus.SUBMITTED
        order.submitted_time = datetime.now()
        
        # Simulate immediate fill for market orders
        if order.order_type == OrderType.MARKET:
            time.sleep(0.1)  # Simulate network delay
            self._simulate_fill(order, order.quantity, order.price or 0.5)
        
        return True
    
    def _submit_to_kalshi(self, order: Order) -> bool:
        """Submit order to Kalshi exchange"""
        try:
            # Prepare order data
            order_data = {
                "market_id": order.match_id,  # Assuming match_id maps to market_id
                "side": order.side.value,
                "order_type": order.order_type.value,
                "quantity": order.quantity,
                "client_order_id": order.client_order_id
            }
            
            if order.price:
                order_data["price"] = order.price
            
            if order.stop_price:
                order_data["stop_price"] = order.stop_price
            
            # Submit to Kalshi
            response = self.kalshi_connector.session.post(
                f"{self.kalshi_connector.base_url}/orders",
                json=order_data,
                timeout=10
            )
            
            if response.status_code == 200:
                response_data = response.json()
                order.status = OrderStatus.SUBMITTED
                order.submitted_time = datetime.now()
                order.exchange_order_id = response_data.get('order_id')
                
                logger.info(f"Order {order.order_id} submitted to Kalshi")
                return True
            else:
                logger.error(f"Kalshi order submission failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Kalshi submission error: {e}")
            return False
    
    def update_order_status(self, order_id: str, status: OrderStatus, **kwargs):
        """Update order status and details"""
        if order_id not in self.orders:
            logger.warning(f"Order {order_id} not found")
            return
        
        order = self.orders[order_id]
        order.status = status
        
        # Update specific fields based on status
        if status == OrderStatus.SUBMITTED:
            order.submitted_time = kwargs.get('submitted_time', datetime.now())
        elif status == OrderStatus.FILLED:
            order.filled_time = kwargs.get('filled_time', datetime.now())
            order.filled_price = kwargs.get('filled_price')
            order.filled_quantity = kwargs.get('filled_quantity', order.quantity)
            order.remaining_quantity = 0
            
            # Calculate average fill price
            if order.filled_quantity > 0:
                order.average_fill_price = order.filled_price
                
            # Update statistics
            self.successful_orders += 1
            self.total_volume += order.filled_quantity
            
            # Calculate fill time
            if order.submitted_time:
                fill_time_ms = (order.filled_time - order.submitted_time).total_seconds() * 1000
                self.fill_time_samples.append(fill_time_ms)
                if len(self.fill_time_samples) > 100:
                    self.fill_time_samples = self.fill_time_samples[-100:]
                self.average_fill_time_ms = sum(self.fill_time_samples) / len(self.fill_time_samples)
                
        elif status == OrderStatus.CANCELLED:
            order.cancelled_time = kwargs.get('cancelled_time', datetime.now())
            self.cancelled_orders += 1
        elif status == OrderStatus.REJECTED:
            order.error_message = kwargs.get('error_message', 'Unknown error')
            self.failed_orders += 1
        
        logger.info(f"Updated order {order_id} status to {status.value}")
    
    def add_execution(self, order_id: str, quantity: int, price: float, 
                     timestamp: Optional[datetime] = None, commission: float = 0.0):
        """Add execution/fill to order"""
        if order_id not in self.orders:
            logger.warning(f"Order {order_id} not found")
            return
        
        order = self.orders[order_id]
        
        execution_id = str(uuid.uuid4())
        execution = OrderExecution(
            execution_id=execution_id,
            order_id=order_id,
            quantity=quantity,
            price=price,
            timestamp=timestamp or datetime.now(),
            commission=commission
        )
        
        if order_id not in self.executions:
            self.executions[order_id] = []
        self.executions[order_id].append(execution)
        
        # Update order
        order.filled_quantity += quantity
        order.remaining_quantity -= quantity
        order.total_commission += commission
        
        # Calculate average fill price
        total_value = sum(ex.quantity * ex.price for ex in self.executions[order_id])
        order.average_fill_price = total_value / order.filled_quantity if order.filled_quantity > 0 else None
        
        # Check if order is fully filled
        if order.remaining_quantity <= 0:
            self.update_order_status(order_id, OrderStatus.FILLED, 
                                   filled_time=execution.timestamp,
                                   filled_price=order.average_fill_price,
                                   filled_quantity=order.filled_quantity)
        
        logger.info(f"Added execution {execution_id} to order {order_id}: {quantity} @ {price}")
    
    def _simulate_fill(self, order: Order, quantity: int, price: float):
        """Simulate order fill for testing"""
        self.add_execution(order.order_id, quantity, price)
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        if order_id not in self.orders:
            logger.warning(f"Order {order_id} not found")
            return False
        
        order = self.orders[order_id]
        
        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED]:
            logger.warning(f"Cannot cancel order {order_id} with status {order.status.value}")
            return False
        
        try:
            if self.kalshi_connector:
                # Cancel on Kalshi
                response = self.kalshi_connector.session.post(
                    f"{self.kalshi_connector.base_url}/orders/{order.exchange_order_id}/cancel",
                    timeout=10
                )
                
                if response.status_code == 200:
                    self.update_order_status(order_id, OrderStatus.CANCELLED)
                    return True
                else:
                    logger.error(f"Failed to cancel order on Kalshi: {response.status_code}")
                    return False
            else:
                # Mock cancellation
                self.update_order_status(order_id, OrderStatus.CANCELLED)
                return True
                
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    def get_order_status(self, order_id: str) -> Optional[Order]:
        """Get order status"""
        return self.orders.get(order_id)
    
    def get_orders_for_position(self, position_id: str) -> List[Order]:
        """Get all orders for a position"""
        return [order for order in self.orders.values() if order.position_id == position_id]
    
    def get_active_orders(self) -> List[Order]:
        """Get all active orders"""
        return [order for order in self.orders.values() 
                if order.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED]]
    
    def get_order_statistics(self) -> Dict[str, Any]:
        """Get order execution statistics"""
        success_rate = (self.successful_orders / max(1, self.total_orders)) * 100
        
        return {
            'total_orders': self.total_orders,
            'successful_orders': self.successful_orders,
            'failed_orders': self.failed_orders,
            'cancelled_orders': self.cancelled_orders,
            'success_rate': f"{success_rate:.1f}%",
            'total_volume': self.total_volume,
            'total_commission': self.total_commission,
            'average_fill_time_ms': self.average_fill_time_ms,
            'active_orders': len(self.get_active_orders())
        }


class PositionManager:
    """
    Manages position lifecycle including order execution.
    
    Integrates with OrderManager to handle the complete trading workflow.
    """
    
    def __init__(self, order_manager: OrderManager):
        self.order_manager = order_manager
        self.positions: Dict[str, Position] = {}
        
        # Statistics
        self.total_positions = 0
        self.closed_positions = 0
        self.total_pnl = 0.0
        
        logger.info("PositionManager initialized")
    
    def open_position(self, position: Position) -> bool:
        """
        Open a new position by creating and submitting orders.
        
        Args:
            position: Position to open
        
        Returns:
            True if position opened successfully
        """
        try:
            # Create order
            order = self.order_manager.create_order(position, OrderType.MARKET)
            
            # Submit order
            if self.order_manager.submit_order(order):
                self.positions[position.position_id] = position
                self.total_positions += 1
                
                logger.info(f"Opened position {position.position_id}")
                return True
            else:
                logger.error(f"Failed to open position {position.position_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error opening position {position.position_id}: {e}")
            return False
    
    def close_position(self, position_id: str, exit_price: float) -> bool:
        """
        Close a position by creating and submitting exit orders.
        
        Args:
            position_id: Position to close
            exit_price: Price to close at
        
        Returns:
            True if position closed successfully
        """
        if position_id not in self.positions:
            logger.warning(f"Position {position_id} not found")
            return False
        
        position = self.positions[position_id]
        
        try:
            # Create exit order (opposite direction)
            exit_direction = self._get_exit_direction(position.direction)
            exit_position = Position(
                position_id=f"{position_id}_exit",
                match_id=position.match_id,
                player=position.player,
                direction=exit_direction,
                quantity=position.quantity,
                entry_price=exit_price,
                entry_probability=1.0 - position.entry_probability,  # Opposite probability
                entry_time=datetime.now(),
                stage=position.stage
            )
            
            # Create and submit exit order
            exit_order = self.order_manager.create_order(exit_position, OrderType.MARKET)
            
            if self.order_manager.submit_order(exit_order):
                # Update position
                position.status = OrderStatus.FILLED
                position.filled_price = exit_price
                position.filled_time = datetime.now()
                
                # Calculate P&L
                if position.direction in [TradeDirection.BUY_YES, TradeDirection.BUY_NO]:
                    position.pnl = (exit_price - position.entry_price) * position.quantity
                else:
                    position.pnl = (position.entry_price - exit_price) * position.quantity
                
                self.total_pnl += position.pnl
                self.closed_positions += 1
                
                logger.info(f"Closed position {position_id}: P&L = {position.pnl:.2f}")
                return True
            else:
                logger.error(f"Failed to close position {position_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error closing position {position_id}: {e}")
            return False
    
    def _get_exit_direction(self, entry_direction: TradeDirection) -> TradeDirection:
        """Get exit direction for position"""
        if entry_direction == TradeDirection.BUY_YES:
            return TradeDirection.SELL_YES
        elif entry_direction == TradeDirection.SELL_YES:
            return TradeDirection.BUY_YES
        elif entry_direction == TradeDirection.BUY_NO:
            return TradeDirection.SELL_NO
        else:  # SELL_NO
            return TradeDirection.BUY_NO
    
    def update_position_pnl(self, position_id: str, current_price: float):
        """Update position P&L based on current market price"""
        if position_id not in self.positions:
            return
        
        position = self.positions[position_id]
        
        if position.direction in [TradeDirection.BUY_YES, TradeDirection.BUY_NO]:
            position.pnl = (current_price - position.entry_price) * position.quantity
        else:
            position.pnl = (position.entry_price - current_price) * position.quantity
    
    def get_position_statistics(self) -> Dict[str, Any]:
        """Get position management statistics"""
        win_rate = 0.0
        if self.closed_positions > 0:
            winning_positions = sum(1 for p in self.positions.values() 
                                  if p.status == OrderStatus.FILLED and p.pnl > 0)
            win_rate = (winning_positions / self.closed_positions) * 100
        
        return {
            'total_positions': self.total_positions,
            'closed_positions': self.closed_positions,
            'active_positions': len(self.positions) - self.closed_positions,
            'total_pnl': self.total_pnl,
            'win_rate': f"{win_rate:.1f}%",
            'average_pnl_per_position': self.total_pnl / max(1, self.closed_positions)
        }


# Test the order execution system
if __name__ == "__main__":
    print("Testing Order Execution System...")
    
    from multi_stage_trading import Position, TradeDirection, TradeStage
    
    # Create order manager
    order_manager = OrderManager()
    
    # Create position manager
    position_manager = PositionManager(order_manager)
    
    # Create test position
    position = Position(
        position_id="test_position_1",
        match_id="test_match",
        player="Djokovic",
        direction=TradeDirection.BUY_YES,
        quantity=100,
        entry_price=0.55,
        entry_probability=0.65,
        entry_time=datetime.now(),
        stage=TradeStage.SERVICE_GAME_START
    )
    
    # Test position opening
    success = position_manager.open_position(position)
    print(f"Position opened: {success}")
    
    # Test order status
    orders = order_manager.get_orders_for_position(position.position_id)
    print(f"Orders for position: {len(orders)}")
    
    if orders:
        order = orders[0]
        print(f"Order status: {order.status.value}")
        print(f"Order details: {order}")
    
    # Test position closing
    if success:
        close_success = position_manager.close_position(position.position_id, 0.60)
        print(f"Position closed: {close_success}")
    
    # Test statistics
    print(f"Order statistics: {order_manager.get_order_statistics()}")
    print(f"Position statistics: {position_manager.get_position_statistics()}")
    
    print("\nOrder Execution System test complete!")
