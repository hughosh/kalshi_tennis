"""
Live Tennis Trading with Score Feed

Simple script to run live trading using web-scraped tennis scores.
Fast, cheap, and works within seconds.
"""

import time
import sys
from typing import Dict, List, Optional

from tennis_match_markov import (
    MatchState, HierarchicalTennisMarkov, PlayerParams, MatchFormat, MarketData
)
from kalshi_trading_strategy import KalshiTradingStrategy
from tennis_score_feed import SimpleTennisScoreFeed
from mock_tennis_feed import MockTennisScoreFeed
from live_tracking import KalshiConnector


def create_player_params() -> Dict[str, PlayerParams]:
    """Create player parameters for common tennis players"""
    return {
        "Djokovic": PlayerParams(
            name="Djokovic",
            base_serve_prob=0.68,
            base_return_prob=0.38,
            pressure_serve_adjustment=0.02,
            fatigue_factor=-0.01
        ),
        "Sinner": PlayerParams(
            name="Sinner", 
            base_serve_prob=0.66,
            base_return_prob=0.36,
            pressure_serve_adjustment=-0.01,
            fatigue_factor=-0.015
        ),
        "Medvedev": PlayerParams(
            name="Medvedev",
            base_serve_prob=0.64,
            base_return_prob=0.40,
            pressure_serve_adjustment=0.01,
            fatigue_factor=-0.005
        ),
        "Zverev": PlayerParams(
            name="Zverev",
            base_serve_prob=0.67,
            base_return_prob=0.37,
            pressure_serve_adjustment=0.01,
            fatigue_factor=-0.01
        ),
        "Tsitsipas": PlayerParams(
            name="Tsitsipas",
            base_serve_prob=0.65,
            base_return_prob=0.39,
            pressure_serve_adjustment=0.01,
            fatigue_factor=-0.01
        )
    }


def setup_trading_system():
    """Set up the complete trading system"""
    print("Setting up tennis trading system...")
    
    # Load RSA secret key from file
    try:
        with open('kalshi_secret_key.txt', 'r') as f:
            secret_key = f.read().strip()
        print(f"Loaded Kalshi RSA secret key")
        
        # Also need your username/email for Kalshi
        try:
            with open('kalshi_username.txt', 'r') as f:
                username = f.read().strip()
            print(f"Loaded Kalshi username: {username}")
        except FileNotFoundError:
            print("Please create kalshi_username.txt with your Kalshi email")
            username = "your_email@example.com"
            
    except FileNotFoundError:
        print("No secret key file found, using mock mode")
        secret_key = "mock_secret_key"
        username = "mock_user"
    
    # Create Markov model
    model = HierarchicalTennisMarkov(MatchFormat.BEST_OF_3)
    
    # Add player parameters
    player_params = create_player_params()
    for player, params in player_params.items():
        model.set_player_parameters(player, params)
    
    # Create trading strategy
    strategy = KalshiTradingStrategy(
        markov_model=model,
        entry_threshold=0.02,  # 2% edge to enter
        exit_threshold=0.05,   # 5% target profit
        stop_loss_threshold=0.03,  # 3% stop loss
        max_position_size=100.0  # Start small
    )
    
    # Create score feed (using mock for now - web scraping needs more work)
    print("Using mock tennis data for testing")
    print("Note: Web scraper needs improvement for live matches")
    score_feed = MockTennisScoreFeed()
    
    # Create Kalshi connector
    kalshi = KalshiConnector(secret_key, username)
    
    return strategy, score_feed, kalshi


def get_mock_market_data(match_data: Dict, player1: str, player2: str) -> MarketData:
    """Create mock market data for testing"""
    # Simulate market prices (in real trading, get from Kalshi API)
    import random
    
    # Base prices around 50-50
    p1_price = 0.5 + random.uniform(-0.1, 0.1)
    p2_price = 1.0 - p1_price
    
    return MarketData(
        match_id=match_data['match_id'],
        player1=player1,
        player2=player2,
        player1_yes_price=p1_price,
        player2_yes_price=p2_price,
        player1_no_price=1-p1_price,
        player2_no_price=1-p2_price,
        timestamp=time.time(),
        volume_24h=1000,
        bid_ask_spread=0.02
    )


