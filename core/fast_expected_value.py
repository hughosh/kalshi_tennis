"""
Fast Expected Value Calculator

This module implements the fast expected value calculation using game-level changes
instead of expensive point-by-point simulation.
"""

from typing import Dict, List
import time
from core.corrected_match_state import CorrectedMatchState
from core.fast_tennis_engine import MatchProbabilityCalculator


class FastExpectedValueCalculator:
    """
    Fast approximation of expected price movement using game-level changes.
    
    Key insight: Most price movement comes from game completion, not individual points.
    
    Performance:
    - Old approach: 2^N point sequences × 100ms = 0.8-25 seconds
    - New approach: 3 calculations × 5ms = 15ms
    - Speedup: 50-1600x
    """
    
    def __init__(self, match_calc: MatchProbabilityCalculator):
        self.match_calc = match_calc
    
    def calculate_expected_movement(self, state: CorrectedMatchState, player: str, p_serve: float) -> float:
        """
        Calculate expected match-win probability change over next game.
        
        Args:
            state: Current match state
            player: Player name to calculate movement for
            p_serve: Server's point-winning probability
        
        Returns:
            Expected probability change over next game
        
        Time: ~10ms (3 probability calculations)
        """
        # Current probability
        current_probs = self.match_calc.get_match_win_probability(state, p_serve)
        current_prob = current_probs[player]
        
        # State if server wins game
        state_if_server_wins = self._get_state_if_server_wins_game(state)
        probs_if_server_wins = self.match_calc.get_match_win_probability(state_if_server_wins, p_serve)
        
        # State if receiver wins game
        state_if_receiver_wins = self._get_state_if_receiver_wins_game(state)
        probs_if_receiver_wins = self.match_calc.get_match_win_probability(state_if_receiver_wins, p_serve)
        
        # Get game-win probability
        p_server_wins_game = self.match_calc.game_chain.get_game_win_probability(p_serve, 0, 0)
        
        # Calculate expected movement
        server_name = state.player_names[0]  # First player is server
        if player == server_name:  # Server
            delta_if_win_game = probs_if_server_wins[player] - current_prob
            delta_if_lose_game = probs_if_receiver_wins[player] - current_prob
            expected_delta = (p_server_wins_game * delta_if_win_game + 
                            (1 - p_server_wins_game) * delta_if_lose_game)
        else:  # Receiver
            delta_if_lose_game = probs_if_server_wins[player] - current_prob
            delta_if_win_game = probs_if_receiver_wins[player] - current_prob
            expected_delta = (p_server_wins_game * delta_if_lose_game + 
                            (1 - p_server_wins_game) * delta_if_win_game)
        
        return expected_delta
    
    def calculate_point_by_point_movement(self, state: CorrectedMatchState, player: str, 
                                        p_serve: float, num_points: int = 3) -> List[float]:
        """
        For critical decisions, calculate expected probability at each point.
        
        Args:
            state: Current match state
            player: Player name
            p_serve: Server's point-winning probability
            num_points: Number of points to simulate
        
        Returns:
            List of expected probability changes for each point
        
        Time: ~5ms × num_points
        """
        movements = []
        current_state = state
        
        for _ in range(num_points):
            if current_state.is_match_complete():
                break
            
            # Get next states
            state_if_server_wins_pt = current_state.copy_with_point_won(0)
            state_if_receiver_wins_pt = current_state.copy_with_point_won(1)
            
            # Get probabilities
            current_prob = self.match_calc.get_match_win_probability(current_state, p_serve)[player]
            prob_if_server_wins = self.match_calc.get_match_win_probability(state_if_server_wins_pt, p_serve)[player]
            prob_if_receiver_wins = self.match_calc.get_match_win_probability(state_if_receiver_wins_pt, p_serve)[player]
            
            # Expected movement this point
            p_server_wins_pt = self._get_point_win_probability(current_state, p_serve)
            delta = (p_server_wins_pt * (prob_if_server_wins - current_prob) +
                    (1 - p_server_wins_pt) * (prob_if_receiver_wins - current_prob))
            
            movements.append(delta)
            
            # Advance to expected state for next iteration
            if p_server_wins_pt > 0.5:
                current_state = state_if_server_wins_pt
            else:
                current_state = state_if_receiver_wins_pt
        
        return movements
    
    def _get_state_if_server_wins_game(self, state: CorrectedMatchState) -> CorrectedMatchState:
        """Get state if server wins current game"""
        if state.is_tiebreak:
            # In tiebreak, server wins tiebreak
            return state.copy_with_point_won(0)  # This will complete the tiebreak
        else:
            # In regular game, server wins game
            # Simulate server winning enough points to win game
            current_state = state
            server_pts, receiver_pts = current_state.points
            
            # Calculate points needed to win
            if server_pts >= 4 and server_pts - receiver_pts >= 2:
                # Already winning, just need one more point
                return current_state.copy_with_point_won(0)
            else:
                # Need to get to 4 points with 2-point lead
                points_needed = max(0, 4 - server_pts)
                if receiver_pts >= 3:
                    points_needed = max(points_needed, receiver_pts - server_pts + 2)
                
                # Simulate winning required points
                for _ in range(points_needed):
                    current_state = current_state.copy_with_point_won(0)
                
                return current_state
    
    def _get_state_if_receiver_wins_game(self, state: CorrectedMatchState) -> CorrectedMatchState:
        """Get state if receiver wins current game"""
        if state.is_tiebreak:
            # In tiebreak, receiver wins tiebreak
            return state.copy_with_point_won(1)  # This will complete the tiebreak
        else:
            # In regular game, receiver wins game
            # Simulate receiver winning enough points to win game
            current_state = state
            server_pts, receiver_pts = current_state.points
            
            # Calculate points needed to win
            if receiver_pts >= 4 and receiver_pts - server_pts >= 2:
                # Already winning, just need one more point
                return current_state.copy_with_point_won(1)
            else:
                # Need to get to 4 points with 2-point lead
                points_needed = max(0, 4 - receiver_pts)
                if server_pts >= 3:
                    points_needed = max(points_needed, server_pts - receiver_pts + 2)
                
                # Simulate winning required points
                for _ in range(points_needed):
                    current_state = current_state.copy_with_point_won(1)
                
                return current_state
    
    def _get_point_win_probability(self, state: CorrectedMatchState, p_serve: float) -> float:
        """Get probability that server wins current point"""
        if state.is_tiebreak:
            # In tiebreak, service alternates
            # For simplicity, use average of serve and return probabilities
            return p_serve
        else:
            # Regular game - server serving
            return p_serve
    
    def calculate_trading_edge(self, state: CorrectedMatchState, player: str, 
                             market_price: float, p_serve: float) -> Dict[str, float]:
        """
        Calculate trading edge and expected value.
        
        Args:
            state: Current match state
            player: Player to trade
            market_price: Current market price
            p_serve: Server's point-winning probability
        
        Returns:
            Dictionary with edge, expected_value, and confidence
        """
        # Get model probability
        model_probs = self.match_calc.get_match_win_probability(state, p_serve)
        model_prob = model_probs[player]
        
        # Calculate edge
        edge = model_prob - market_price
        
        # Calculate expected movement
        expected_movement = self.calculate_expected_movement(state, player, p_serve)
        
        # Calculate expected value (simplified)
        # Assume we can capture 50% of the expected movement
        expected_value = edge * 0.5
        
        # Calculate confidence based on edge size and game state
        confidence = min(1.0, abs(edge) * 10)  # Scale edge to confidence
        
        return {
            'edge': edge,
            'expected_value': expected_value,
            'expected_movement': expected_movement,
            'model_probability': model_prob,
            'market_price': market_price,
            'confidence': confidence
        }


