"""
Phase 3: Multi-Stage Trading Strategy

This module implements the corrected trading strategy that captures more opportunities
than just 0-0 service games, with proper order execution and risk management.
"""

from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import logging
import time
from data.data_integration import ValidatedMatchState
from core.fast_expected_value import FastExpectedValueCalculator
from core.simple_probability_calculator import SimpleProbabilityCalculator

logger = logging.getLogger(__name__)


class TradeDirection(Enum):
    BUY_YES = "buy_yes"
    SELL_YES = "sell_yes"
    BUY_NO = "buy_no"
    SELL_NO = "sell_no"


class OrderStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class TradeStage(Enum):
    SERVICE_GAME_START = "service_game_start"  # 0-0 points
    BREAK_POINT = "break_point"  # Receiver has break point
    SET_POINT = "set_point"  # Server has set point
    MATCH_POINT = "match_point"  # Server has match point
    MOMENTUM_SHIFT = "momentum_shift"  # Recent performance change
    PRESSURE_SITUATION = "pressure_situation"  # High-pressure moments


@dataclass
class TradingSignal:
    """Trading signal with all necessary information"""
    match_id: str
    player: str
    direction: TradeDirection
    stage: TradeStage
    entry_probability: float
    expected_value: float
    confidence: float
    edge: float
    market_price: float
    model_price: float
    timestamp: datetime
    reasoning: str


@dataclass
class Position:
    """Active trading position"""
    position_id: str
    match_id: str
    player: str
    direction: TradeDirection
    quantity: int
    entry_price: float
    entry_probability: float
    entry_time: datetime
    stage: TradeStage
    
    # Risk management
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    max_loss: Optional[float] = None
    
    # Status
    status: OrderStatus = OrderStatus.PENDING
    filled_price: Optional[float] = None
    filled_time: Optional[datetime] = None
    pnl: float = 0.0


@dataclass
class RiskLimits:
    """Risk management limits"""
    max_total_exposure: float = 1000.0
    max_position_size: float = 100.0
    max_positions_per_match: int = 1
    max_concurrent_positions: int = 3
    max_daily_loss: float = 200.0
    stop_loss_threshold: float = 0.03  # 3%
    take_profit_threshold: float = 0.05  # 5%


