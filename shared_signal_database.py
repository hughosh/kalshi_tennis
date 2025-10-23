"""
Shared Signal Database for Tennis Trading System

This module provides a shared signal database that can be used by both
the signal generator and web portal to store and retrieve trading signals.
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class SignalRecord:
    """Record of a trading signal with outcome tracking"""
    id: str
    timestamp: datetime
    match_id: str
    player_names: tuple
    tournament: str
    signal: str  # "Buy Player1", "Sell Player1", etc.
    direction: str  # "YES" or "NO"
    stage: str  # "Service Game", "Break Point", etc.
    edge: float
    expected_value: float
    confidence: float
    current_odds: Optional[float] = None
    outcome: Optional[str] = None  # "Win", "Loss", "Pending"
    match_result: Optional[str] = None
    notes: Optional[str] = None

class SharedSignalDatabase:
    """Shared signal database with file persistence"""
    
    def __init__(self, db_file: str = "signals_database.json"):
        self.db_file = Path(db_file)
        self.signals: List[SignalRecord] = []
        self.match_results: Dict[str, str] = {}  # match_id -> result
        self.last_update = datetime.now()
        
        # Load existing data
        self.load_from_file()
    
    def load_from_file(self):
        """Load signals from JSON file"""
        if self.db_file.exists():
            try:
                with open(self.db_file, 'r') as f:
                    data = json.load(f)
                
                # Convert back to SignalRecord objects
                self.signals = []
                for signal_data in data.get('signals', []):
                    # Convert timestamp string back to datetime
                    signal_data['timestamp'] = datetime.fromisoformat(signal_data['timestamp'])
                    # Convert tuple back from list
                    signal_data['player_names'] = tuple(signal_data['player_names'])
                    self.signals.append(SignalRecord(**signal_data))
                
                self.match_results = data.get('match_results', {})
                logger.info(f"Loaded {len(self.signals)} signals from {self.db_file}")
                
            except Exception as e:
                logger.error(f"Error loading signals database: {e}")
                self.signals = []
                self.match_results = {}
    
    def reload_from_file(self) -> None:
        """Reload signals from JSON file (useful for web portal)"""
        self.load_from_file()
    
    def save_to_file(self):
        """Save signals to JSON file"""
        try:
            # Convert SignalRecord objects to dictionaries
            signals_data = []
            for signal in self.signals:
                signal_dict = asdict(signal)
                # Convert datetime to string
                signal_dict['timestamp'] = signal.timestamp.isoformat()
                # Convert tuple to list for JSON serialization
                signal_dict['player_names'] = list(signal.player_names)
                signals_data.append(signal_dict)
            
            data = {
                'signals': signals_data,
                'match_results': self.match_results,
                'last_update': self.last_update.isoformat()
            }
            
            with open(self.db_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Saved {len(self.signals)} signals to {self.db_file}")
            
        except Exception as e:
            logger.error(f"Error saving signals database: {e}")
    
    def add_signal(self, signal, match_state) -> str:
        """Add a new signal to the database"""
        signal_id = f"signal_{len(self.signals)}_{int(time.time())}"
        
        # Determine Kalshi position based on signal
        if signal.direction.value in ["buy_yes", "buy_no"]:
            kalshi_position = "YES" if signal.direction.value == "buy_yes" else "NO"
            signal_text = f"Buy {signal.player}"
        else:  # sell_yes, sell_no
            kalshi_position = "YES" if signal.direction.value == "sell_yes" else "NO"
            signal_text = f"Sell {signal.player}"
        
        record = SignalRecord(
            id=signal_id,
            timestamp=datetime.now(),
            match_id=match_state.match_id,
            player_names=(match_state.player_names[0], match_state.player_names[1]),
            tournament=getattr(match_state, 'tournament', 'Unknown Tournament'),
            signal=signal_text,
            direction=kalshi_position,
            stage=signal.stage.value,
            edge=signal.edge,
            expected_value=signal.expected_value,
            confidence=signal.confidence,
            outcome="Pending"
        )
        
        self.signals.append(record)
        self.last_update = datetime.now()
        
        # Save to file
        self.save_to_file()
        
        logger.info(f"Added signal {signal_id}: {signal_text}")
        return signal_id
    
    def get_signals(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent signals as dictionaries"""
        recent_signals = sorted(self.signals, key=lambda x: x.timestamp, reverse=True)[:limit]
        return [asdict(signal) for signal in recent_signals]
    
    def get_signals_by_match(self, match_id: str) -> List[Dict[str, Any]]:
        """Get all signals for a specific match"""
        match_signals = [s for s in self.signals if s.match_id == match_id]
        return [asdict(signal) for signal in match_signals]
    
    def update_signal_outcome(self, signal_id: str, outcome: str, notes: str = None) -> bool:
        """
        Update the outcome of a specific signal.
        
        Args:
            signal_id: ID of the signal to update
            outcome: New outcome (Win, Loss, etc.)
            notes: Optional notes about the outcome
            
        Returns:
            True if signal was found and updated, False otherwise
        """
        for signal in self.signals:
            if signal.id == signal_id:
                signal.outcome = outcome
                if notes:
                    signal.notes = notes
                self.last_update = datetime.now()
                self.save_to_file()
                logger.info(f"Updated signal {signal_id} outcome to {outcome}")
                return True
        
        logger.warning(f"Signal {signal_id} not found for outcome update")
        return False
    
    def update_outcome(self, match_id: str, result: str):
        self.match_results[match_id] = result
        
        # Update all signals for this match
        updated_count = 0
        for signal in self.signals:
            if signal.match_id == match_id and signal.outcome == "Pending":
                # Simple outcome logic - this would need to be more sophisticated
                # For now, just mark as completed
                signal.outcome = "Completed"
                signal.match_result = result
                signal.notes = f"Match result: {result}"
                updated_count += 1
        
        self.last_update = datetime.now()
        self.save_to_file()
        
        logger.info(f"Updated {updated_count} signal outcomes for match {match_id}: {result}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get trading statistics"""
        if not self.signals:
            return {
                'total_signals': 0,
                'win_rate': 0,
                'total_edge': 0,
                'avg_confidence': 0,
                'completed_signals': 0,
                'pending_signals': 0
            }
        
        completed_signals = [s for s in self.signals if s.outcome != "Pending"]
        wins = len([s for s in completed_signals if s.outcome == "Win"])
        
        return {
            'total_signals': len(self.signals),
            'completed_signals': len(completed_signals),
            'win_rate': round(wins / len(completed_signals) * 100, 1) if completed_signals else 0,
            'total_edge': round(sum(s.edge for s in self.signals), 3),
            'avg_confidence': round(sum(s.confidence for s in self.signals) / len(self.signals), 3),
            'pending_signals': len([s for s in self.signals if s.outcome == "Pending"])
        }
    
    def clear_old_signals(self, days: int = 7):
        """Clear signals older than specified days"""
        cutoff_date = datetime.now() - timedelta(days=days)
        old_count = len(self.signals)
        
        self.signals = [s for s in self.signals if s.timestamp > cutoff_date]
        
        removed_count = old_count - len(self.signals)
        if removed_count > 0:
            self.save_to_file()
            logger.info(f"Cleared {removed_count} signals older than {days} days")
    
    def clear_database(self) -> None:
        """Clear all signals and match results from the database"""
        self.signals = []
        self.match_results = {}
        self.last_update = datetime.now()
        self.save_to_file()
        logger.info("Database cleared successfully")

# Global instance
signal_db = SharedSignalDatabase()

def get_signal_database() -> SharedSignalDatabase:
    """Get the global signal database instance"""
    return signal_db