def run_live_trading():
    """Run live trading loop"""
    print("Starting live tennis trading...")
    
    # Setup
    strategy, score_feed, kalshi = setup_trading_system()
    
    # Track positions
    active_positions = {}
    last_states = {}
    
    print("Monitoring tennis matches...")
    
    try:
        while True:
            # Get active matches
            matches = score_feed.get_active_matches()
            
            if not matches:
                print("No active matches found, waiting...")
                time.sleep(10)
                continue
            
            print(f"Found {len(matches)} active matches")
            
            for match_id in matches:
                try:
                    # Get current match data
                    match_data = score_feed.get_match_data(match_id)
                    if not match_data:
                        continue
                    
                    # Get current state
                    current_state = score_feed.get_match_state(match_id)
                    if not current_state:
                        continue
                    
                    player1 = match_data['player1']
                    player2 = match_data['player2']
                    
                    # Check if we know these players
                    if player1 not in strategy.markov_model.base_serve_prob:
                        print(f"Unknown player: {player1}, skipping")
                        continue
                    if player2 not in strategy.markov_model.base_serve_prob:
                        print(f"Unknown player: {player2}, skipping")
                        continue
                    
                    # Get market data
                    market_data = get_mock_market_data(match_data, player1, player2)
                    
                    # Check for state changes
                    if match_id in last_states:
                        last_state = last_states[match_id]
                        if last_state.to_key() != current_state.to_key():
                            print(f"State change in {match_id}: {last_state.to_key()} -> {current_state.to_key()}")
                    
                    last_states[match_id] = current_state
                    
                    # Check for trading opportunities
                    if current_state.is_service_game_start():
                        print(f"Service game start: {player1} vs {player2}")
                        
                        # Evaluate trading opportunity
                        signal = strategy.evaluate_service_game_opportunity(current_state, market_data)
                        
                        if signal:
                            print(f"TRADE SIGNAL: {signal.player} at {signal.entry_price:.3f}")
                            print(f"Expected value: {signal.expected_value:.4f}")
                            print(f"Confidence: {signal.confidence:.3f}")
                            
                            # In real trading, execute the trade here
                            # order_id = kalshi.place_order(signal)
                            
                            # Track position
                            active_positions[match_id] = {
                                'signal': signal,
                                'entry_time': time.time(),
                                'entry_state': current_state
                            }
                    
                    # Check existing positions
                    if match_id in active_positions:
                        position = active_positions[match_id]
                        
                        # Check if we should exit
                        should_exit, reason = strategy.should_exit_trade(
                            position['signal'], current_state, market_data
                        )
                        
                        if should_exit:
                            print(f"EXIT SIGNAL: {reason}")
                            del active_positions[match_id]
                
                except Exception as e:
                    print(f"Error processing match {match_id}: {e}")
                    continue
            
            # Wait before next check
            print("Waiting 5 seconds...")
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\nStopping live trading...")
        print(f"Active positions: {len(active_positions)}")
        
        # Close all positions
        for match_id, position in active_positions.items():
            print(f"Closing position in {match_id}")


def test_score_feed():
    """Test the score feed"""
    print("Testing tennis score feed...")
    
    feed = MockTennisScoreFeed()
    
    # Get active matches
    matches = feed.get_active_matches()
    print(f"Found {len(matches)} active matches")
    
    if matches:
        # Test first match
        match_id = matches[0]
        print(f"Testing match: {match_id}")
        
        data = feed.get_match_data(match_id)
        if data:
            print(f"Match: {data['player1']} vs {data['player2']}")
            print(f"Score: Sets {data['sets']}, Games {data['games']}, Points {data['points']}")
            print(f"Server serving: {data['server_serving']}")
            
            state = feed.get_match_state(match_id)
            if state:
                print(f"State key: {state.to_key()}")
                print(f"Is service game start: {state.is_service_game_start()}")
        else:
            print("No data available")
    else:
        print("No active matches found")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_score_feed()
    else:
        run_live_trading()
