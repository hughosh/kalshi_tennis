"""
Comprehensive Risk Management System

This module implements advanced risk management including:
- Position limits and correlation tracking
- Drawdown protection and adverse selection handling
- Portfolio-level risk monitoring
- Real-time risk alerts and circuit breakers
"""

from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import logging
import numpy as np
from collections import defaultdict, deque
from trading.multi_stage_trading import Position, TradeDirection
from execution.order_execution import OrderManager, PositionManager

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskAlert(Enum):
    POSITION_LIMIT_EXCEEDED = "position_limit_exceeded"
    CORRELATION_RISK = "correlation_risk"
    DRAWDOWN_THRESHOLD = "drawdown_threshold"
    ADVERSE_SELECTION = "adverse_selection"
    VOLATILITY_SPIKE = "volatility_spike"
    LIQUIDITY_RISK = "liquidity_risk"


@dataclass
class RiskMetrics:
    """Comprehensive risk metrics"""
    # Position metrics
    total_exposure: float = 0.0
    net_exposure: float = 0.0
    gross_exposure: float = 0.0
    position_count: int = 0
    
    # Risk metrics
    var_95: float = 0.0  # Value at Risk 95%
    expected_shortfall: float = 0.0
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    
    # Correlation metrics
    max_correlation: float = 0.0
    correlation_clusters: int = 0
    
    # Performance metrics
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    monthly_pnl: float = 0.0
    sharpe_ratio: float = 0.0
    
    # Timestamps
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RiskAlert:
    """Risk alert with severity and details"""
    alert_type: RiskAlert
    severity: RiskLevel
    message: str
    timestamp: datetime
    position_ids: List[str] = field(default_factory=list)
    suggested_action: str = ""
    is_active: bool = True


class CorrelationTracker:
    """
    Tracks correlation between positions and markets.
    
    Identifies when positions are too correlated and pose concentration risk.
    """
    
    def __init__(self, max_correlation: float = 0.7):
        self.max_correlation = max_correlation
        self.position_correlations: Dict[str, Dict[str, float]] = defaultdict(dict)
        self.market_correlations: Dict[str, Dict[str, float]] = defaultdict(dict)
        
        # Correlation history for analysis
        self.correlation_history: deque = deque(maxlen=1000)
        
    def update_correlation(self, position1_id: str, position2_id: str, correlation: float):
        """Update correlation between two positions"""
        self.position_correlations[position1_id][position2_id] = correlation
        self.position_correlations[position2_id][position1_id] = correlation
        
        # Store in history
        self.correlation_history.append({
            'timestamp': datetime.now(),
            'position1': position1_id,
            'position2': position2_id,
            'correlation': correlation
        })
    
    def get_correlation_clusters(self, positions: List[Position]) -> List[List[str]]:
        """
        Identify correlation clusters in current positions.
        
        Returns:
            List of position ID clusters that are highly correlated
        """
        clusters = []
        processed = set()
        
        for position in positions:
            if position.position_id in processed:
                continue
            
            cluster = [position.position_id]
            processed.add(position.position_id)
            
            # Find all positions correlated with this one
            for other_position in positions:
                if other_position.position_id in processed:
                    continue
                
                correlation = self.position_correlations.get(position.position_id, {}).get(other_position.position_id, 0.0)
                
                if abs(correlation) > self.max_correlation:
                    cluster.append(other_position.position_id)
                    processed.add(other_position.position_id)
            
            if len(cluster) > 1:
                clusters.append(cluster)
        
        return clusters
    
    def calculate_portfolio_correlation_risk(self, positions: List[Position]) -> float:
        """Calculate overall portfolio correlation risk"""
        if len(positions) < 2:
            return 0.0
        
        # Calculate average correlation
        total_correlation = 0.0
        correlation_count = 0
        
        for i, pos1 in enumerate(positions):
            for j, pos2 in enumerate(positions[i+1:], i+1):
                correlation = self.position_correlations.get(pos1.position_id, {}).get(pos2.position_id, 0.0)
                total_correlation += abs(correlation)
                correlation_count += 1
        
        return total_correlation / max(1, correlation_count)


