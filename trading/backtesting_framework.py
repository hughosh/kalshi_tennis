"""
Backtesting Framework

This module implements a comprehensive backtesting framework for validating
the tennis trading strategy on historical data.
"""

from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import logging
import pandas as pd
import numpy as np
from collections import defaultdict
import json
import time

from data.data_integration import ValidatedMatchState
from trading.multi_stage_trading import MultiStageTradingStrategy, TradingSignal, Position, TradeDirection
from execution.order_execution import OrderManager, PositionManager
from execution.risk_management import RiskManager

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """Backtesting configuration"""
    start_date: datetime
    end_date: datetime
    initial_capital: float = 10000.0
    commission_rate: float = 0.01  # 1% commission
    slippage_rate: float = 0.005   # 0.5% slippage
    
    # Risk limits
    max_position_size: float = 100.0
    max_total_exposure: float = 1000.0
    max_drawdown: float = 0.15
    
    # Strategy parameters
    entry_threshold: float = 0.02
    exit_threshold: float = 0.05
    
    # Data settings
    data_frequency: str = "1min"  # 1min, 5min, 15min, 1hour
    include_weekends: bool = False


@dataclass
class BacktestResult:
    """Backtesting results"""
    # Performance metrics
    total_return: float = 0.0
    annualized_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    
    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    average_win: float = 0.0
    average_loss: float = 0.0
    
    # Risk metrics
    var_95: float = 0.0
    expected_shortfall: float = 0.0
    volatility: float = 0.0
    
    # Detailed results
    equity_curve: List[Tuple[datetime, float]] = field(default_factory=list)
    trade_log: List[Dict[str, Any]] = field(default_factory=list)
    daily_returns: List[float] = field(default_factory=list)
    
    # Configuration
    config: BacktestConfig = field(default_factory=BacktestConfig)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None


class HistoricalDataProvider:
    """
    Provides historical tennis match data for backtesting.
    
    In production, this would connect to a historical data source.
    For now, it generates synthetic data.
    """
    
    def __init__(self):
        self.data_cache: Dict[str, List[Dict]] = {}
    
    def get_match_data(self, match_id: str, start_date: datetime, 
                      end_date: datetime) -> List[Dict[str, Any]]:
        """
        Get historical data for a match.
        
        Returns:
            List of data points with timestamps, scores, and market prices
        """
        if match_id in self.data_cache:
            return self.data_cache[match_id]
        
        # Generate synthetic data for testing
        data = self._generate_synthetic_match_data(match_id, start_date, end_date)
        self.data_cache[match_id] = data
        
        return data
    
    def _generate_synthetic_match_data(self, match_id: str, start_date: datetime, 
                                     end_date: datetime) -> List[Dict[str, Any]]:
        """Generate synthetic tennis match data"""
        data = []
        current_time = start_date
        
        # Simulate a tennis match progression
        sets = (0, 0)
        games = (0, 0)
        points = (0, 0)
        server_serving = True
        
        # Base probabilities
        p_serve = 0.65
        p_break = 0.25
        
        # Market prices (start with fair value)
        market_price_server = 0.60
        market_price_receiver = 0.40
        
        while current_time < end_date and max(sets) < 2:  # BO3 match
            # Simulate point outcome
            if server_serving:
                server_wins_point = np.random.random() < p_serve
            else:
                server_wins_point = np.random.random() < (1 - p_break)
            
            # Update score
            if server_wins_point:
                points = (points[0] + 1, points[1])
            else:
                points = (points[0], points[1] + 1)
            
            # Check for game completion
            if self._is_game_complete(points):
                if points[0] > points[1]:
                    games = (games[0] + 1, games[1])
                else:
                    games = (games[0], games[1] + 1)
                
                points = (0, 0)
                server_serving = not server_serving
                
                # Update market prices based on game outcome
                if games[0] > games[1]:
                    market_price_server += 0.02
                    market_price_receiver -= 0.02
                else:
                    market_price_server -= 0.02
                    market_price_receiver += 0.02
                
                # Clamp prices
                market_price_server = max(0.01, min(0.99, market_price_server))
                market_price_receiver = max(0.01, min(0.99, market_price_receiver))
            
            # Check for set completion
            if self._is_set_complete(games):
                if games[0] > games[1]:
                    sets = (sets[0] + 1, sets[1])
                else:
                    sets = (sets[0], sets[1] + 1)
                
                games = (0, 0)
            
            # Create data point
            data_point = {
                'timestamp': current_time,
                'match_id': match_id,
                'sets': sets,
                'games': games,
                'points': points,
                'server_serving': server_serving,
                'market_price_server': market_price_server,
                'market_price_receiver': market_price_receiver,
                'total_games_played': sum(sets) * 10 + sum(games)  # Rough estimate
            }
            
            data.append(data_point)
            
            # Advance time (simulate 30 seconds per point)
            current_time += timedelta(seconds=30)
        
        return data
    
    def _is_game_complete(self, points: Tuple[int, int]) -> bool:
        """Check if game is complete"""
        s_pts, r_pts = points
        return (s_pts >= 4 and s_pts - r_pts >= 2) or (r_pts >= 4 and r_pts - s_pts >= 2)
    
    def _is_set_complete(self, games: Tuple[int, int]) -> bool:
        """Check if set is complete"""
        s_games, r_games = games
        return (s_games >= 6 and s_games - r_games >= 2) or (r_games >= 6 and r_games - s_games >= 2)


