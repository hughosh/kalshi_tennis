"""
Position Models for Tennis Trading System

This module contains the data models for trading positions and related enums.
"""

from typing import Optional
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from trading.multi_stage_trading import TradeDirection


class PositionStatus(Enum):
    """Status of a trading position"""
    ACTIVE = "active"
    CLOSED_PROFIT = "closed_profit"
    CLOSED_LOSS = "closed_loss"
    CLOSED_EXPIRED = "closed_expired"
    CLOSED_MANUAL = "closed_manual"


@dataclass
class TradingPosition:
    """Represents an active trading position"""
    signal_id: str
    match_id: str
    player: str
    direction: TradeDirection
    entry_price: float
    entry_time: datetime
    quantity: int = 5  # Number of shares
    
    # Risk management
    stop_loss_pct: float = 0.05  # 5% stop loss
    take_profit_pct: float = 0.05  # 5% take profit
    
    # Current status
    status: PositionStatus = PositionStatus.ACTIVE
    current_price: Optional[float] = None
    current_pnl_pct: float = 0.0
    current_pnl_absolute: float = 0.0
    
    # Exit information
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[str] = None
    
    # Metadata
    last_updated: datetime = field(default_factory=datetime.now)
    update_count: int = 0