class DrawdownTracker:
    """
    Tracks portfolio drawdown and implements protection measures.
    """
    
    def __init__(self, max_drawdown: float = 0.15, lookback_days: int = 30):
        self.max_drawdown = max_drawdown
        self.lookback_days = lookback_days
        
        # P&L history
        self.pnl_history: deque = deque(maxlen=lookback_days * 24)  # Hourly data
        self.peak_value = 0.0
        self.current_value = 0.0
        
        # Drawdown statistics
        self.max_drawdown_seen = 0.0
        self.current_drawdown = 0.0
        self.drawdown_start_time: Optional[datetime] = None
        
    def update_pnl(self, pnl: float, timestamp: Optional[datetime] = None):
        """Update P&L and recalculate drawdown metrics"""
        if timestamp is None:
            timestamp = datetime.now()
        
        self.pnl_history.append({
            'timestamp': timestamp,
            'pnl': pnl
        })
        
        self.current_value = pnl
        
        # Update peak value
        if pnl > self.peak_value:
            self.peak_value = pnl
            self.drawdown_start_time = None
        
        # Calculate current drawdown
        if self.peak_value > 0:
            self.current_drawdown = (self.peak_value - pnl) / self.peak_value
        else:
            self.current_drawdown = 0.0
        
        # Update max drawdown
        if self.current_drawdown > self.max_drawdown_seen:
            self.max_drawdown_seen = self.current_drawdown
            if self.drawdown_start_time is None:
                self.drawdown_start_time = timestamp
    
    def is_drawdown_threshold_exceeded(self) -> bool:
        """Check if drawdown threshold is exceeded"""
        return self.current_drawdown > self.max_drawdown
    
    def get_drawdown_duration(self) -> Optional[timedelta]:
        """Get duration of current drawdown"""
        if self.drawdown_start_time is None:
            return None
        
        return datetime.now() - self.drawdown_start_time
    
    def get_recovery_probability(self) -> float:
        """Estimate probability of recovering from current drawdown"""
        if self.current_drawdown == 0:
            return 1.0
        
        # Simple heuristic based on drawdown magnitude
        if self.current_drawdown < 0.05:
            return 0.9
        elif self.current_drawdown < 0.10:
            return 0.7
        elif self.current_drawdown < 0.15:
            return 0.5
        else:
            return 0.3


class AdverseSelectionDetector:
    """
    Detects adverse selection in trading patterns.
    
    Identifies when the market is moving against our positions systematically.
    """
    
    def __init__(self, lookback_periods: int = 20):
        self.lookback_periods = lookback_periods
        self.trade_outcomes: deque = deque(maxlen=lookback_periods)
        self.market_movements: deque = deque(maxlen=lookback_periods)
        
    def record_trade_outcome(self, position: Position, exit_price: float, 
                           market_movement: float):
        """Record trade outcome and market movement"""
        # Calculate trade outcome
        if position.direction in [TradeDirection.BUY_YES, TradeDirection.BUY_NO]:
            trade_outcome = exit_price - position.entry_price
        else:
            trade_outcome = position.entry_price - exit_price
        
        self.trade_outcomes.append(trade_outcome)
        self.market_movements.append(market_movement)
    
    def detect_adverse_selection(self) -> Tuple[bool, float]:
        """
        Detect if there's systematic adverse selection.
        
        Returns:
            (is_adverse_selection, correlation_score)
        """
        if len(self.trade_outcomes) < 10:
            return False, 0.0
        
        # Calculate correlation between trade outcomes and market movements
        outcomes = np.array(self.trade_outcomes)
        movements = np.array(self.market_movements)
        
        correlation = np.corrcoef(outcomes, movements)[0, 1]
        
        # Adverse selection if correlation is strongly negative
        is_adverse = correlation < -0.5
        
        return is_adverse, correlation