class MultiStageTradingStrategy:
    """
    Multi-stage trading strategy that captures opportunities beyond 0-0.
    
    Stages:
    1. Service Game Start (0-0) - Original strategy
    2. Break Points - Receiver has break point
    3. Set Points - Server has set point  
    4. Match Points - Server has match point
    5. Momentum Shifts - Recent performance changes
    6. Pressure Situations - High-pressure moments
    """
    
    def __init__(self, 
                 risk_limits: RiskLimits,
                 entry_threshold: float = 0.05,  # Increased from 0.02 to 0.05 (5%)
                 exit_threshold: float = 0.05):
        
        self.risk_limits = risk_limits
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        
        # Initialize probability engine (using simplified calculator for now)
        self.match_calc = SimpleProbabilityCalculator()
        self.expected_value_calc = FastExpectedValueCalculator(self.match_calc)
        
        # Active positions
        self.active_positions: Dict[str, Position] = {}
        
        # Statistics
        self.total_signals = 0
        self.executed_trades = 0
        self.successful_trades = 0
        self.total_pnl = 0.0
        
        logger.info("MultiStageTradingStrategy initialized")
    
    def evaluate_trading_opportunities(self, 
                                     state: ValidatedMatchState,
                                     market_data: Dict[str, Any]) -> List[TradingSignal]:
        """
        Evaluate all possible trading opportunities for a match.
        
        Args:
            state: Current match state
            market_data: Market prices and metadata
        
        Returns:
            List of trading signals
        """
        signals = []
        
        if not state.is_valid_for_trading():
            return signals
        
        # Get player parameters (simplified for now)
        server_name, receiver_name = state.player_names
        p_serve = 0.65  # Default serve probability
        
        # Stage 1: Service Game Start (0-0)
        if state.is_service_game_start():
            signal = self._evaluate_service_game_start(state, server_name, market_data, p_serve)
            if signal:
                signals.append(signal)
        
        # Stage 2: Break Points
        if self._is_break_point(state):
            signal = self._evaluate_break_point(state, receiver_name, market_data, p_serve)
            if signal:
                signals.append(signal)
        
        # Stage 3: Set Points
        if self._is_set_point(state):
            signal = self._evaluate_set_point(state, server_name, market_data, p_serve)
            if signal:
                signals.append(signal)
        
        # Stage 4: Match Points
        if self._is_match_point(state):
            signal = self._evaluate_match_point(state, server_name, market_data, p_serve)
            if signal:
                signals.append(signal)
        
        # Stage 5: General Edge Detection (any profitable opportunity)
        general_signal = self._evaluate_general_edge(state, market_data, p_serve)
        if general_signal:
            signals.append(general_signal)
        
        # Stage 6: Momentum Shifts
        momentum_signal = self._evaluate_momentum_shift(state, market_data, p_serve)
        if momentum_signal:
            signals.append(momentum_signal)
        
        # Stage 7: Pressure Situations
        pressure_signal = self._evaluate_pressure_situation(state, market_data, p_serve)
        if pressure_signal:
            signals.append(pressure_signal)
        
        # Deduplicate signals - only keep one signal per player per match
        deduplicated_signals = self._deduplicate_signals(signals)
        
        self.total_signals += len(deduplicated_signals)
        return deduplicated_signals
    
    def _evaluate_service_game_start(self, state: ValidatedMatchState, 
                                    server_name: str, market_data: Dict, p_serve: float) -> Optional[TradingSignal]:
        """Evaluate service game start opportunity"""
        if server_name not in market_data:
            return None
        
        market_price = market_data[server_name]['yes_price']
        
        # Calculate model probability
        model_probs = self.match_calc.get_match_win_probability(state, p_serve)
        model_price = model_probs[server_name]
        
        # Calculate edge
        edge = model_price - market_price
        
        if edge > self.entry_threshold:
            # Calculate expected value
            expected_movement = self.expected_value_calc.calculate_expected_movement(state, server_name, p_serve)
            expected_value = edge * 0.5  # Simplified
            
            return TradingSignal(
                match_id=state.match_id,
                player=server_name,
                direction=TradeDirection.BUY_YES,
                stage=TradeStage.SERVICE_GAME_START,
                entry_probability=model_price,
                expected_value=expected_value,
                confidence=min(1.0, abs(edge) * 10),
                edge=edge,
                market_price=market_price,
                model_price=model_price,
                timestamp=datetime.now(),
                reasoning=f"Service game start edge: {edge:.3f}"
            )
        
        return None
    
    def _evaluate_general_edge(self, state: ValidatedMatchState, 
                              market_data: Dict, p_serve: float) -> Optional[TradingSignal]:
        """Evaluate general edge opportunities for any match state"""
        server_name, receiver_name = state.player_names
        
        # Check both players for profitable edges
        for player_name in [server_name, receiver_name]:
            if player_name not in market_data:
                continue
            
            market_price = market_data[player_name]['yes_price']
            
            # Skip extreme prices - avoid trading at very high or very low probabilities
            if market_price > 0.95 or market_price < 0.05:
                logger.debug(f"Skipping {player_name} - extreme price: {market_price:.3f}")
                continue
            
            # Calculate model probability
            model_probs = self.match_calc.get_match_win_probability(state, p_serve)
            model_price = model_probs[player_name]
            
            # Calculate edge
            edge = model_price - market_price
            
            # Use higher threshold for general edge detection (5% instead of 2%)
            general_edge_threshold = 0.05
            
            # Check if edge is profitable (positive edge for BUY_YES)
            if edge > general_edge_threshold:
                # Additional validation: model price should be reasonable
                if model_price < 0.1 or model_price > 0.9:
                    logger.debug(f"Skipping {player_name} - extreme model price: {model_price:.3f}")
                    continue
                
                # Calculate expected value
                expected_movement = self.expected_value_calc.calculate_expected_movement(state, player_name, p_serve)
                expected_value = edge * 0.5  # Simplified
                
                return TradingSignal(
                    match_id=state.match_id,
                    player=player_name,
                    direction=TradeDirection.BUY_YES,
                    stage=TradeStage.MOMENTUM_SHIFT,  # Use existing stage
                    entry_probability=model_price,
                    expected_value=expected_value,
                    confidence=min(1.0, abs(edge) * 10),
                    edge=edge,
                    market_price=market_price,
                    model_price=model_price,
                    timestamp=datetime.now(),
                    reasoning=f"General edge detected: {edge:.3f} (model: {model_price:.3f}, market: {market_price:.3f})"
                )
            
            # Check for negative edge (SELL_YES opportunity)
            elif edge < -general_edge_threshold:
                # Additional validation: model price should be reasonable
                if model_price < 0.1 or model_price > 0.9:
                    logger.debug(f"Skipping {player_name} - extreme model price: {model_price:.3f}")
                    continue
                
                expected_movement = self.expected_value_calc.calculate_expected_movement(state, player_name, p_serve)
                expected_value = abs(edge) * 0.5  # Simplified
                
                return TradingSignal(
                    match_id=state.match_id,
                    player=player_name,
                    direction=TradeDirection.SELL_YES,
                    stage=TradeStage.MOMENTUM_SHIFT,  # Use existing stage
                    entry_probability=model_price,
                    expected_value=expected_value,
                    confidence=min(1.0, abs(edge) * 10),
                    edge=edge,
                    market_price=market_price,
                    model_price=model_price,
                    timestamp=datetime.now(),
                    reasoning=f"Negative edge detected: {edge:.3f} (model: {model_price:.3f}, market: {market_price:.3f})"
                )
        
        return None
    
    def _deduplicate_signals(self, signals: List[TradingSignal]) -> List[TradingSignal]:
        """
        Deduplicate signals to only keep one signal per player per match.
        Prioritizes signals with higher confidence and better edge.
        """
        if not signals:
            return signals
        
        # Group signals by player
        player_signals = {}
        for signal in signals:
            player = signal.player
            if player not in player_signals:
                player_signals[player] = []
            player_signals[player].append(signal)
        
        # For each player, keep only the best signal
        deduplicated = []
        for player, player_signal_list in player_signals.items():
            if len(player_signal_list) == 1:
                deduplicated.append(player_signal_list[0])
            else:
                # Choose the signal with the best combination of edge and confidence
                best_signal = max(player_signal_list, 
                                key=lambda s: abs(s.edge) * s.confidence)
                deduplicated.append(best_signal)
                logger.debug(f"Deduplicated {len(player_signal_list)} signals for {player}, kept best with edge {best_signal.edge:.3f}")
        
        return deduplicated
    
    def _evaluate_break_point(self, state: ValidatedMatchState,
                            receiver_name: str, market_data: Dict, p_serve: float) -> Optional[TradingSignal]:
        """Evaluate break point opportunity"""
        if receiver_name not in market_data:
            return None
        
        # Check if receiver has break point
        if not self._is_break_point(state):
            return None
        
        market_price = market_data[receiver_name]['yes_price']
        
        # Calculate model probability with break point pressure
        adjusted_p_serve = p_serve - 0.05  # Reduce serve probability under pressure
        model_probs = self.match_calc.get_match_win_probability(state, adjusted_p_serve)
        model_price = model_probs[receiver_name]
        
        edge = model_price - market_price
        
        if edge > self.entry_threshold:
            return TradingSignal(
                match_id=state.match_id,
                player=receiver_name,
                direction=TradeDirection.BUY_YES,
                stage=TradeStage.BREAK_POINT,
                entry_probability=model_price,
                expected_value=edge * 0.4,  # Lower expected value due to pressure
                confidence=min(0.8, abs(edge) * 8),
                edge=edge,
                market_price=market_price,
                model_price=model_price,
                timestamp=datetime.now(),
                reasoning=f"Break point opportunity: {edge:.3f}"
            )
        
        return None
    
    def _evaluate_set_point(self, state: ValidatedMatchState,
                          server_name: str, market_data: Dict, p_serve: float) -> Optional[TradingSignal]:
        """Evaluate set point opportunity"""
        if server_name not in market_data:
            return None
        
        if not self._is_set_point(state):
            return None
        
        market_price = market_data[server_name]['yes_price']
        
        # Calculate model probability with set point pressure
        adjusted_p_serve = p_serve + 0.03  # Increase serve probability under pressure
        model_probs = self.match_calc.get_match_win_probability(state, adjusted_p_serve)
        model_price = model_probs[server_name]
        
        edge = model_price - market_price
        
        if edge > self.entry_threshold:
            return TradingSignal(
                match_id=state.match_id,
                player=server_name,
                direction=TradeDirection.BUY_YES,
                stage=TradeStage.SET_POINT,
                entry_probability=model_price,
                expected_value=edge * 0.6,
                confidence=min(0.9, abs(edge) * 9),
                edge=edge,
                market_price=market_price,
                model_price=model_price,
                timestamp=datetime.now(),
                reasoning=f"Set point opportunity: {edge:.3f}"
            )
        
        return None
    
    def _evaluate_match_point(self, state: ValidatedMatchState,
                             server_name: str, market_data: Dict, p_serve: float) -> Optional[TradingSignal]:
        """Evaluate match point opportunity"""
        if server_name not in market_data:
            return None
        
        if not self._is_match_point(state):
            return None
        
        market_price = market_data[server_name]['yes_price']
        
        # Calculate model probability with match point pressure
        adjusted_p_serve = p_serve + 0.05  # Increase serve probability under pressure
        model_probs = self.match_calc.get_match_win_probability(state, adjusted_p_serve)
        model_price = model_probs[server_name]
        
        edge = model_price - market_price
        
        if edge > self.entry_threshold:
            return TradingSignal(
                match_id=state.match_id,
                player=server_name,
                direction=TradeDirection.BUY_YES,
                stage=TradeStage.MATCH_POINT,
                entry_probability=model_price,
                expected_value=edge * 0.7,
                confidence=min(0.95, abs(edge) * 10),
                edge=edge,
                market_price=market_price,
                model_price=model_price,
                timestamp=datetime.now(),
                reasoning=f"Match point opportunity: {edge:.3f}"
            )
        
        return None
    
    def _evaluate_momentum_shift(self, state: ValidatedMatchState,
                               market_data: Dict, p_serve: float) -> Optional[TradingSignal]:
        """Evaluate momentum shift opportunity"""
        # Simplified momentum detection
        # In production, this would analyze recent game results
        
        # For now, return None (placeholder)
        return None
    
    def _evaluate_pressure_situation(self, state: ValidatedMatchState,
                                    market_data: Dict, p_serve: float) -> Optional[TradingSignal]:
        """Evaluate pressure situation opportunity"""
        # Check for high-pressure situations
        server_games, receiver_games = state.games
        
        # Close games (4-4, 5-5, etc.)
        if abs(server_games - receiver_games) <= 1 and max(server_games, receiver_games) >= 4:
            # This is a pressure situation
            # Simplified implementation
            pass
        
        return None
    
    def _is_break_point(self, state: ValidatedMatchState) -> bool:
        """Check if receiver has break point"""
        if state.is_tiebreak:
            return False  # Simplified for tiebreak
        
        server_pts, receiver_pts = state.points
        
        # Receiver has break point if they have 3+ points and server has fewer
        return receiver_pts >= 3 and server_pts < receiver_pts
    
    def _is_set_point(self, state: ValidatedMatchState) -> bool:
        """Check if server has set point"""
        server_games, receiver_games = state.games
        
        # Server has set point if they have 5+ games and opponent has fewer
        return server_games >= 5 and server_games > receiver_games
    
    def _is_match_point(self, state: ValidatedMatchState) -> bool:
        """Check if server has match point"""
        server_sets, receiver_sets = state.sets
        
        if state.match_format == "BO3":
            # Server has match point if they have 1 set and are about to win second
            return server_sets == 1 and receiver_sets == 0 and self._is_set_point(state)
        else:  # BO5
            # Server has match point if they have 2 sets and are about to win third
            return server_sets == 2 and receiver_sets <= 1 and self._is_set_point(state)
    
    def execute_trade(self, signal: TradingSignal, market_data: Dict) -> Optional[Position]:
        """
        Execute a trade based on signal.
        
        Args:
            signal: Trading signal
            market_data: Current market data
        
        Returns:
            Position object if trade executed, None otherwise
        """
        # Check risk limits
        if not self._check_risk_limits(signal):
            logger.warning(f"Trade rejected due to risk limits: {signal}")
            return None
        
        # Calculate position size
        position_size = self._calculate_position_size(signal)
        
        # Create position
        position_id = f"{signal.match_id}_{signal.player}_{int(time.time())}"
        position = Position(
            position_id=position_id,
            match_id=signal.match_id,
            player=signal.player,
            direction=signal.direction,
            quantity=position_size,
            entry_price=signal.market_price,
            entry_probability=signal.entry_probability,
            entry_time=datetime.now(),
            stage=signal.stage,
            stop_loss_price=self._calculate_stop_loss(signal),
            take_profit_price=self._calculate_take_profit(signal)
        )
        
        # Store position
        self.active_positions[position_id] = position
        self.executed_trades += 1
        
        logger.info(f"Executed trade: {position}")
        return position
    
    def _check_risk_limits(self, signal: TradingSignal) -> bool:
        """Check if trade violates risk limits"""
        # Check concurrent positions
        if len(self.active_positions) >= self.risk_limits.max_concurrent_positions:
            return False
        
        # Check positions per match
        match_positions = sum(1 for p in self.active_positions.values() 
                             if p.match_id == signal.match_id)
        if match_positions >= self.risk_limits.max_positions_per_match:
            return False
        
        # Check total exposure
        total_exposure = sum(p.quantity * p.entry_price for p in self.active_positions.values())
        if total_exposure >= self.risk_limits.max_total_exposure:
            return False
        
        return True
    
    def _calculate_position_size(self, signal: TradingSignal) -> int:
        """Calculate position size based on risk limits and signal strength"""
        base_size = min(50, int(self.risk_limits.max_position_size * signal.confidence))
        return max(10, base_size)  # Minimum 10 shares
    
    def _calculate_stop_loss(self, signal: TradingSignal) -> float:
        """Calculate stop loss price"""
        if signal.direction in [TradeDirection.BUY_YES, TradeDirection.BUY_NO]:
            return signal.market_price * (1 - self.risk_limits.stop_loss_threshold)
        else:
            return signal.market_price * (1 + self.risk_limits.stop_loss_threshold)
    
    def _calculate_take_profit(self, signal: TradingSignal) -> float:
        """Calculate take profit price"""
        if signal.direction in [TradeDirection.BUY_YES, TradeDirection.BUY_NO]:
            return signal.market_price * (1 + self.risk_limits.take_profit_threshold)
        else:
            return signal.market_price * (1 - self.risk_limits.take_profit_threshold)
    
    def update_positions(self, state: ValidatedMatchState, market_data: Dict):
        """Update all active positions with current market data"""
        for position in self.active_positions.values():
            if position.match_id == state.match_id:
                self._update_position(position, state, market_data)
    
    def _update_position(self, position: Position, state: ValidatedMatchState, market_data: Dict):
        """Update individual position"""
        if position.player not in market_data:
            return
        
        current_price = market_data[position.player]['yes_price']
        
        # Calculate P&L
        if position.direction == TradeDirection.BUY_YES:
            position.pnl = (current_price - position.entry_price) * position.quantity
        elif position.direction == TradeDirection.SELL_YES:
            position.pnl = (position.entry_price - current_price) * position.quantity
        
        # Check exit conditions
        if self._should_exit_position(position, state, current_price):
            self._close_position(position, current_price)
    
    def _should_exit_position(self, position: Position, state: ValidatedMatchState, current_price: float) -> bool:
        """Check if position should be closed"""
        # Stop loss
        if position.stop_loss_price and self._price_hit_stop_loss(position, current_price):
            return True
        
        # Take profit
        if position.take_profit_price and self._price_hit_take_profit(position, current_price):
            return True
        
        # Game completion
        if state.is_service_game_start() and position.stage == TradeStage.SERVICE_GAME_START:
            return True
        
        # Time-based exit (simplified)
        if (datetime.now() - position.entry_time).total_seconds() > 300:  # 5 minutes
            return True
        
        return False
    
    def _price_hit_stop_loss(self, position: Position, current_price: float) -> bool:
        """Check if current price hit stop loss"""
        if position.direction in [TradeDirection.BUY_YES, TradeDirection.BUY_NO]:
            return current_price <= position.stop_loss_price
        else:
            return current_price >= position.stop_loss_price
    
    def _price_hit_take_profit(self, position: Position, current_price: float) -> bool:
        """Check if current price hit take profit"""
        if position.direction in [TradeDirection.BUY_YES, TradeDirection.BUY_NO]:
            return current_price >= position.take_profit_price
        else:
            return current_price <= position.take_profit_price
    
    def _close_position(self, position: Position, exit_price: float):
        """Close position"""
        position.status = OrderStatus.FILLED
        position.filled_price = exit_price
        position.filled_time = datetime.now()
        
        # Update statistics
        if position.pnl > 0:
            self.successful_trades += 1
        
        self.total_pnl += position.pnl
        
        logger.info(f"Closed position {position.position_id}: P&L = {position.pnl:.2f}")
    
    def get_strategy_statistics(self) -> Dict[str, Any]:
        """Get strategy performance statistics"""
        win_rate = (self.successful_trades / max(1, self.executed_trades)) * 100
        
        return {
            'total_signals': self.total_signals,
            'executed_trades': self.executed_trades,
            'successful_trades': self.successful_trades,
            'win_rate': f"{win_rate:.1f}%",
            'total_pnl': self.total_pnl,
            'active_positions': len(self.active_positions),
            'average_pnl_per_trade': self.total_pnl / max(1, self.executed_trades)
        }


