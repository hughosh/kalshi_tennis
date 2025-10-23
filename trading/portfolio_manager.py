import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from simple_kalshi_client import SimpleKalshiClient
from order_logging.kalshi_order_logger import order_logger

logger = logging.getLogger(__name__)

@dataclass
class PortfolioBalance:
    """Portfolio balance information"""
    balance_cents: int
    balance_dollars: float
    available_cash_cents: int
    available_cash_dollars: float
    timestamp: datetime

@dataclass
class Position:
    """Kalshi position information"""
    ticker: str
    position: int  # Positive for long, negative for short
    market_value_cents: int
    market_value_dollars: float
    timestamp: datetime

class PortfolioManager:
    """
    Manages portfolio balance, cash availability, and position sizing.
    Integrates with Kalshi API to track real portfolio state.
    """

    def __init__(self, kalshi_client: Optional[SimpleKalshiClient] = None):
        self.kalshi_client = kalshi_client or SimpleKalshiClient()
        self.current_balance: Optional[PortfolioBalance] = None
        self.current_positions: List[Position] = []
        self.last_update: Optional[datetime] = None
        
        # Position sizing parameters
        self.max_position_size_pct = float(os.getenv("MAX_POSITION_SIZE_PCT", "0.05"))  # 5% max per position
        self.max_total_exposure_pct = float(os.getenv("MAX_TOTAL_EXPOSURE_PCT", "0.20"))  # 20% max total exposure
        
        logger.info(f"PortfolioManager initialized - Max position: {self.max_position_size_pct:.1%}, Max exposure: {self.max_total_exposure_pct:.1%}")

    def update_portfolio_data(self) -> bool:
        """Update portfolio balance and positions from Kalshi API"""
        try:
            # Get balance
            balance_response = self.kalshi_client.get_portfolio_balance()
            if not balance_response:
                logger.warning("Failed to get portfolio balance from Kalshi")
                return False
            
            # Extract balance information
            balance_cents = balance_response.get('balance', 0)
            balance_dollars = balance_cents / 100.0
            
            # For now, assume all balance is available cash (simplified)
            # In reality, you'd need to account for margin requirements, etc.
            available_cash_cents = balance_cents
            available_cash_dollars = balance_dollars
            
            self.current_balance = PortfolioBalance(
                balance_cents=balance_cents,
                balance_dollars=balance_dollars,
                available_cash_cents=available_cash_cents,
                available_cash_dollars=available_cash_dollars,
                timestamp=datetime.now()
            )
            
            # Get positions
            positions_response = self.kalshi_client.get_portfolio_positions()
            self.current_positions = []
            
            if positions_response:
                for pos_data in positions_response:
                    position = Position(
                        ticker=pos_data.get('ticker', ''),
                        position=pos_data.get('position', 0),
                        market_value_cents=pos_data.get('market_value', 0),
                        market_value_dollars=pos_data.get('market_value', 0) / 100.0,
                        timestamp=datetime.now()
                    )
                    self.current_positions.append(position)
            
            self.last_update = datetime.now()
            
            logger.info(f"Portfolio updated - Balance: ${balance_dollars:.2f}, Positions: {len(self.current_positions)}")
            order_logger.log_portfolio_update(
                balance_dollars=balance_dollars,
                available_cash_dollars=available_cash_dollars,
                position_count=len(self.current_positions),
                total_exposure_dollars=self.get_total_exposure_dollars()
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating portfolio data: {e}")
            return False

    def get_available_cash_dollars(self) -> float:
        """Get available cash in dollars"""
        if not self.current_balance:
            self.update_portfolio_data()
        
        if self.current_balance:
            return self.current_balance.available_cash_dollars
        return 0.0

    def get_total_exposure_dollars(self) -> float:
        """Calculate total exposure across all positions"""
        total_exposure = 0.0
        for position in self.current_positions:
            # Exposure is the absolute value of position * market value
            exposure = abs(position.position) * position.market_value_dollars
            total_exposure += exposure
        return total_exposure

    def can_place_order(self, order_value_dollars: float) -> Tuple[bool, str]:
        """
        Check if we can place an order based on available cash and risk limits.
        
        Returns:
            (can_place: bool, reason: str)
        """
        if not self.current_balance:
            if not self.update_portfolio_data():
                return False, "Failed to get portfolio balance"
        
        available_cash = self.get_available_cash_dollars()
        
        # Check if we have enough cash
        if order_value_dollars > available_cash:
            return False, f"Insufficient cash: need ${order_value_dollars:.2f}, have ${available_cash:.2f}"
        
        # Check position size limit
        max_position_value = available_cash * self.max_position_size_pct
        if order_value_dollars > max_position_value:
            return False, f"Position too large: ${order_value_dollars:.2f} exceeds {self.max_position_size_pct:.1%} limit (${max_position_value:.2f})"
        
        # Check total exposure limit
        current_exposure = self.get_total_exposure_dollars()
        max_total_exposure = available_cash * self.max_total_exposure_pct
        if current_exposure + order_value_dollars > max_total_exposure:
            return False, f"Total exposure limit: ${current_exposure + order_value_dollars:.2f} exceeds {self.max_total_exposure_pct:.1%} limit (${max_total_exposure:.2f})"
        
        return True, "Order approved"

    def calculate_position_size(self, signal_price: float, max_shares: int = 10) -> int:
        """
        Calculate appropriate position size based on available cash and risk limits.
        
        Args:
            signal_price: Price per share for the signal
            max_shares: Maximum shares to consider
            
        Returns:
            Number of shares to trade
        """
        available_cash = self.get_available_cash_dollars()
        
        # Calculate maximum position value based on risk limits
        max_position_value = available_cash * self.max_position_size_pct
        
        # Calculate maximum shares based on position value limit
        max_shares_by_value = int(max_position_value / signal_price)
        
        # Use the smaller of the two limits
        recommended_shares = min(max_shares, max_shares_by_value)
        
        # Ensure we don't exceed available cash
        total_cost = recommended_shares * signal_price
        if total_cost > available_cash:
            recommended_shares = int(available_cash / signal_price)
        
        # Ensure minimum of 1 share if we have enough cash
        if recommended_shares == 0 and available_cash >= signal_price:
            recommended_shares = 1
        
        logger.info(f"Position sizing: {recommended_shares} shares at ${signal_price:.3f} = ${total_cost:.2f}")
        return recommended_shares

    def get_portfolio_summary(self) -> Dict[str, any]:
        """Get a summary of current portfolio state"""
        if not self.current_balance:
            self.update_portfolio_data()
        
        return {
            "balance_dollars": self.current_balance.balance_dollars if self.current_balance else 0.0,
            "available_cash_dollars": self.get_available_cash_dollars(),
            "total_exposure_dollars": self.get_total_exposure_dollars(),
            "position_count": len(self.current_positions),
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "risk_limits": {
                "max_position_size_pct": self.max_position_size_pct,
                "max_total_exposure_pct": self.max_total_exposure_pct
            }
        }

# Global instance
portfolio_manager = PortfolioManager()
