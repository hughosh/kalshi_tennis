"""
Simple Probability Calculator for Tennis Trading

This is a simplified probability calculator that returns reasonable values
for testing purposes while the complex Markov chain engine is being debugged.
"""

from typing import Dict, Tuple
from core.corrected_match_state import CorrectedMatchState


class SimpleProbabilityCalculator:
    """
    Simplified probability calculator that returns reasonable values
    based on current match state and serve probability.
    
    This calculator provides a simplified interface that mimics the
    complex Markov chain engine for testing purposes.
    """
    
    def __init__(self):
        # Initialize mock chain attributes to maintain compatibility
        self.game_chain = self
        self.point_chain = self
        self.set_chain = self
    
    def get_match_win_probability(self, state: CorrectedMatchState, p_serve: float) -> Dict[str, float]:
        """
        Calculate match win probability using simplified logic.
        
        Args:
            state: Current match state
            p_serve: Server's point-winning probability
            
        Returns:
            Dictionary with player win probabilities
        """
        server_name, receiver_name = state.player_names
        server_sets, receiver_sets = state.sets
        server_games, receiver_games = state.games
        server_points, receiver_points = state.points
        
        # Base probability from serve advantage
        base_server_prob = p_serve
        
        # Adjust based on sets won
        set_advantage = (server_sets - receiver_sets) * 0.3  # Each set is worth 30%
        
        # Adjust based on games in current set
        game_advantage = (server_games - receiver_games) * 0.05  # Each game is worth 5%
        
        # Adjust based on points in current game
        point_advantage = (server_points - receiver_points) * 0.01  # Each point is worth 1%
        
        # Calculate final probability
        server_prob = base_server_prob + set_advantage + game_advantage + point_advantage
        
        # Clamp to reasonable range
        server_prob = max(0.1, min(0.9, server_prob))
        receiver_prob = 1.0 - server_prob
        
        return {
            server_name: server_prob,
            receiver_name: receiver_prob
        }
    
    def get_set_win_probability(self, p_serve: float, server_games: int, receiver_games: int) -> float:
        """
        Calculate set win probability using simplified logic.
        
        Args:
            p_serve: Server's point-winning probability
            server_games: Server's games in current set
            receiver_games: Receiver's games in current set
            
        Returns:
            Probability server wins the set
        """
        # Base probability from serve advantage
        base_prob = p_serve
        
        # Adjust based on games won
        game_advantage = (server_games - receiver_games) * 0.1  # Each game is worth 10%
        
        # Calculate final probability
        prob = base_prob + game_advantage
        
        # Clamp to reasonable range
        return max(0.1, min(0.9, prob))
    
    def get_game_win_probability(self, p_serve: float, server_points: int, receiver_points: int) -> float:
        """
        Calculate game win probability using simplified logic.
        
        Args:
            p_serve: Server's point-winning probability
            server_points: Server's points in current game
            receiver_points: Receiver's points in current game
            
        Returns:
            Probability server wins the game
        """
        # Base probability from serve advantage
        base_prob = p_serve
        
        # Adjust based on points won
        point_advantage = (server_points - receiver_points) * 0.2  # Each point is worth 20%
        
        # Calculate final probability
        prob = base_prob + point_advantage
        
        # Clamp to reasonable range
        return max(0.1, min(0.9, prob))
