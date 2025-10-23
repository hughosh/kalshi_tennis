"""
Corrected MatchState Implementation

This module implements the corrected MatchState with proper service tracking
and state transitions that match tennis rules exactly.
"""

from dataclasses import dataclass, replace
from typing import Tuple, Optional
from datetime import datetime
from enum import Enum
import time


class MatchFormat(Enum):
    BEST_OF_3 = "BO3"
    BEST_OF_5 = "BO5"


@dataclass(frozen=True)
class CorrectedMatchState:
    """
    Corrected match state with proper service tracking.
    
    Key fixes:
    1. Tracks total_games_played for service alternation between sets
    2. Proper tiebreak detection and handling
    3. Correct service alternation logic
    4. Immutable state transitions
    """
    
    # Match identification
    match_id: str
    player_names: Tuple[str, str]  # (server_name, receiver_name)
    match_format: MatchFormat
    
    # Current score
    sets: Tuple[int, int]  # (server_sets, receiver_sets)
    games: Tuple[int, int]  # (server_games, receiver_games) in current set
    points: Tuple[int, int]  # (server_points, receiver_points) in current game
    
    # Service state
    server_serving: bool  # True if player_names[0] serves, False if player_names[1] serves
    
    # Critical fix: Track total games for service alternation
    total_games_played: int  # Cumulative across all sets
    
    # Tiebreak state
    is_tiebreak: bool = False
    tiebreak_points: Optional[Tuple[int, int]] = None  # Only used in tiebreak
    
    # Metadata
    timestamp: float = None
    data_source: str = "corrected"
    
    def __post_init__(self):
        """Set default timestamp if not provided"""
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', time.time())
    
    @property
    def current_server_name(self) -> str:
        """Get name of current server"""
        return self.player_names[0] if self.server_serving else self.player_names[1]
    
    @property
    def current_receiver_name(self) -> str:
        """Get name of current receiver"""
        return self.player_names[1] if self.server_serving else self.player_names[0]
    
    def is_service_game_start(self) -> bool:
        """Check if this is the start of a service game (0-0 points)"""
        return self.points == (0, 0)
    
    def is_match_complete(self) -> bool:
        """Check if match is complete"""
        if self.match_format == MatchFormat.BEST_OF_3:
            return max(self.sets) >= 2
        else:  # BEST_OF_5
            return max(self.sets) >= 3
    
    def is_set_complete(self) -> bool:
        """Check if current set is complete"""
        server_games, receiver_games = self.games
        
        # Regular set completion
        if server_games >= 6 and server_games - receiver_games >= 2:
            return True
        if receiver_games >= 6 and receiver_games - server_games >= 2:
            return True
        
        # Tiebreak completion
        if self.is_tiebreak and self.tiebreak_points:
            s_pts, r_pts = self.tiebreak_points
            if s_pts >= 7 and s_pts - r_pts >= 2:
                return True
            if r_pts >= 7 and r_pts - s_pts >= 2:
                return True
        
        return False
    
    def is_game_complete(self) -> bool:
        """Check if current game is complete"""
        if self.is_tiebreak:
            if not self.tiebreak_points:
                return False
            s_pts, r_pts = self.tiebreak_points
            return (s_pts >= 7 and s_pts - r_pts >= 2) or (r_pts >= 7 and r_pts - s_pts >= 2)
        else:
            s_pts, r_pts = self.points
            return (s_pts >= 4 and s_pts - r_pts >= 2) or (r_pts >= 4 and r_pts - s_pts >= 2)
    
    def copy_with_point_won(self, winner: int) -> 'CorrectedMatchState':
        """
        Create new state after a point is won.
        
        Args:
            winner: 0 for server wins, 1 for receiver wins
        """
        if self.is_match_complete():
            return self
        
        if self.is_tiebreak:
            return self._advance_tiebreak_point(winner)
        else:
            return self._advance_regular_point(winner)
    
    def _advance_regular_point(self, winner: int) -> 'CorrectedMatchState':
        """Advance regular game point"""
        server_pts, receiver_pts = self.points
        
        if winner == 0:  # Server wins
            new_server_pts = server_pts + 1
            new_receiver_pts = receiver_pts
        else:  # Receiver wins
            new_server_pts = server_pts
            new_receiver_pts = receiver_pts + 1
        
        # Check if game is complete
        if (new_server_pts >= 4 and new_server_pts - new_receiver_pts >= 2) or \
           (new_receiver_pts >= 4 and new_receiver_pts - new_server_pts >= 2):
            return self.copy_with_game_complete(winner)
        
        return replace(
            self,
            points=(new_server_pts, new_receiver_pts),
            timestamp=time.time()
        )
    
    def _advance_tiebreak_point(self, winner: int) -> 'CorrectedMatchState':
        """Advance tiebreak point"""
        if not self.tiebreak_points:
            return self
        
        s_pts, r_pts = self.tiebreak_points
        
        if winner == 0:  # Server wins
            new_s_pts = s_pts + 1
            new_r_pts = r_pts
        else:  # Receiver wins
            new_s_pts = s_pts
            new_r_pts = r_pts + 1
        
        # Check if tiebreak is complete
        if (new_s_pts >= 7 and new_s_pts - new_r_pts >= 2) or \
           (new_r_pts >= 7 and new_r_pts - new_s_pts >= 2):
            return self.copy_with_game_complete(winner)
        
        return replace(
            self,
            tiebreak_points=(new_s_pts, new_r_pts),
            timestamp=time.time()
        )
    
    def copy_with_game_complete(self, winner: int) -> 'CorrectedMatchState':
        """
        Create new state after a game is complete.
        
        Args:
            winner: 0 for server wins, 1 for receiver wins
        """
        server_games, receiver_games = self.games
        
        if winner == 0:  # Server wins game
            new_server_games = server_games + 1
            new_receiver_games = receiver_games
        else:  # Receiver wins game
            new_server_games = server_games
            new_receiver_games = receiver_games + 1
        
        # Check if set is complete
        if (new_server_games >= 6 and new_server_games - new_receiver_games >= 2) or \
           (new_receiver_games >= 6 and new_receiver_games - new_server_games >= 2):
            return self._advance_set_completion(winner)
        
        # Check if tiebreak needed
        if new_server_games == 6 and new_receiver_games == 6:
            return self._enter_tiebreak()
        
        # Regular game completion - service alternates
        return replace(
            self,
            games=(new_server_games, new_receiver_games),
            points=(0, 0),
            server_serving=not self.server_serving,  # Service alternates
            total_games_played=self.total_games_played + 1,
            timestamp=time.time()
        )
    
    def _enter_tiebreak(self) -> 'CorrectedMatchState':
        """Enter tiebreak state"""
        return replace(
            self,
            is_tiebreak=True,
            tiebreak_points=(0, 0),
            points=(0, 0),  # Reset regular points
            timestamp=time.time()
        )
    
    def _advance_set_completion(self, set_winner: int) -> 'CorrectedMatchState':
        """
        Handle set completion and determine next server.
        
        CRITICAL FIX: Service alternation between sets depends on total games played.
        """
        server_sets, receiver_sets = self.sets
        
        if set_winner == 0:  # Server wins set
            new_server_sets = server_sets + 1
            new_receiver_sets = receiver_sets
        else:  # Receiver wins set
            new_server_sets = server_sets
            new_receiver_sets = receiver_sets + 1
        
        # Calculate total games in completed set
        games_in_set = self.games[0] + self.games[1]
        new_total_games = self.total_games_played + games_in_set
        
        # CRITICAL FIX: Determine next server based on total games
        # If odd total games in set, same relative server; if even, swap
        if (games_in_set % 2) == 1:
            # Odd games in set → same player serves first in next set
            next_server = self.server_serving
        else:
            # Even games in set → other player serves first in next set
            next_server = not self.server_serving
        
        # Check if match is complete
        if self.match_format == MatchFormat.BEST_OF_3:
            if max(new_server_sets, new_receiver_sets) >= 2:
                return replace(
                    self,
                    sets=(new_server_sets, new_receiver_sets),
                    games=(0, 0),
                    points=(0, 0),
                    server_serving=next_server,
                    total_games_played=new_total_games,
                    is_tiebreak=False,
                    tiebreak_points=None,
                    timestamp=time.time()
                )
        else:  # BEST_OF_5
            if max(new_server_sets, new_receiver_sets) >= 3:
                return replace(
                    self,
                    sets=(new_server_sets, new_receiver_sets),
                    games=(0, 0),
                    points=(0, 0),
                    server_serving=next_server,
                    total_games_played=new_total_games,
                    is_tiebreak=False,
                    tiebreak_points=None,
                    timestamp=time.time()
                )
        
        # Match continues
        return replace(
            self,
            sets=(new_server_sets, new_receiver_sets),
            games=(0, 0),
            points=(0, 0),
            server_serving=next_server,
            total_games_played=new_total_games,
            is_tiebreak=False,
            tiebreak_points=None,
            timestamp=time.time()
        )
    
    def to_key(self) -> str:
        """Create unique string key for caching"""
        if self.is_tiebreak and self.tiebreak_points:
            s_pts, r_pts = self.tiebreak_points
            return f"s{self.sets[0]}-{self.sets[1]}_g{self.games[0]}-{self.games[1]}_tb{s_pts}-{r_pts}_serving{self.server_serving}"
        else:
            s_pts, r_pts = self.points
            return f"s{self.sets[0]}-{self.sets[1]}_g{self.games[0]}-{self.games[1]}_p{s_pts}-{r_pts}_serving{self.server_serving}"
    
    def get_current_score_string(self) -> str:
        """Get human-readable score string"""
        if self.is_tiebreak and self.tiebreak_points:
            s_pts, r_pts = self.tiebreak_points
            return f"Sets {self.sets[0]}-{self.sets[1]}, Games {self.games[0]}-{self.games[1]}, Tiebreak {s_pts}-{r_pts}"
        else:
            s_pts, r_pts = self.points
            return f"Sets {self.sets[0]}-{self.sets[1]}, Games {self.games[0]}-{self.games[1]}, Points {s_pts}-{r_pts}"
    
    def __str__(self) -> str:
        """String representation"""
        server_name = self.current_server_name
        receiver_name = self.current_receiver_name
        return f"Match {self.match_id}: {server_name} vs {receiver_name} - {self.get_current_score_string()}"


