"""
Win Tracking System for Tennis Trading Signals

This module implements real-time P&L monitoring and automatic position management
for trading signals, including profit targets and stop losses.
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import logging
import json
import time
import os
from pathlib import Path

from trading.multi_stage_trading import TradingSignal, TradeDirection
from trading.position_models import TradingPosition, PositionStatus
from data.data_integration import ValidatedMatchState
from execution.improved_order_executor import ImprovedOrderExecutor, create_improved_executor
from order_logging.kalshi_order_logger import order_logger

logger = logging.getLogger(__name__)


class WinTracker:
    """
    Real-time win tracking system for trading signals.
    
    Monitors active positions and automatically closes them at profit targets
    or stop losses.
    """
    
    def __init__(self, 
                 profit_target_pct: float = 0.05,
                 stop_loss_pct: float = 0.05,
                 max_holding_hours: float = 24.0,
                 update_interval_seconds: int = 30,
                 enable_trading: bool = True):
        
        self.profit_target_pct = profit_target_pct
        self.stop_loss_pct = stop_loss_pct
        self.max_holding_hours = max_holding_hours
        self.update_interval_seconds = update_interval_seconds
        self.enable_trading = enable_trading
        
        # Initialize simple order executor if trading is enabled
        self.order_executor = None
        if enable_trading:
            try:
                self.order_executor = create_improved_executor()
                logger.info("Improved order executor initialized for live trading")
            except Exception as e:
                logger.error(f"Failed to initialize order executor: {e}")
                logger.warning("Continuing in simulation mode")
                self.enable_trading = False
        
        # Active positions
        self.active_positions: Dict[str, TradingPosition] = {}
        
        # Closed positions (for statistics)
        self.closed_positions: List[TradingPosition] = []
        
        # Statistics
        self.total_positions = 0
        self.winning_positions = 0
        self.losing_positions = 0
        self.total_pnl = 0.0
        
        logger.info(f"WinTracker initialized - Profit target: {profit_target_pct*100}%, Stop loss: {stop_loss_pct*100}%")
        
        # Load existing data
        self.load_from_file()
    
    def load_from_file(self):
        """Load positions from file"""
        file_path = Path("win_tracker_data.json")
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                # Load active positions
                for pos_id, pos_data in data.get('active_positions', {}).items():
                    # Convert datetime strings back to datetime objects
                    pos_data['entry_time'] = datetime.fromisoformat(pos_data['entry_time'])
                    pos_data['last_updated'] = datetime.fromisoformat(pos_data['last_updated'])
                    if pos_data.get('exit_time'):
                        pos_data['exit_time'] = datetime.fromisoformat(pos_data['exit_time'])
                    
                    # Convert enum strings back to enums
                    pos_data['direction'] = TradeDirection(pos_data['direction'])
                    pos_data['status'] = PositionStatus(pos_data['status'])
                    
                    position = TradingPosition(**pos_data)
                    self.active_positions[pos_id] = position
                
                # Load closed positions
                for pos_data in data.get('closed_positions', []):
                    pos_data['entry_time'] = datetime.fromisoformat(pos_data['entry_time'])
                    pos_data['last_updated'] = datetime.fromisoformat(pos_data['last_updated'])
                    if pos_data.get('exit_time'):
                        pos_data['exit_time'] = datetime.fromisoformat(pos_data['exit_time'])
                    
                    pos_data['direction'] = TradeDirection(pos_data['direction'])
                    pos_data['status'] = PositionStatus(pos_data['status'])
                    
                    position = TradingPosition(**pos_data)
                    self.closed_positions.append(position)
                
                # Load statistics
                stats = data.get('statistics', {})
                self.total_positions = stats.get('total_positions', 0)
                self.winning_positions = stats.get('winning_positions', 0)
                self.losing_positions = stats.get('losing_positions', 0)
                self.total_pnl = stats.get('total_pnl', 0.0)
                
                logger.info(f"Loaded {len(self.active_positions)} active and {len(self.closed_positions)} closed positions")
                
            except Exception as e:
                logger.error(f"Error loading win tracker data: {e}")
    
    def save_to_file(self):
        """Save positions to file"""
        file_path = Path("win_tracker_data.json")
        try:
            data = {
                'active_positions': {},
                'closed_positions': [],
                'statistics': {
                    'total_positions': self.total_positions,
                    'winning_positions': self.winning_positions,
                    'losing_positions': self.losing_positions,
                    'total_pnl': self.total_pnl
                }
            }
            
            # Convert active positions to serializable format
            for pos_id, position in self.active_positions.items():
                pos_dict = {
                    'signal_id': position.signal_id,
                    'match_id': position.match_id,
                    'player': position.player,
                    'direction': position.direction.value,
                    'entry_price': position.entry_price,
                    'entry_time': position.entry_time.isoformat(),
                    'quantity': position.quantity,
                    'stop_loss_pct': position.stop_loss_pct,
                    'take_profit_pct': position.take_profit_pct,
                    'status': position.status.value,
                    'current_price': position.current_price,
                    'current_pnl_pct': position.current_pnl_pct,
                    'current_pnl_absolute': position.current_pnl_absolute,
                    'exit_price': position.exit_price,
                    'exit_time': position.exit_time.isoformat() if position.exit_time else None,
                    'exit_reason': position.exit_reason,
                    'last_updated': position.last_updated.isoformat(),
                    'update_count': position.update_count
                }
                data['active_positions'][pos_id] = pos_dict
            
            # Convert closed positions to serializable format
            for position in self.closed_positions:
                pos_dict = {
                    'signal_id': position.signal_id,
                    'match_id': position.match_id,
                    'player': position.player,
                    'direction': position.direction.value,
                    'entry_price': position.entry_price,
                    'entry_time': position.entry_time.isoformat(),
                    'quantity': position.quantity,
                    'stop_loss_pct': position.stop_loss_pct,
                    'take_profit_pct': position.take_profit_pct,
                    'status': position.status.value,
                    'current_price': position.current_price,
                    'current_pnl_pct': position.current_pnl_pct,
                    'current_pnl_absolute': position.current_pnl_absolute,
                    'exit_price': position.exit_price,
                    'exit_time': position.exit_time.isoformat() if position.exit_time else None,
                    'exit_reason': position.exit_reason,
                    'last_updated': position.last_updated.isoformat(),
                    'update_count': position.update_count
                }
                data['closed_positions'].append(pos_dict)
            
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving win tracker data: {e}")
    
    def add_signal(self, signal: TradingSignal, match_state: ValidatedMatchState, signal_id: str = None) -> str:
        """
        Add a new trading signal as an active position.
        
        Args:
            signal: Trading signal to track
            match_state: Current match state
            signal_id: Optional signal ID to use (if not provided, will generate one)
            
        Returns:
            Position ID for tracking
        """
        if signal_id is None:
            position_id = f"pos_{signal.match_id}_{signal.player}_{int(time.time())}"
        else:
            position_id = f"pos_{signal_id}"
        
        # Determine entry price based on signal direction
        if signal.direction in [TradeDirection.BUY_YES, TradeDirection.BUY_NO]:
            entry_price = signal.market_price
        else:  # SELL_YES, SELL_NO
            entry_price = signal.market_price
        
        position = TradingPosition(
            signal_id=signal_id or f"signal_{signal.match_id}_{signal.player}",
            match_id=signal.match_id,
            player=signal.player,
            direction=signal.direction,
            entry_price=entry_price,
            entry_time=datetime.now(),
            stop_loss_pct=self.stop_loss_pct,
            take_profit_pct=self.profit_target_pct
        )
        
        self.active_positions[position_id] = position
        self.total_positions += 1
        
        # Place buy + limit sell orders if trading is enabled
        if self.enable_trading and self.order_executor:
            try:
                # Get market ticker for the player
                market_ticker = self._get_market_ticker(signal.player, match_state)
                if market_ticker:
                    success = self.order_executor.place_buy_order(
                        market_ticker=market_ticker,
                        current_price=entry_price,
                        position_id=position_id
                    )
                    if success:
                        logger.info(f"Orders placed for position {position_id}: Buy + Limit Sell at {self.order_executor.profit_target_pct:.1%} profit")
                        # Log successful order placement
                        order_logger.log_order_placement(
                            order_id=f"buy_{position_id}",
                            position_id=position_id,
                            market_ticker=market_ticker,
                            player_name=signal.player,
                            direction="BUY_YES",
                            price=entry_price,
                            quantity=5,
                            message=f"Successfully placed buy order for {signal.player}"
                        )
                    else:
                        logger.error(f"Failed to place orders for position {position_id}")
                        order_logger.log_order_error(
                            order_id="N/A",
                            position_id=position_id,
                            error_message=f"Failed to place orders for position {position_id}",
                            error_details="Order executor returned False"
                        )
                else:
                    logger.warning(f"Could not find market ticker for {signal.player}")
                    order_logger.log_order_error(
                        order_id="N/A",
                        position_id=position_id,
                        error_message=f"Could not find market ticker for {signal.player}",
                        error_details="Market ticker lookup failed"
                    )
            except Exception as e:
                logger.error(f"Error placing orders for position {position_id}: {e}")
                order_logger.log_order_error(
                    order_id="N/A",
                    position_id=position_id,
                    error_message=f"Error placing orders for position {position_id}: {e}",
                    error_details=str(e)
                )
        
        logger.info(f"Added position {position_id}: {signal.player} {signal.direction.value} at {entry_price:.3f}")
        
        # Save to file
        self.save_to_file()
        
        return position_id
    
    def _get_market_ticker(self, player_name: str, match_state: ValidatedMatchState) -> Optional[str]:
        """
        Get the Kalshi market ticker for a player by finding the actual market ticker
        from the Kalshi markets API call.
        
        Args:
            player_name: Name of the player
            match_state: Current match state
            
        Returns:
            Market ticker string or None if not found
        """
        try:
            # Import here to avoid circular imports
            from kalshi_api_client import kalshi_api_client
            
            if not kalshi_api_client.client:
                logger.warning("Kalshi client not available for market ticker lookup")
                return None
            
            # Get all tennis events (which are actually markets)
            events = kalshi_api_client.get_tennis_events()
            if not events:
                logger.warning("No tennis events found for market ticker lookup")
                return None
            
            # Extract player last name for matching
            player_last_name = player_name.split()[-1].lower()
            
            # Find matching event/market for this player
            for event in events:
                event_title_lower = event.title.lower()
                
                # Check if player name appears in the event title
                if player_last_name in event_title_lower:
                    logger.debug(f"Found matching market ticker for {player_name}: {event.event_id}")
                    return event.event_id  # event_id is actually the market ticker
            
            logger.warning(f"Could not find market ticker for {player_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting market ticker for {player_name}: {e}")
            return None
    
    def update_position_prices(self, kalshi_client) -> None:
        """
        Update current prices for all active positions.
        
        Args:
            kalshi_client: Kalshi API client for fetching current prices
        """
        positions_to_close = []
        
        for position_id, position in self.active_positions.items():
            try:
                # Get current market price for this player
                current_price = self._get_current_price(position, kalshi_client)
                
                if current_price is not None:
                    position.current_price = current_price
                    position.last_updated = datetime.now()
                    position.update_count += 1
                    
                    # Calculate P&L
                    self._calculate_pnl(position)
                    
                    # Check exit conditions and collect positions to close
                    should_close, close_reason = self._check_exit_conditions(position)
                    if should_close:
                        positions_to_close.append((position, close_reason))
                    
            except Exception as e:
                logger.error(f"Error updating position {position_id}: {e}")
        
        # Close positions that met exit conditions (after iteration is complete)
        for position, reason in positions_to_close:
            # Determine status based on reason
            if "Profit target" in reason:
                status = PositionStatus.CLOSED_PROFIT
            elif "Stop loss" in reason:
                status = PositionStatus.CLOSED_LOSS
            elif "Max holding time" in reason:
                status = PositionStatus.CLOSED_EXPIRED
            else:
                status = PositionStatus.CLOSED_MANUAL
            
            self._close_position(position, status, reason)
        
        # Save to file after all updates
        self.save_to_file()
    
    def _get_current_price(self, position: TradingPosition, kalshi_client) -> Optional[float]:
        """
        Get current market price for a position.
        
        Args:
            position: Trading position
            kalshi_client: Kalshi API client
            
        Returns:
            Current market price or None if not available
        """
        try:
            # Import here to avoid circular imports
            from kalshi_api_client import kalshi_api_client
            
            if not kalshi_api_client.client:
                return None
            
            # Get tennis events
            events = kalshi_api_client.get_tennis_events()
            if not events:
                return None
            
            # Find matching event for this player
            player_lastname = position.player.split()[-1].lower()
            
            for event in events:
                event_title_lower = event.title.lower()
                
                if 'will' in event_title_lower and 'win' in event_title_lower:
                    will_index = event_title_lower.find('will')
                    win_index = event_title_lower.find('win')
                    if will_index != -1 and win_index != -1 and win_index > will_index:
                        player_name_in_title = event_title_lower[will_index+4:win_index].strip()
                        
                        if player_lastname in player_name_in_title:
                            markets = kalshi_api_client.get_event_markets(event.event_id)
                            for market in markets:
                                return market.yes_price
            
            return None
            
        except Exception as e:
            logger.debug(f"Error getting current price for {position.player}: {e}")
            return None
    
    def _calculate_pnl(self, position: TradingPosition) -> None:
        """
        Calculate P&L for a position.
        
        Args:
            position: Trading position to calculate P&L for
        """
        if position.current_price is None:
            return
        
        # Calculate P&L based on direction
        if position.direction in [TradeDirection.BUY_YES, TradeDirection.BUY_NO]:
            # Long position: profit if price goes up
            pnl_pct = (position.current_price - position.entry_price) / position.entry_price
        else:  # SELL_YES, SELL_NO
            # Short position: profit if price goes down
            pnl_pct = (position.entry_price - position.current_price) / position.entry_price
        
        position.current_pnl_pct = pnl_pct
        position.current_pnl_absolute = pnl_pct * position.quantity * 100  # Assuming $1 per share
    
    def _check_exit_conditions(self, position: TradingPosition) -> Tuple[bool, Optional[str]]:
        """
        Check if position should be closed based on exit conditions.
        
        Args:
            position: Trading position to check
            
        Returns:
            Tuple of (should_close, close_reason)
        """
        if position.status != PositionStatus.ACTIVE:
            return False, None
        
        # Check profit target
        if position.current_pnl_pct >= position.take_profit_pct:
            return True, f"Profit target reached: {position.current_pnl_pct:.1%}"
        
        # Check stop loss
        if position.current_pnl_pct <= -position.stop_loss_pct:
            return True, f"Stop loss triggered: {position.current_pnl_pct:.1%}"
        
        # Check time expiry
        holding_time = datetime.now() - position.entry_time
        if holding_time.total_seconds() > self.max_holding_hours * 3600:
            return True, f"Max holding time exceeded: {holding_time}"
        
        return False, None
    
    def _close_position(self, position: TradingPosition, status: PositionStatus, reason: str) -> None:
        """
        Close a position.
        
        Args:
            position: Position to close
            status: Final status
            reason: Reason for closing
        """
        position.status = status
        position.exit_price = position.current_price
        position.exit_time = datetime.now()
        position.exit_reason = reason
        
        # Move to closed positions
        position_id = None
        for pid, pos in self.active_positions.items():
            if pos == position:
                position_id = pid
                break
        
        if position_id:
            del self.active_positions[position_id]
            self.closed_positions.append(position)
            
            # Update statistics
            if status == PositionStatus.CLOSED_PROFIT:
                self.winning_positions += 1
            elif status == PositionStatus.CLOSED_LOSS:
                self.losing_positions += 1
            
            self.total_pnl += position.current_pnl_absolute
            
            # Log position closure
            order_logger.log_position_close(
                position_id=position_id,
                player_name=position.player,
                exit_price=position.exit_price or position.entry_price,
                exit_reason=reason,
                final_pnl_pct=position.current_pnl_pct,
                final_pnl_absolute=position.current_pnl_absolute,
                message=f"Position {position_id} closed: {reason}"
            )
            
            # Update corresponding signal outcome in database
            self._update_signal_outcome(position, status, reason)
            
            logger.info(f"Closed position: {position.player} {position.direction.value} - "
                       f"P&L: {position.current_pnl_pct:.1%} ({position.current_pnl_absolute:.2f}) - "
                       f"Reason: {reason}")
    
    def _update_signal_outcome(self, position: TradingPosition, status: PositionStatus, reason: str) -> None:
        """
        Update the corresponding signal outcome in the database.
        
        Args:
            position: Closed position
            status: Final position status
            reason: Reason for closing
        """
        try:
            # Import here to avoid circular imports
            from shared_signal_database import get_signal_database
            
            signal_db = get_signal_database()
            
            # Determine outcome based on status
            if status == PositionStatus.CLOSED_PROFIT:
                outcome = "Win"
                notes = f"Profit target reached: {position.current_pnl_pct:.1%}"
            elif status == PositionStatus.CLOSED_LOSS:
                outcome = "Loss"
                notes = f"Stop loss triggered: {position.current_pnl_pct:.1%}"
            else:
                outcome = "Closed"
                notes = reason
            
            # Update the signal outcome
            success = signal_db.update_signal_outcome(position.signal_id, outcome, notes)
            if not success:
                logger.warning(f"Failed to update signal outcome for {position.signal_id}")
                
        except Exception as e:
            logger.error(f"Error updating signal outcome: {e}")
    
    def get_position_summary(self) -> Dict[str, any]:
        """
        Get summary of all positions.
        
        Returns:
            Dictionary with position statistics
        """
        active_count = len(self.active_positions)
        closed_count = len(self.closed_positions)
        
        win_rate = 0.0
        if self.winning_positions + self.losing_positions > 0:
            win_rate = self.winning_positions / (self.winning_positions + self.losing_positions)
        
        return {
            "active_positions": active_count,
            "closed_positions": closed_count,
            "total_positions": self.total_positions,
            "winning_positions": self.winning_positions,
            "losing_positions": self.losing_positions,
            "win_rate": win_rate,
            "total_pnl": self.total_pnl,
            "profit_target_pct": self.profit_target_pct,
            "stop_loss_pct": self.stop_loss_pct
        }
    
    def get_active_positions(self) -> List[Dict[str, any]]:
        """
        Get list of active positions with current status.
        
        Returns:
            List of active position dictionaries
        """
        positions = []
        for position in self.active_positions.values():
            positions.append({
                "signal_id": position.signal_id,
                "match_id": position.match_id,
                "player": position.player,
                "direction": position.direction.value,
                "entry_price": position.entry_price,
                "current_price": position.current_price,
                "entry_time": position.entry_time.isoformat(),
                "current_pnl_pct": position.current_pnl_pct,
                "current_pnl_absolute": position.current_pnl_absolute,
                "status": position.status.value,
                "last_updated": position.last_updated.isoformat(),
                "update_count": position.update_count,
                "holding_time_minutes": (datetime.now() - position.entry_time).total_seconds() / 60
            })
        return positions
    
    def get_closed_positions(self) -> List[Dict[str, any]]:
        """
        Get list of closed positions.
        
        Returns:
            List of closed position dictionaries
        """
        positions = []
        for position in self.closed_positions:
            positions.append({
                "signal_id": position.signal_id,
                "match_id": position.match_id,
                "player": position.player,
                "direction": position.direction.value,
                "entry_price": position.entry_price,
                "exit_price": position.exit_price,
                "entry_time": position.entry_time.isoformat(),
                "exit_time": position.exit_time.isoformat() if position.exit_time else None,
                "final_pnl_pct": position.current_pnl_pct,
                "final_pnl_absolute": position.current_pnl_absolute,
                "status": position.status.value,
                "exit_reason": position.exit_reason,
                "holding_time_minutes": (position.exit_time - position.entry_time).total_seconds() / 60 if position.exit_time else None
            })
        return positions
    
    def clear_all_positions(self) -> None:
        """Clear all active and closed positions"""
        self.active_positions = {}
        self.closed_positions = []
        self.total_positions = 0
        self.winning_positions = 0
        self.losing_positions = 0
        self.total_pnl = 0.0
        self.save_to_file()
        logger.info("All positions cleared successfully")
    
    def check_and_manage_orders(self):
        """Check order status and manage fills/cancellations"""
        if self.order_executor:
            self.order_executor.check_and_manage_orders()


# Global win tracker instance
win_tracker = WinTracker(
    profit_target_pct=0.05,  # 5% profit target
    stop_loss_pct=0.05,      # 5% stop loss
    max_holding_hours=24.0,
    update_interval_seconds=30,
    enable_trading=True  # Enable actual trading
)
