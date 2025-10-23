"""
Complete Data Pipeline

This module orchestrates the complete data flow from feeds to trading strategy
with proper error handling, validation, and reconciliation.
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging
import time
from dataclasses import dataclass
from data.data_integration import TennisDataFeed, ValidatedMatchState, FeedStatus
from data.state_reconciliation import StateReconciliation, ReconciliationResult

logger = logging.getLogger(__name__)


@dataclass
class PipelineStatistics:
    """Statistics for the data pipeline"""
    total_updates: int = 0
    successful_updates: int = 0
    failed_updates: int = 0
    validation_failures: int = 0
    reconciliation_failures: int = 0
    stale_data_rejections: int = 0
    last_update: Optional[datetime] = None
    average_latency_ms: float = 0.0


class TennisDataPipeline:
    """
    Orchestrates data flow from feeds to trading strategy.
    
    Features:
    - Primary and backup feed support
    - Data validation and staleness detection
    - State reconciliation with Kalshi
    - Error handling and recovery
    - Performance monitoring
    """
    
    def __init__(self,
                 primary_feed: TennisDataFeed,
                 backup_feed: Optional[TennisDataFeed] = None,
                 reconciler: Optional[StateReconciliation] = None,
                 max_staleness_seconds: float = 5.0):
        
        self.primary_feed = primary_feed
        self.backup_feed = backup_feed
        self.reconciler = reconciler
        self.max_staleness_seconds = max_staleness_seconds
        
        # State storage
        self.canonical_states: Dict[str, ValidatedMatchState] = {}
        self.state_history: Dict[str, List[ValidatedMatchState]] = {}
        self.market_mappings: Dict[str, str] = {}  # match_id -> market_id
        
        # Statistics
        self.stats = PipelineStatistics()
        self.latency_samples: List[float] = []
        
        # Configuration
        self.max_history_per_match = 100
        self.enable_reconciliation = reconciler is not None
        self.enable_backup_feed = backup_feed is not None
        
        logger.info("TennisDataPipeline initialized")
        logger.info(f"Primary feed: {type(primary_feed).__name__}")
        logger.info(f"Backup feed: {type(backup_feed).__name__ if backup_feed else 'None'}")
        logger.info(f"Reconciliation: {'Enabled' if self.enable_reconciliation else 'Disabled'}")
    
    def get_state(self, match_id: str) -> Optional[ValidatedMatchState]:
        """
        Get current validated state for match.
        
        Process:
        1. Fetch from primary feed
        2. Validate data
        3. Reconcile with Kalshi (if configured)
        4. Fallback to backup feed if primary fails
        5. Store in canonical state
        """
        start_time = time.time()
        
        try:
            state = None
            
            # Try primary feed
            try:
                state = self.primary_feed.get_match_state(match_id)
                if state:
                    logger.debug(f"Primary feed provided state for {match_id}")
            except Exception as e:
                logger.warning(f"Primary feed failed for {match_id}: {e}")
                
                # Try backup feed
                if self.enable_backup_feed:
                    try:
                        state = self.backup_feed.get_match_state(match_id)
                        if state:
                            logger.info(f"Using backup feed for {match_id}")
                    except Exception as e2:
                        logger.error(f"Backup feed also failed: {e2}")
            
            if state is None:
                logger.warning(f"No state data available for {match_id}")
                self.stats.failed_updates += 1
                return None
            
            # Check staleness
            if state.is_stale(self.max_staleness_seconds):
                logger.warning(f"State for {match_id} is stale ({state.staleness_seconds:.1f}s)")
                self.stats.stale_data_rejections += 1
                return None
            
            # Validate state
            if not state.validation_passed:
                logger.warning(f"State validation failed for {match_id}: {state.validation_errors}")
                self.stats.validation_failures += 1
                return None
            
            # Reconcile with Kalshi (if configured)
            if self.enable_reconciliation and match_id in self.market_mappings:
                market_id = self.market_mappings[match_id]
                reconciliation_result = self.reconciler.reconcile(state, market_id)
                
                if not reconciliation_result.is_consistent:
                    logger.warning(f"Reconciliation failed for {match_id}: {reconciliation_result.issues}")
                    self.stats.reconciliation_failures += 1
                    # Don't reject state, but flag for review
            
            # Store canonical state
            self.canonical_states[match_id] = state
            
            # Store history
            if match_id not in self.state_history:
                self.state_history[match_id] = []
            self.state_history[match_id].append(state)
            
            # Trim history
            if len(self.state_history[match_id]) > self.max_history_per_match:
                self.state_history[match_id] = self.state_history[match_id][-self.max_history_per_match:]
            
            # Update statistics
            self.stats.total_updates += 1
            self.stats.successful_updates += 1
            self.stats.last_update = datetime.now()
            
            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000
            self.latency_samples.append(latency_ms)
            if len(self.latency_samples) > 100:
                self.latency_samples = self.latency_samples[-100:]
            
            self.stats.average_latency_ms = sum(self.latency_samples) / len(self.latency_samples)
            
            logger.debug(f"Successfully updated state for {match_id} in {latency_ms:.1f}ms")
            return state
            
        except Exception as e:
            logger.error(f"Pipeline error for {match_id}: {e}")
            self.stats.failed_updates += 1
            return None
    
    def get_state_change(self, match_id: str) -> Optional[Tuple[ValidatedMatchState, ValidatedMatchState]]:
        """
        Get previous and current state for detecting transitions.
        
        Returns:
            (previous_state, current_state) or None
        """
        history = self.state_history.get(match_id, [])
        if len(history) < 2:
            return None
        
        return (history[-2], history[-1])
    
    def detect_service_game_start(self, match_id: str) -> bool:
        """Detect if match just started a new service game"""
        change = self.get_state_change(match_id)
        if not change:
            return False
        
        prev, current = change
        
        # Check if previous was not 0-0 but current is 0-0
        return (not prev.is_service_game_start() and 
                current.is_service_game_start())
    
    def detect_game_completion(self, match_id: str) -> bool:
        """Detect if a game just completed"""
        change = self.get_state_change(match_id)
        if not change:
            return False
        
        prev, current = change
        
        # Check if points reset to 0-0 (game completed)
        return (prev.points != (0, 0) and 
                current.points == (0, 0))
    
    def detect_set_completion(self, match_id: str) -> bool:
        """Detect if a set just completed"""
        change = self.get_state_change(match_id)
        if not change:
            return False
        
        prev, current = change
        
        # Check if games reset to 0-0 (set completed)
        return (prev.games != (0, 0) and 
                current.games == (0, 0) and
                current.sets != prev.sets)
    
    def get_active_matches(self) -> List[str]:
        """Get list of active matches from primary feed"""
        try:
            return self.primary_feed.get_active_matches()
        except Exception as e:
            logger.error(f"Failed to get active matches: {e}")
            if self.enable_backup_feed:
                try:
                    return self.backup_feed.get_active_matches()
                except Exception as e2:
                    logger.error(f"Backup feed also failed: {e2}")
            return []
    
    def add_market_mapping(self, match_id: str, market_id: str):
        """Add mapping between match ID and Kalshi market ID"""
        self.market_mappings[match_id] = market_id
        logger.info(f"Added market mapping: {match_id} -> {market_id}")
    
    def get_pipeline_status(self) -> Dict[str, any]:
        """Get comprehensive pipeline status"""
        primary_status = self.primary_feed.get_feed_status()
        backup_status = self.backup_feed.get_feed_status() if self.backup_feed else None
        
        return {
            'primary_feed_status': primary_status.value,
            'backup_feed_status': backup_status.value if backup_status else 'N/A',
            'reconciliation_enabled': self.enable_reconciliation,
            'canonical_states_count': len(self.canonical_states),
            'active_mappings': len(self.market_mappings),
            'statistics': {
                'total_updates': self.stats.total_updates,
                'successful_updates': self.stats.successful_updates,
                'failed_updates': self.stats.failed_updates,
                'validation_failures': self.stats.validation_failures,
                'reconciliation_failures': self.stats.reconciliation_failures,
                'stale_data_rejections': self.stats.stale_data_rejections,
                'success_rate': (self.stats.successful_updates / max(1, self.stats.total_updates)) * 100,
                'average_latency_ms': self.stats.average_latency_ms,
                'last_update': self.stats.last_update
            }
        }
    
    def get_reconciliation_summary(self) -> Optional[Dict[str, any]]:
        """Get reconciliation summary if enabled"""
        if not self.enable_reconciliation:
            return None
        
        return self.reconciler.get_discrepancy_summary()
    
    def cleanup_old_data(self, max_age_hours: int = 24):
        """Clean up old state history and mappings"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        # Clean up state history
        for match_id in list(self.state_history.keys()):
            history = self.state_history[match_id]
            # Keep only recent states
            recent_history = [
                state for state in history 
                if state.timestamp > cutoff_time
            ]
            
            if recent_history:
                self.state_history[match_id] = recent_history
            else:
                del self.state_history[match_id]
        
        # Clean up canonical states
        for match_id in list(self.canonical_states.keys()):
            state = self.canonical_states[match_id]
            if state.timestamp < cutoff_time:
                del self.canonical_states[match_id]
        
        logger.info(f"Cleaned up data older than {max_age_hours} hours")


# Test the complete pipeline
if __name__ == "__main__":
    print("Testing Complete Data Pipeline...")
    
    from data_integration import FlashScoreFeed
    from state_reconciliation import MockKalshiConnector, StateReconciliation
    
    # Create components
    primary_feed = FlashScoreFeed()
    backup_feed = FlashScoreFeed()  # Same for testing
    mock_kalshi = MockKalshiConnector()
    reconciler = StateReconciliation(mock_kalshi)
    
    # Create pipeline
    pipeline = TennisDataPipeline(
        primary_feed=primary_feed,
        backup_feed=backup_feed,
        reconciler=reconciler,
        max_staleness_seconds=5.0
    )
    
    # Add market mapping
    pipeline.add_market_mapping("test_match", "test_market")
    
    # Test pipeline
    print(f"Pipeline status: {pipeline.get_pipeline_status()}")
    
    # Test state retrieval
    state = pipeline.get_state("test_match")
    if state:
        print(f"Retrieved state: {state}")
    else:
        print("No state data available")
    
    print("\nComplete Data Pipeline test complete!")