class RiskManager:
    """
    Comprehensive risk management system.
    
    Integrates all risk components and provides centralized risk monitoring.
    """
    
    def __init__(self, 
                 max_total_exposure: float = 1000.0,
                 max_position_size: float = 100.0,
                 max_correlation: float = 0.7,
                 max_drawdown: float = 0.15,
                 max_daily_loss: float = 200.0):
        
        # Risk limits
        self.max_total_exposure = max_total_exposure
        self.max_position_size = max_position_size
        self.max_correlation = max_correlation
        self.max_drawdown = max_drawdown
        self.max_daily_loss = max_daily_loss
        
        # Risk components
        self.correlation_tracker = CorrelationTracker(max_correlation)
        self.drawdown_tracker = DrawdownTracker(max_drawdown)
        self.adverse_selection_detector = AdverseSelectionDetector()
        
        # Risk state
        self.active_alerts: List[RiskAlert] = []
        self.risk_metrics = RiskMetrics()
        self.circuit_breaker_active = False
        
        # Statistics
        self.total_risk_checks = 0
        self.risk_violations = 0
        self.circuit_breaker_triggers = 0
        
        logger.info("RiskManager initialized")
    
    def check_position_risk(self, position: Position, 
                           existing_positions: List[Position]) -> Tuple[bool, List[str]]:
        """
        Check if new position violates risk limits.
        
        Args:
            position: New position to check
            existing_positions: Current positions
        
        Returns:
            (is_safe, violation_reasons)
        """
        violations = []
        
        # Check position size
        if position.quantity > self.max_position_size:
            violations.append(f"Position size {position.quantity} exceeds limit {self.max_position_size}")
        
        # Check total exposure
        current_exposure = sum(p.quantity * p.entry_price for p in existing_positions)
        new_exposure = current_exposure + (position.quantity * position.entry_price)
        
        if new_exposure > self.max_total_exposure:
            violations.append(f"Total exposure {new_exposure:.2f} exceeds limit {self.max_total_exposure}")
        
        # Check correlation risk
        if len(existing_positions) > 0:
            correlation_clusters = self.correlation_tracker.get_correlation_clusters(existing_positions + [position])
            
            for cluster in correlation_clusters:
                if len(cluster) > 3:  # Too many correlated positions
                    violations.append(f"Correlation cluster with {len(cluster)} positions")
        
        # Check drawdown
        if self.drawdown_tracker.is_drawdown_threshold_exceeded():
            violations.append(f"Drawdown {self.drawdown_tracker.current_drawdown:.2%} exceeds limit {self.max_drawdown:.2%}")
        
        # Check daily loss
        daily_pnl = self._calculate_daily_pnl(existing_positions)
        if daily_pnl < -self.max_daily_loss:
            violations.append(f"Daily loss {daily_pnl:.2f} exceeds limit {self.max_daily_loss}")
        
        is_safe = len(violations) == 0
        
        self.total_risk_checks += 1
        if not is_safe:
            self.risk_violations += 1
        
        return is_safe, violations
    
    def update_risk_metrics(self, positions: List[Position]):
        """Update comprehensive risk metrics"""
        # Position metrics
        self.risk_metrics.position_count = len(positions)
        self.risk_metrics.total_exposure = sum(p.quantity * p.entry_price for p in positions)
        
        # Calculate net and gross exposure
        buy_exposure = sum(p.quantity * p.entry_price for p in positions 
                          if p.direction in [TradeDirection.BUY_YES, TradeDirection.BUY_NO])
        sell_exposure = sum(p.quantity * p.entry_price for p in positions 
                           if p.direction in [TradeDirection.SELL_YES, TradeDirection.SELL_NO])
        
        self.risk_metrics.net_exposure = abs(buy_exposure - sell_exposure)
        self.risk_metrics.gross_exposure = buy_exposure + sell_exposure
        
        # Drawdown metrics
        total_pnl = sum(p.pnl for p in positions)
        self.drawdown_tracker.update_pnl(total_pnl)
        
        self.risk_metrics.current_drawdown = self.drawdown_tracker.current_drawdown
        self.risk_metrics.max_drawdown = self.drawdown_tracker.max_drawdown_seen
        
        # Correlation metrics
        correlation_clusters = self.correlation_tracker.get_correlation_clusters(positions)
        self.risk_metrics.correlation_clusters = len(correlation_clusters)
        
        if len(positions) > 1:
            self.risk_metrics.max_correlation = self.correlation_tracker.calculate_portfolio_correlation_risk(positions)
        
        # Performance metrics
        self.risk_metrics.daily_pnl = self._calculate_daily_pnl(positions)
        self.risk_metrics.weekly_pnl = self._calculate_weekly_pnl(positions)
        self.risk_metrics.monthly_pnl = self._calculate_monthly_pnl(positions)
        
        # Update timestamp
        self.risk_metrics.timestamp = datetime.now()
    
    def check_circuit_breaker(self) -> bool:
        """Check if circuit breaker should be triggered"""
        triggers = []
        
        # Drawdown trigger
        if self.drawdown_tracker.current_drawdown > self.max_drawdown * 1.5:
            triggers.append("Excessive drawdown")
        
        # Daily loss trigger
        if self.risk_metrics.daily_pnl < -self.max_daily_loss * 1.5:
            triggers.append("Excessive daily loss")
        
        # Correlation trigger
        if self.risk_metrics.max_correlation > self.max_correlation * 1.2:
            triggers.append("Excessive correlation")
        
        # Adverse selection trigger
        is_adverse, correlation = self.adverse_selection_detector.detect_adverse_selection()
        if is_adverse:
            triggers.append("Adverse selection detected")
        
        if triggers:
            self.circuit_breaker_active = True
            self.circuit_breaker_triggers += 1
            
            logger.critical(f"Circuit breaker triggered: {', '.join(triggers)}")
            return True
        
        return False
    
    def reset_circuit_breaker(self):
        """Reset circuit breaker (manual intervention required)"""
        self.circuit_breaker_active = False
        logger.info("Circuit breaker reset")
    
    def _calculate_daily_pnl(self, positions: List[Position]) -> float:
        """Calculate daily P&L"""
        today = datetime.now().date()
        return sum(p.pnl for p in positions if p.entry_time.date() == today)
    
    def _calculate_weekly_pnl(self, positions: List[Position]) -> float:
        """Calculate weekly P&L"""
        week_ago = datetime.now() - timedelta(days=7)
        return sum(p.pnl for p in positions if p.entry_time > week_ago)
    
    def _calculate_monthly_pnl(self, positions: List[Position]) -> float:
        """Calculate monthly P&L"""
        month_ago = datetime.now() - timedelta(days=30)
        return sum(p.pnl for p in positions if p.entry_time > month_ago)
    
    def get_risk_summary(self) -> Dict[str, Any]:
        """Get comprehensive risk summary"""
        return {
            'risk_metrics': {
                'total_exposure': self.risk_metrics.total_exposure,
                'net_exposure': self.risk_metrics.net_exposure,
                'position_count': self.risk_metrics.position_count,
                'current_drawdown': f"{self.risk_metrics.current_drawdown:.2%}",
                'max_drawdown': f"{self.risk_metrics.max_drawdown:.2%}",
                'max_correlation': self.risk_metrics.max_correlation,
                'correlation_clusters': self.risk_metrics.correlation_clusters,
                'daily_pnl': self.risk_metrics.daily_pnl,
                'weekly_pnl': self.risk_metrics.weekly_pnl,
                'monthly_pnl': self.risk_metrics.monthly_pnl
            },
            'risk_limits': {
                'max_total_exposure': self.max_total_exposure,
                'max_position_size': self.max_position_size,
                'max_correlation': self.max_correlation,
                'max_drawdown': f"{self.max_drawdown:.2%}",
                'max_daily_loss': self.max_daily_loss
            },
            'circuit_breaker': {
                'active': self.circuit_breaker_active,
                'triggers': self.circuit_breaker_triggers
            },
            'statistics': {
                'total_risk_checks': self.total_risk_checks,
                'risk_violations': self.risk_violations,
                'violation_rate': f"{(self.risk_violations / max(1, self.total_risk_checks)) * 100:.1f}%"
            }
        }