# Test the corrected MatchState
if __name__ == "__main__":
    print("Testing Corrected MatchState...")
    
    # Create initial state
    initial_state = CorrectedMatchState(
        match_id="test_match",
        player_names=("Djokovic", "Sinner"),
        match_format=MatchFormat.BEST_OF_3,
        sets=(0, 0),
        games=(0, 0),
        points=(0, 0),
        server_serving=True,  # Djokovic serves first
        total_games_played=0
    )
    
    print(f"Initial state: {initial_state}")
    print(f"Service game start: {initial_state.is_service_game_start()}")
    
    # Test point progression
    state = initial_state
    print(f"\nPoint progression test:")
    
    # Server wins first point
    state = state.copy_with_point_won(0)
    print(f"After server wins point: {state}")
    
    # Server wins game
    state = state.copy_with_point_won(0)  # 30-0
    state = state.copy_with_point_won(0)  # 40-0
    state = state.copy_with_point_won(0)  # Game complete
    print(f"After server wins game: {state}")
    print(f"Service alternated: {not state.server_serving}")
    
    # Test set completion
    print(f"\nSet completion test:")
    state = CorrectedMatchState(
        match_id="test_match",
        player_names=("Djokovic", "Sinner"),
        match_format=MatchFormat.BEST_OF_3,
        sets=(0, 0),
        games=(5, 4),  # Server leads 5-4
        points=(0, 0),
        server_serving=True,
        total_games_played=9
    )
    
    # Server wins game to complete set 6-4
    state = state.copy_with_point_won(0)  # 15-0
    state = state.copy_with_point_won(0)  # 30-0
    state = state.copy_with_point_won(0)  # 40-0
    state = state.copy_with_point_won(0)  # Set complete
    
    print(f"After set completion: {state}")
    print(f"Total games played: {state.total_games_played}")
    print(f"Service for next set: {state.server_serving} (should be True - even games, service alternates)")
    
    print("\nCorrected MatchState test complete!")