class BacktestEngine:
    """
    Main backtesting engine that runs the strategy on historical data.
    """
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.data_provider = HistoricalDataProvider()
        
        # Initialize components
        self.order_manager = OrderManager()
        self.position_manager = PositionManager(self.order_manager)
        
        # Risk management
        self.risk_manager = RiskManager(
            max_total_exposure=config.max_total_exposure,
            max_position_size=config.max_position_size,
            max_drawdown=config.max_drawdown
        )
        
        # Trading strategy
        self.strategy = MultiStageTradingStrategy(
            risk_limits=self.risk_manager,
            entry_threshold=config.entry_threshold,
            exit_threshold=config.exit_threshold
        )
        
        # Backtest state
        self.current_capital = config.initial_capital
        self.positions: Dict[str, Position] = {}
        self.equity_curve: List[Tuple[datetime, float]] = []
        self.trade_log: List[Dict[str, Any]] = []
        
        logger.info(f"BacktestEngine initialized with capital {config.initial_capital}")
    
    def run_backtest(self, match_ids: List[str]) -> BacktestResult:
        """
        Run backtest on historical data.
        
        Args:
            match_ids: List of match IDs to backtest
        
        Returns:
            BacktestResult with performance metrics
        """
        logger.info(f"Starting backtest for {len(match_ids)} matches")
        start_time = time.time()
        
        # Process each match
        for match_id in match_ids:
            self._process_match(match_id)
        
        # Calculate final results
        result = self._calculate_results()
        
        elapsed_time = time.time() - start_time
        logger.info(f"Backtest completed in {elapsed_time:.2f} seconds")
        
        return result
    
    def _process_match(self, match_id: str):
        """Process a single match through the backtest"""
        logger.info(f"Processing match {match_id}")
        
        # Get historical data
        data = self.data_provider.get_match_data(
            match_id, 
            self.config.start_date, 
            self.config.end_date
        )
        
        if not data:
            logger.warning(f"No data available for match {match_id}")
            return
        
        # Process each data point
        for i, data_point in enumerate(data):
            self._process_data_point(data_point)
            
            # Update equity curve periodically
            if i % 10 == 0:  # Every 10 data points
                self._update_equity_curve(data_point['timestamp'])
    
    def _process_data_point(self, data_point: Dict[str, Any]):
        """Process a single data point"""
        timestamp = data_point['timestamp']
        match_id = data_point['match_id']
        
        # Create ValidatedMatchState
        state = ValidatedMatchState(
            match_id=match_id,
            player_names=("Server", "Receiver"),  # Simplified
            match_format="BO3",
            sets=data_point['sets'],
            games=data_point['games'],
            points=data_point['points'],
            server_serving=data_point['server_serving'],
            total_games_played=data_point['total_games_played'],
            timestamp=timestamp,
            data_source="backtest",
            staleness_seconds=0.0
        )
        
        # Create market data
        market_data = {
            "Server": {
                "yes_price": data_point['market_price_server'],
                "no_price": 1.0 - data_point['market_price_server']
            },
            "Receiver": {
                "yes_price": data_point['market_price_receiver'],
                "no_price": 1.0 - data_point['market_price_receiver']
            }
        }
        
        # Generate trading signals
        signals = self.strategy.evaluate_trading_opportunities(state, market_data)
        
        # Execute trades
        for signal in signals:
            self._execute_signal(signal, market_data)
        
        # Update existing positions
        self._update_positions(state, market_data)
        
        # Check risk limits
        self._check_risk_limits()
    
    def _execute_signal(self, signal: TradingSignal, market_data: Dict):
        """Execute a trading signal"""
        # Check if we already have a position for this match
        existing_positions = [p for p in self.positions.values() if p.match_id == signal.match_id]
        
        if len(existing_positions) >= 1:  # Max 1 position per match
            return
        
        # Create position
        position = Position(
            position_id=f"{signal.match_id}_{signal.player}_{int(time.time())}",
            match_id=signal.match_id,
            player=signal.player,
            direction=signal.direction,
            quantity=50,  # Fixed quantity for backtest
            entry_price=signal.market_price,
            entry_probability=signal.entry_probability,
            entry_time=signal.timestamp,
            stage=signal.stage
        )
        
        # Check risk limits
        is_safe, violations = self.risk_manager.check_position_risk(position, list(self.positions.values()))
        
        if not is_safe:
            logger.warning(f"Trade rejected due to risk violations: {violations}")
            return
        
        # Execute trade
        if self.position_manager.open_position(position):
            self.positions[position.position_id] = position
            
            # Log trade
            self.trade_log.append({
                'timestamp': signal.timestamp,
                'action': 'OPEN',
                'position_id': position.position_id,
                'match_id': signal.match_id,
                'player': signal.player,
                'direction': signal.direction.value,
                'quantity': position.quantity,
                'price': position.entry_price,
                'signal_stage': signal.stage.value,
                'edge': signal.edge,
                'expected_value': signal.expected_value
            })
    
    def _update_positions(self, state: ValidatedMatchState, market_data: Dict):
        """Update existing positions"""
        positions_to_close = []
        
        for position in self.positions.values():
            if position.match_id != state.match_id:
                continue
            
            # Update P&L
            if position.player in market_data:
                current_price = market_data[position.player]['yes_price']
                self.position_manager.update_position_pnl(position.position_id, current_price)
                
                # Check exit conditions
                if self._should_exit_position(position, state, current_price):
                    positions_to_close.append(position)
        
        # Close positions
        for position in positions_to_close:
            self._close_position(position, market_data)
    
    def _should_exit_position(self, position: Position, state: ValidatedMatchState, 
                             current_price: float) -> bool:
        """Check if position should be closed"""
        # Game completion
        if state.is_service_game_start() and position.stage.value == "service_game_start":
            return True
        
        # Time-based exit (5 minutes)
        if (datetime.now() - position.entry_time).total_seconds() > 300:
            return True
        
        # Profit/loss thresholds
        if position.direction in [TradeDirection.BUY_YES, TradeDirection.BUY_NO]:
            pnl_pct = (current_price - position.entry_price) / position.entry_price
        else:
            pnl_pct = (position.entry_price - current_price) / position.entry_price
        
        if abs(pnl_pct) > self.config.exit_threshold:
            return True
        
        return False
    
    def _close_position(self, position: Position, market_data: Dict):
        """Close a position"""
        if position.player not in market_data:
            return
        
        exit_price = market_data[position.player]['yes_price']
        
        # Apply slippage
        if position.direction in [TradeDirection.BUY_YES, TradeDirection.BUY_NO]:
            exit_price *= (1 + self.config.slippage_rate)
        else:
            exit_price *= (1 - self.config.slippage_rate)
        
        # Close position
        if self.position_manager.close_position(position.position_id, exit_price):
            # Calculate P&L
            if position.direction in [TradeDirection.BUY_YES, TradeDirection.BUY_NO]:
                pnl = (exit_price - position.entry_price) * position.quantity
            else:
                pnl = (position.entry_price - exit_price) * position.quantity
            
            # Apply commission
            commission = abs(pnl) * self.config.commission_rate
            pnl -= commission
            
            # Update capital
            self.current_capital += pnl
            
            # Log trade
            self.trade_log.append({
                'timestamp': datetime.now(),
                'action': 'CLOSE',
                'position_id': position.position_id,
                'match_id': position.match_id,
                'player': position.player,
                'direction': position.direction.value,
                'quantity': position.quantity,
                'entry_price': position.entry_price,
                'exit_price': exit_price,
                'pnl': pnl,
                'commission': commission,
                'capital_after': self.current_capital
            })
            
            # Remove from active positions
            del self.positions[position.position_id]
    
    def _check_risk_limits(self):
        """Check risk limits and trigger circuit breaker if needed"""
        self.risk_manager.update_risk_metrics(list(self.positions.values()))
        
        if self.risk_manager.check_circuit_breaker():
            logger.critical("Circuit breaker triggered in backtest")
            # Close all positions
            for position in list(self.positions.values()):
                self._close_position(position, {})
    
    def _update_equity_curve(self, timestamp: datetime):
        """Update equity curve"""
        self.equity_curve.append((timestamp, self.current_capital))
    
    def _calculate_results(self) -> BacktestResult:
        """Calculate backtest results"""
        result = BacktestResult()
        result.config = self.config
        result.end_time = datetime.now()
        
        # Basic metrics
        result.total_return = (self.current_capital - self.config.initial_capital) / self.config.initial_capital
        
        # Calculate annualized return
        days = (self.config.end_date - self.config.start_date).days
        if days > 0:
            result.annualized_return = (1 + result.total_return) ** (365 / days) - 1
        
        # Trade statistics
        trades = [log for log in self.trade_log if log['action'] == 'CLOSE']
        result.total_trades = len(trades)
        
        if trades:
            winning_trades = [t for t in trades if t['pnl'] > 0]
            losing_trades = [t for t in trades if t['pnl'] < 0]
            
            result.winning_trades = len(winning_trades)
            result.losing_trades = len(losing_trades)
            result.win_rate = len(winning_trades) / len(trades)
            
            if winning_trades:
                result.average_win = np.mean([t['pnl'] for t in winning_trades])
            if losing_trades:
                result.average_loss = np.mean([t['pnl'] for t in losing_trades])
        
        # Calculate daily returns
        if self.equity_curve:
            daily_returns = []
            for i in range(1, len(self.equity_curve)):
                prev_equity = self.equity_curve[i-1][1]
                curr_equity = self.equity_curve[i][1]
                daily_return = (curr_equity - prev_equity) / prev_equity
                daily_returns.append(daily_return)
            
            result.daily_returns = daily_returns
            
            if daily_returns:
                result.volatility = np.std(daily_returns) * np.sqrt(252)  # Annualized
                
                if result.volatility > 0:
                    result.sharpe_ratio = result.annualized_return / result.volatility
        
        # Calculate max drawdown
        if self.equity_curve:
            equity_values = [point[1] for point in self.equity_curve]
            peak = equity_values[0]
            max_dd = 0
            
            for value in equity_values:
                if value > peak:
                    peak = value
                dd = (peak - value) / peak
                if dd > max_dd:
                    max_dd = dd
            
            result.max_drawdown = max_dd
        
        # Copy detailed results
        result.equity_curve = self.equity_curve
        result.trade_log = self.trade_log
        
        return result