# Test the risk management system
if __name__ == "__main__":
    print("Testing Comprehensive Risk Management...")
    
    from multi_stage_trading import Position, TradeDirection, TradeStage
    
    # Create risk manager
    risk_manager = RiskManager(
        max_total_exposure=1000.0,
        max_position_size=100.0,
        max_correlation=0.7,
        max_drawdown=0.15,
        max_daily_loss=200.0
    )
    
    # Create test positions
    positions = [
        Position(
            position_id="pos1",
            match_id="match1",
            player="Djokovic",
            direction=TradeDirection.BUY_YES,
            quantity=50,
            entry_price=0.55,
            entry_probability=0.65,
            entry_time=datetime.now(),
            stage=TradeStage.SERVICE_GAME_START,
            pnl=10.0
        ),
        Position(
            position_id="pos2",
            match_id="match2",
            player="Sinner",
            direction=TradeDirection.BUY_YES,
            quantity=75,
            entry_price=0.60,
            entry_probability=0.70,
            entry_time=datetime.now(),
            stage=TradeStage.SERVICE_GAME_START,
            pnl=-5.0
        )
    ]
    
    # Test risk checking
    new_position = Position(
        position_id="pos3",
        match_id="match3",
        player="Medvedev",
        direction=TradeDirection.BUY_YES,
        quantity=200,  # Exceeds limit
        entry_price=0.50,
        entry_probability=0.60,
        entry_time=datetime.now(),
        stage=TradeStage.SERVICE_GAME_START
    )
    
    is_safe, violations = risk_manager.check_position_risk(new_position, positions)
    print(f"Position safe: {is_safe}")
    print(f"Violations: {violations}")
    
    # Test risk metrics
    risk_manager.update_risk_metrics(positions)
    print(f"Risk metrics: {risk_manager.risk_metrics}")
    
    # Test circuit breaker
    circuit_breaker_triggered = risk_manager.check_circuit_breaker()
    print(f"Circuit breaker triggered: {circuit_breaker_triggered}")
    
    # Test risk summary
    risk_summary = risk_manager.get_risk_summary()
    print(f"Risk summary: {risk_summary}")
    
    print("\nComprehensive Risk Management test complete!")