# Test the multi-stage trading strategy
if __name__ == "__main__":
    print("Testing Multi-Stage Trading Strategy...")
    
    from data_integration import ValidatedMatchState
    
    # Create strategy
    risk_limits = RiskLimits(
        max_total_exposure=1000.0,
        max_position_size=100.0,
        max_positions_per_match=1,
        max_concurrent_positions=3
    )
    
    strategy = MultiStageTradingStrategy(risk_limits)
    
    # Create test state
    state = ValidatedMatchState(
        match_id="test_match",
        player_names=("Djokovic", "Sinner"),
        match_format="BO3",
        sets=(0, 0),
        games=(0, 0),
        points=(0, 0),
        server_serving=True,
        total_games_played=0,
        timestamp=datetime.now(),
        data_source="test",
        staleness_seconds=1.0
    )
    
    # Test market data
    market_data = {
        "Djokovic": {"yes_price": 0.55, "no_price": 0.45},
        "Sinner": {"yes_price": 0.45, "no_price": 0.55}
    }
    
    # Test signal generation
    signals = strategy.evaluate_trading_opportunities(state, market_data)
    print(f"Generated {len(signals)} signals")
    
    for signal in signals:
        print(f"Signal: {signal.stage.value} - {signal.player} - Edge: {signal.edge:.3f}")
    
    # Test trade execution
    if signals:
        position = strategy.execute_trade(signals[0], market_data)
        if position:
            print(f"Executed trade: {position}")
    
    print(f"Strategy statistics: {strategy.get_strategy_statistics()}")
    print("\nMulti-Stage Trading Strategy test complete!")