# Test the backtesting framework
if __name__ == "__main__":
    print("Testing Backtesting Framework...")
    
    # Create backtest configuration
    config = BacktestConfig(
        start_date=datetime.now() - timedelta(days=1),
        end_date=datetime.now(),
        initial_capital=10000.0,
        commission_rate=0.01,
        slippage_rate=0.005,
        max_position_size=100.0,
        max_total_exposure=1000.0,
        max_drawdown=0.15,
        entry_threshold=0.02,
        exit_threshold=0.05
    )
    
    # Create backtest engine
    engine = BacktestEngine(config)
    
    # Run backtest
    match_ids = ["match1", "match2", "match3"]
    result = engine.run_backtest(match_ids)
    
    # Print results
    print(f"Backtest Results:")
    print(f"Total Return: {result.total_return:.2%}")
    print(f"Annualized Return: {result.annualized_return:.2%}")
    print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
    print(f"Max Drawdown: {result.max_drawdown:.2%}")
    print(f"Win Rate: {result.win_rate:.2%}")
    print(f"Total Trades: {result.total_trades}")
    print(f"Winning Trades: {result.winning_trades}")
    print(f"Losing Trades: {result.losing_trades}")
    print(f"Average Win: {result.average_win:.2f}")
    print(f"Average Loss: {result.average_loss:.2f}")
    print(f"Volatility: {result.volatility:.2%}")
    
    print(f"\nTrade Log Sample:")
    for trade in result.trade_log[:5]:  # Show first 5 trades
        print(f"{trade['timestamp']}: {trade['action']} {trade['player']} @ {trade.get('price', trade.get('exit_price', 'N/A'))}")
    
    print("\nBacktesting Framework test complete!")