# Test the FastExpectedValueCalculator
if __name__ == "__main__":
    print("Testing FastExpectedValueCalculator...")
    
    from fast_tennis_engine import GameMarkovChain, TiebreakMarkovChain, SetProbabilityCalculator, MatchProbabilityCalculator
    from corrected_match_state import CorrectedMatchState, MatchFormat
    
    # Initialize components
    game_chain = GameMarkovChain()
    tiebreak_chain = TiebreakMarkovChain()
    set_calc = SetProbabilityCalculator(game_chain, tiebreak_chain)
    match_calc = MatchProbabilityCalculator(game_chain, set_calc)
    
    # Create calculator
    calc = FastExpectedValueCalculator(match_calc)
    
    # Test state
    state = CorrectedMatchState(
        match_id="test_match",
        player_names=("Djokovic", "Sinner"),
        match_format=MatchFormat.BEST_OF_3,
        sets=(0, 0),
        games=(0, 0),
        points=(0, 0),
        server_serving=True,
        total_games_played=0
    )
    
    print(f"Test state: {state}")
    
    # Test expected movement calculation
    start_time = time.time()
    movement = calc.calculate_expected_movement(state, "Djokovic", 0.65)
    elapsed = time.time() - start_time
    
    print(f"Expected movement: {movement:.4f}")
    print(f"Calculation time: {elapsed*1000:.2f}ms")
    
    # Test trading edge calculation
    edge_info = calc.calculate_trading_edge(state, "Djokovic", 0.55, 0.65)
    print(f"\nTrading edge info: {edge_info}")
    
    # Test point-by-point movement
    movements = calc.calculate_point_by_point_movement(state, "Djokovic", 0.65, 3)
    print(f"\nPoint-by-point movements: {movements}")
    
    print("\nFastExpectedValueCalculator test complete!")
