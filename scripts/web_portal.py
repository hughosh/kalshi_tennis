#!/usr/bin/env python3
"""
Web Portal for Tennis Trading System

A local web interface to view live trading signals, Kalshi odds, and simulated outcomes.
No actual trades are performed - this is for analysis only.
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.api_tennis_client import APITennisFeed, TennisMatch
from trading.multi_stage_trading import TradingSignal, TradeDirection, TradeStage
# Import win tracker from the signal generation script to use the same instance
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from trading.win_tracking import win_tracker
from shared_signal_database import get_signal_database, SignalRecord
from kalshi_api_client import kalshi_api_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

class KalshiOddsFetcher:
    """Real Kalshi odds fetcher with live market data"""
    
    def __init__(self):
        self.cache: Dict[str, Dict[str, float]] = {}
        self.last_fetch = {}
        self.kalshi_client = kalshi_api_client
    
    def get_odds(self, match_id: str, player: str) -> Optional[float]:
        """Get current odds for a player in a match"""
        cache_key = f"{match_id}_{player}"
        
        # Check cache first
        if cache_key in self.cache:
            cache_time = self.last_fetch.get(cache_key)
            if cache_time and (datetime.now() - cache_time).seconds < 30:  # 30 second cache
                return self.cache[cache_key]["yes"]
        
        # Try to get real Kalshi price
        try:
            # This is a simplified approach - in practice you'd need to match the match_id
            # to a Kalshi market more precisely
            kalshi_price = self._get_kalshi_price_for_match(match_id, player)
            
            if kalshi_price is not None:
                self.cache[cache_key] = {
                    "yes": kalshi_price,
                    "no": round(1.0 - kalshi_price, 3)
                }
                self.last_fetch[cache_key] = datetime.now()
                return kalshi_price
        except Exception as e:
            logger.error(f"Error fetching Kalshi price: {e}")
        
        # No fallback - return None if Kalshi unavailable
        return None
    
    def _get_kalshi_price_for_match(self, match_id: str, player: str) -> Optional[float]:
        """Get Kalshi price for a specific match and player"""
        # This is a placeholder - you'd need to implement proper matching
        # between API-Tennis.com match IDs and Kalshi markets
        
        # For now, return None to use mock data
        # In production, you'd:
        # 1. Map match_id to player names and tournament
        # 2. Find matching Kalshi market using tennis_matcher
        # 3. Get live price from that market
        return None
    
    def get_odds_for_signal(self, signal: dict) -> Optional[float]:
        """Get odds for a specific signal"""
        # Extract player name from signal
        if "Buy" in signal['signal']:
            player = signal['signal'].replace("Buy ", "")
        elif "Sell" in signal['signal']:
            player = signal['signal'].replace("Sell ", "")
        else:
            return None
        
        return self.get_odds(signal['match_id'], player)

# Global instances
signal_db = get_signal_database()
odds_fetcher = KalshiOddsFetcher()
tennis_feed = APITennisFeed()

def get_kalshi_odds_for_match(match):
    """
    Get Kalshi odds for a specific match using proper RSA authentication.
    
    Args:
        match: TennisMatch object
        
    Returns:
        Dictionary with player odds or None if not available
    """
    try:
        # Import Kalshi client
        from kalshi_api_client import kalshi_api_client
        
        if not kalshi_api_client.client:
            return None
        
        # Get tennis events
        events = kalshi_api_client.get_tennis_events()
        if not events:
            return None
        
        # Find matching event
        matching_event = None
        server_name, receiver_name = match.player_names
        
        # Extract last names only for simple matching
        def get_last_name(name):
            """Extract last name from player name"""
            # Handle names like "M. Berrettini" or "Matteo Berrettini"
            parts = name.strip().split()
            if len(parts) >= 2:
                return parts[-1].lower()  # Last part is surname
            return name.lower()
        
        server_lastname = get_last_name(server_name)
        receiver_lastname = get_last_name(receiver_name)
        
        for event in events:
            event_title_lower = event.title.lower()
            
            # Simple last name matching
            if server_lastname in event_title_lower or receiver_lastname in event_title_lower:
                matching_event = event
                break
        
        if not matching_event:
            return None
        
        # Find markets for both players
        odds = {}
        
        # Look through all events to find markets for both players
        for event in events:
            event_title_lower = event.title.lower()
            
            # Check if this event is for one of our players
            # Look for the pattern "Will [Player Name] win" to determine which player this event is for
            if 'will' in event_title_lower and 'win' in event_title_lower:
                # Extract the player name after "will" and before "win"
                will_index = event_title_lower.find('will')
                win_index = event_title_lower.find('win')
                if will_index != -1 and win_index != -1 and win_index > will_index:
                    player_name_in_title = event_title_lower[will_index+4:win_index].strip()
                    
                    # Check which of our players this event is for
                    if server_lastname in player_name_in_title and server_name not in odds:
                        markets = kalshi_api_client.get_event_markets(event.event_id)
                        for market in markets:
                            odds[server_name] = {
                                'yes_price': market.yes_price,
                                'no_price': market.no_price,
                                'ticker': market.ticker
                            }
                    elif receiver_lastname in player_name_in_title and receiver_name not in odds:
                        markets = kalshi_api_client.get_event_markets(event.event_id)
                        for market in markets:
                            odds[receiver_name] = {
                                'yes_price': market.yes_price,
                                'no_price': market.no_price,
                                'ticker': market.ticker
                            }
        
        # Return odds if we found both players
        if len(odds) == 2:
            return odds
        else:
            return None
            
    except Exception as e:
        logger.debug(f"Error getting Kalshi odds for match {match.match_id}: {e}")
        return None


@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/positions')
def get_positions():
    """Get active trading positions with P&L"""
    try:
        active_positions = win_tracker.get_active_positions()
        closed_positions = win_tracker.get_closed_positions()
        summary = win_tracker.get_position_summary()
        
        return jsonify({
            'active_positions': active_positions,
            'closed_positions': closed_positions,
            'summary': summary,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/signals')
def get_signals():
    """API endpoint to get recent signals with position information"""
    # Reload database to get latest updates
    try:
        signal_db.reload_from_file()
        logger.info("Database reloaded successfully")
    except Exception as e:
        logger.error(f"Error reloading database: {e}")
    
    limit = request.args.get('limit', 100, type=int)
    signals = signal_db.get_signals(limit)
    
    # Get active positions for matching
    active_positions = {pos['signal_id']: pos for pos in win_tracker.get_active_positions()}
    closed_positions = {pos['signal_id']: pos for pos in win_tracker.get_closed_positions()}
    
    # Add current odds and position info for each signal
    for signal in signals:
        if signal['outcome'] == 'Pending':
            odds = odds_fetcher.get_odds_for_signal(signal)
            signal['current_odds'] = odds
        
        # Add position information
        signal_id = signal.get('id')  # Use 'id' instead of 'signal_id'
        if signal_id:
            if signal_id in active_positions:
                pos = active_positions[signal_id]
                signal['position'] = {
                    'status': 'active',
                    'entry_price': pos['entry_price'],
                    'current_price': pos['current_price'],
                    'current_pnl_pct': pos['current_pnl_pct'],
                    'current_pnl_absolute': pos['current_pnl_absolute'],
                    'entry_time': pos['entry_time'],
                    'last_updated': pos['last_updated'],
                    'holding_time_minutes': pos['holding_time_minutes']
                }
            elif signal_id in closed_positions:
                pos = closed_positions[signal_id]
                signal['position'] = {
                    'status': 'closed',
                    'entry_price': pos['entry_price'],
                    'exit_price': pos['exit_price'],
                    'final_pnl_pct': pos['final_pnl_pct'],
                    'final_pnl_absolute': pos['final_pnl_absolute'],
                    'entry_time': pos['entry_time'],
                    'exit_time': pos['exit_time'],
                    'exit_reason': pos['exit_reason'],
                    'holding_time_minutes': pos['holding_time_minutes']
                }
            else:
                signal['position'] = None
    
    return jsonify({
        'signals': signals,
        'total': len(signal_db.signals),
        'last_update': signal_db.last_update.isoformat()
    })

@app.route('/api/matches')
def get_matches():
    """API endpoint to get current live matches (WTA/ATP only)"""
    try:
        import asyncio
        matches = asyncio.run(tennis_feed.get_live_matches())
        
        # Filter for WTA and ATP matches only (the only ones trading on Kalshi)
        filtered_matches = []
        for match in matches:
            tournament_lower = match.tournament.lower()
            if 'wta' in tournament_lower or 'atp' in tournament_lower:
                # Determine who is serving
                serving_player = match.player_names[0] if match.server_serving else match.player_names[1]
                
                # Format game score (e.g., "4-2" or "15-30")
                game_score = f"{match.points[0]}-{match.points[1]}"
                
                # Convert tennis points to readable format
                def format_tennis_points(points):
                    """Convert numerical points to tennis scoring"""
                    if points == 0:
                        return "0"
                    elif points == 1:
                        return "15"
                    elif points == 2:
                        return "30"
                    elif points == 3:
                        return "40"
                    elif points == 4:
                        return "A"  # Advantage
                    else:
                        return str(points)
                
                formatted_game_score = f"{format_tennis_points(match.points[0])}-{format_tennis_points(match.points[1])}"
                
                # Get Kalshi odds for this match
                kalshi_odds = get_kalshi_odds_for_match(match)
                
                filtered_matches.append({
                    'match_id': match.match_id,
                    'players': f"{match.player_names[0]} vs {match.player_names[1]}",
                    'tournament': match.tournament,
                    'set_score': f"{match.sets[0]}-{match.sets[1]}",
                    'game_score': f"{match.games[0]}-{match.games[1]}",
                    'point_score': formatted_game_score,
                    'serving_player': serving_player,
                    'status': match.status,
                    'is_live': match.is_live,
                    'current_set': match.sets[0] + match.sets[1] + 1,  # Which set we're in
                    'kalshi_odds': kalshi_odds
                })
        
        return jsonify({
            'matches': filtered_matches,
            'count': len(filtered_matches),
            'total_found': len(matches),
            'filtered_for': 'WTA/ATP only (Kalshi trading)',
            'note': 'Only WTA/ATP matches generate trading signals'
        })
    except Exception as e:
        logger.error(f"Error fetching matches: {e}")
        return jsonify({'matches': [], 'count': 0, 'error': str(e)})

@app.route('/api/kalshi/events')
def get_kalshi_events():
    """API endpoint to get Kalshi tennis events"""
    try:
        events = kalshi_api_client.get_tennis_events()
        return jsonify({
            'events': [
                {
                    'event_id': event.event_id,
                    'name': event.name,
                    'start_time': event.start_time,
                    'status': event.status,
                    'ticker': event.ticker
                }
                for event in events
            ],
            'count': len(events),
            'kalshi_connected': kalshi_api_client.client.private_key is not None
        })
    except Exception as e:
        logger.error(f"Error fetching Kalshi events: {e}")
        return jsonify({'events': [], 'count': 0, 'error': str(e), 'kalshi_connected': False})

@app.route('/api/kalshi/markets/<event_id>')
def get_kalshi_markets(event_id):
    """API endpoint to get Kalshi markets for an event"""
    try:
        markets = kalshi_api_client.get_event_markets(event_id)
        return jsonify({
            'markets': [
                {
                    'market_id': market.market_id,
                    'ticker': market.ticker,
                    'title': market.title,
                    'status': market.status,
                    'yes_bid': market.yes_bid,
                    'yes_ask': market.yes_ask,
                    'no_bid': market.no_bid,
                    'no_ask': market.no_ask,
                    'last_price': market.last_price,
                    'volume': market.volume
                }
                for market in markets
            ],
            'count': len(markets)
        })
    except Exception as e:
        logger.error(f"Error fetching Kalshi markets for event {event_id}: {e}")
        return jsonify({'markets': [], 'count': 0, 'error': str(e)})

@app.route('/api/stats')
def get_stats():
    """API endpoint to get trading statistics"""
    return jsonify(signal_db.get_statistics())

@app.route('/api/add_signal', methods=['POST'])
def add_signal():
    """API endpoint to add a new signal (for testing)"""
    try:
        data = request.json
        
        # This endpoint is disabled - no mock signals
        return jsonify({'error': 'Mock signals disabled - use real signal generation'}), 400
        
    except Exception as e:
        logger.error(f"Error adding signal: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

def update_match_outcomes():
    """Background task to update match outcomes"""
    try:
        import asyncio
        matches = asyncio.run(tennis_feed.get_live_matches())
        
        for match in matches:
            if not match.is_live and match.match_id not in signal_db.match_results:
                # Match has finished, update outcomes
                result = f"{match.player_names[0]} {match.sets[0]}-{match.sets[1]} {match.player_names[1]}"
                signal_db.update_outcome(match.match_id, result)
                
    except Exception as e:
        logger.error(f"Error updating match outcomes: {e}")

def main():
    """Main function to run the web portal"""
    print("🌐 TENNIS TRADING WEB PORTAL")
    print("=" * 50)
    print("Starting web portal...")
    print("Open http://localhost:5000 in your browser")
    print("=" * 50)
    
    # Create templates directory if it doesn't exist
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    os.makedirs(template_dir, exist_ok=True)
    
    # Start background task for updating outcomes
    import threading
    def background_update():
        while True:
            try:
                update_match_outcomes()
                time.sleep(30)  # Update every 30 seconds
            except Exception as e:
                logger.error(f"Background update error: {e}")
                time.sleep(60)
    
    update_thread = threading.Thread(target=background_update, daemon=True)
    update_thread.start()
    
    # Run Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)

if __name__ == "__main__":
    main()
