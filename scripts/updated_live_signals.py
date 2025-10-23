"""
Live Signal Generator with API-Tennis.com Integration

This uses the API-Tennis.com client directly for live tennis data.
Generates trading signals based on multi-stage trading strategy.
"""

import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import json

# Import our components
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.api_tennis_client import APITennisFeed, TennisMatch
from trading.multi_stage_trading import MultiStageTradingStrategy, RiskLimits, TradingSignal
from trading.win_tracking import win_tracker
from data.data_integration import ValidatedMatchState
from shared_signal_database import get_signal_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UpdatedLiveSignalGenerator:
    """
    Updated live signal generator using API-Tennis.com feed.
    
    This generates real trading signals for live tennis matches
    WITHOUT executing any trades.
    """
    
    def __init__(self, output_file: str = "api_live_trading_signals.txt"):
        self.output_file = output_file
        
        # Initialize API tennis feed
        self.tennis_feed = APITennisFeed()
        
        # Initialize trading strategy
        risk_limits = RiskLimits(
            max_total_exposure=1000.0,
            max_position_size=100.0,
            max_positions_per_match=1,
            max_concurrent_positions=3
        )
        
        self.strategy = MultiStageTradingStrategy(risk_limits)
        
        # Initialize shared signal database
        self.signal_db = get_signal_database()
        
        # Track processed matches
        self.processed_matches = set()
        
        # Statistics
        self.total_signals = 0
        self.matches_processed = 0
        self.start_time = datetime.now()
        
        logger.info("UpdatedLiveSignalGenerator initialized")
        logger.info(f"Output file: {output_file}")
        logger.info(f"Tennis feed mode: api")
    
    def write_signal_to_file(self, signal: TradingSignal, match_state: ValidatedMatchState):
        """Write trading signal to output file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        signal_data = {
            "timestamp": timestamp,
            "match_id": signal.match_id,
            "player_names": match_state.player_names,
            "current_score": {
                "sets": match_state.sets,
                "games": match_state.games,
                "points": match_state.points
            },
            "server_serving": match_state.server_serving,
            "signal": {
                "player": signal.player,
                "direction": signal.direction.value,
                "stage": signal.stage.value,
                "entry_probability": signal.entry_probability,
                "expected_value": signal.expected_value,
                "confidence": signal.confidence,
                "edge": signal.edge,
                "market_price": signal.market_price,
                "model_price": signal.model_price,
                "reasoning": signal.reasoning
            }
        }
        
        # Write to file
        with open(self.output_file, "a") as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"API LIVE TRADING SIGNAL - {timestamp}\n")
            f.write(f"{'='*80}\n")
            f.write(f"Match: {match_state.player_names[0]} vs {match_state.player_names[1]}\n")
            f.write(f"Match ID: {signal.match_id}\n")
            f.write(f"Current Score: {match_state.sets[0]}-{match_state.sets[1]} sets, ")
            f.write(f"{match_state.games[0]}-{match_state.games[1]} games, ")
            f.write(f"{match_state.points[0]}-{match_state.points[1]} points\n")
            f.write(f"Server: {match_state.player_names[0] if match_state.server_serving else match_state.player_names[1]}\n")
            f.write(f"Data Source: API-Tennis.com\n")
            f.write(f"\nSIGNAL DETAILS:\n")
            f.write(f"  Player: {signal.player}\n")
            f.write(f"  Direction: {signal.direction.value}\n")
            f.write(f"  Stage: {signal.stage.value}\n")
            f.write(f"  Edge: {signal.edge:.4f}\n")
            f.write(f"  Market Price: {signal.market_price:.4f}\n")
            f.write(f"  Model Price: {signal.model_price:.4f}\n")
            f.write(f"  Expected Value: {signal.expected_value:.4f}\n")
            f.write(f"  Confidence: {signal.confidence:.4f}\n")
            f.write(f"  Reasoning: {signal.reasoning}\n")
            f.write(f"\nJSON DATA:\n{json.dumps(signal_data, indent=2)}\n")
            f.write(f"{'='*80}\n")
        
        logger.info(f"Signal written to {self.output_file}")
    
    def convert_tennis_match_to_validated_state(self, match: TennisMatch) -> ValidatedMatchState:
        """
        Convert TennisMatch to ValidatedMatchState for trading strategy.
        
        Args:
            match: TennisMatch from API-Tennis.com
            
        Returns:
            ValidatedMatchState for trading
        """
        return ValidatedMatchState(
            match_id=match.match_id,
            player_names=match.player_names,
            match_format=match.match_format,
            sets=match.sets,
            games=match.games,
            points=match.points,
            server_serving=match.server_serving,
            total_games_played=sum(match.sets) * 10 + sum(match.games),
            timestamp=match.timestamp,
            data_source=match.data_source,
            staleness_seconds=1.0
        )
    
    
    def get_kalshi_market_data(self, match_state: ValidatedMatchState) -> Optional[Dict[str, Dict[str, float]]]:
        """
        Get real market data from Kalshi API.
        
        Args:
            match_state: Current match state
            
        Returns:
            Market data dictionary or None if not available
        """
        try:
            # Import Kalshi client
            from kalshi_api_client import kalshi_api_client
            
            if not kalshi_api_client.client:
                logger.debug("No Kalshi client available - skipping market data")
                return None
            
            # Get tennis events
            events = kalshi_api_client.get_tennis_events()
            if not events:
                logger.debug("No tennis events found on Kalshi")
                return None
            
            # Find matching event using last names only
            def get_last_name(name):
                """Extract last name from player name"""
                parts = name.strip().split()
                if len(parts) >= 2:
                    return parts[-1].lower()  # Last part is surname
                return name.lower()
            
            server_name, receiver_name = match_state.player_names
            server_lastname = get_last_name(server_name)
            receiver_lastname = get_last_name(receiver_name)
            
            matching_event = None
            for event in events:
                event_title_lower = event.title.lower()
                
                # Simple last name matching
                if server_lastname in event_title_lower or receiver_lastname in event_title_lower:
                    matching_event = event
                    break
            
            if not matching_event:
                logger.debug(f"No matching Kalshi event for {match_state.player_names}")
                return None
            
            # Find markets for both players
            market_data = {}
            
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
                        if server_lastname in player_name_in_title and server_name not in market_data:
                            markets = kalshi_api_client.get_event_markets(event.event_id)
                            for market in markets:
                                market_data[server_name] = {
                                    "yes_price": market.yes_price,
                                    "no_price": market.no_price
                                }
                        elif receiver_lastname in player_name_in_title and receiver_name not in market_data:
                            markets = kalshi_api_client.get_event_markets(event.event_id)
                            for market in markets:
                                market_data[receiver_name] = {
                                    "yes_price": market.yes_price,
                                    "no_price": market.no_price
                                }
            
            if len(market_data) == 2:
                logger.info(f"Found Kalshi market data for {match_state.player_names}")
                return market_data
            else:
                logger.debug(f"Incomplete market data: {list(market_data.keys())}")
                return None
                
        except Exception as e:
            logger.debug(f"Error getting Kalshi market data: {e}")
            return None
    
    async def process_live_matches(self) -> List[TradingSignal]:
        """
        Process all live matches and generate signals.
        
        Returns:
            List of generated trading signals
        """
        logger.info("Processing live matches with API-Tennis.com feed...")
        
        # Get active matches from API-Tennis.com
        active_matches = await self.tennis_feed.get_live_matches()
        
        if not active_matches:
            logger.info("No active matches found")
            return []
        
        # Filter for WTA/ATP matches only (the only ones trading on Kalshi)
        wta_atp_matches = []
        for match in active_matches:
            tournament_lower = match.tournament.lower()
            if 'wta' in tournament_lower or 'atp' in tournament_lower:
                wta_atp_matches.append(match)
        
        logger.info(f"Found {len(active_matches)} total matches")
        logger.info(f"Found {len(wta_atp_matches)} WTA/ATP matches (Kalshi trading)")
        
        if not wta_atp_matches:
            logger.info("No WTA/ATP matches found - no signals will be generated")
            return []
        
        all_signals = []
        
        for match in wta_atp_matches:
            if match.match_id in self.processed_matches:
                continue
            
            logger.info(f"Processing WTA/ATP match: {match.match_id}")
            logger.info(f"  Players: {match.player_names[0]} vs {match.player_names[1]}")
            logger.info(f"  Score: {match.sets[0]}-{match.sets[1]} sets")
            logger.info(f"  Tournament: {match.tournament}")
            logger.info(f"  Data source: {match.data_source}")
            
            try:
                # Convert to ValidatedMatchState
                match_state = self.convert_tennis_match_to_validated_state(match)
                
                # Get real Kalshi market data
                market_data = self.get_kalshi_market_data(match_state)
                
                if not market_data:
                    logger.debug(f"No Kalshi market data available for {match_state.player_names} - skipping match")
                    continue
                
                # Debug: Log match state details
                logger.info(f"  Current points: {match_state.points}")
                logger.info(f"  Current games: {match_state.games}")
                logger.info(f"  Is service game start: {match_state.points == (0, 0)}")
                logger.info(f"  Is valid for trading: {match_state.is_valid_for_trading()}")
                
                # Generate trading signals
                signals = self.strategy.evaluate_trading_opportunities(match_state, market_data)
                
                if signals:
                    logger.info(f"Generated {len(signals)} signals for match {match.match_id}")
                    
                    # Write signals to file and add to shared database
                    for signal in signals:
                        self.write_signal_to_file(signal, match_state)
                        # Add to shared database for web portal
                        signal_id = self.signal_db.add_signal(signal, match_state)
                        # Add to win tracker for P&L monitoring using the same signal ID
                        position_id = win_tracker.add_signal(signal, match_state, signal_id)
                        logger.info(f"Added signal to win tracker: {position_id}")
                        all_signals.append(signal)
                        self.total_signals += 1
                else:
                    logger.info(f"No signals generated for match {match.match_id}")
                
                self.processed_matches.add(match.match_id)
                self.matches_processed += 1
                
            except Exception as e:
                logger.error(f"Error processing match {match.match_id}: {e}")
                continue
        
        return all_signals
    
    async def run_live_monitoring(self, check_interval_seconds: int = 30, run_indefinitely: bool = True):
        """
        Run live monitoring indefinitely or for specified duration.
        
        Args:
            check_interval_seconds: How often to check for new matches
            run_indefinitely: If True, run forever until interrupted
        """
        logger.info(f"Starting live monitoring {'indefinitely' if run_indefinitely else 'for specified duration'}")
        logger.info(f"Check interval: {check_interval_seconds} seconds")
        logger.info(f"Tennis feed mode: API-Tennis.com")
        
        # Clear output file
        with open(self.output_file, "w") as f:
            f.write(f"API LIVE TENNIS TRADING SIGNALS\n")
            f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Mode: {'Indefinite' if run_indefinitely else 'Limited duration'}\n")
            f.write(f"Check interval: {check_interval_seconds} seconds\n")
            f.write(f"Tennis feed mode: API-Tennis.com\n")
            f.write(f"LIVE TRADING ENABLED - ORDERS WILL BE PLACED!\n")
            f.write(f"{'='*80}\n")
        
        check_count = 0
        
        try:
            while True:  # Run indefinitely
                check_count += 1
                current_time = datetime.now()
                
                logger.info(f"Check #{check_count} - {current_time.strftime('%H:%M:%S')}")
                
                try:
                    # Check and manage orders before updating positions
                    win_tracker.check_and_manage_orders()
                    
                    # Update win tracker prices for existing positions
                    if win_tracker.active_positions:
                        logger.info(f"Updating prices for {len(win_tracker.active_positions)} active positions")
                        win_tracker.update_position_prices(None)  # Will use kalshi_api_client internally
                    
                    # Process live matches
                    signals = await self.process_live_matches()
                    
                    if signals:
                        logger.info(f"Generated {len(signals)} total signals")
                    else:
                        logger.info("No signals generated this check")
                    
                    # Write status update every 10 checks
                    if check_count % 10 == 0:
                        self.write_status_update()
                    
                    # Wait before next check
                    logger.info(f"Waiting {check_interval_seconds} seconds...")
                    time.sleep(check_interval_seconds)
                    
                except Exception as e:
                    logger.error(f"Error in monitoring loop: {e}")
                    time.sleep(check_interval_seconds)
                    
        except KeyboardInterrupt:
            logger.info("Monitoring interrupted by user")
            self.write_final_summary()
        except Exception as e:
            logger.error(f"Unexpected error in monitoring: {e}")
            self.write_final_summary()
        
        logger.info("Live monitoring completed")
    
    def write_status_update(self):
        """Write status update to file"""
        elapsed = datetime.now() - self.start_time
        
        with open(self.output_file, "a") as f:
            f.write(f"\n--- STATUS UPDATE ---\n")
            f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Elapsed: {elapsed}\n")
            f.write(f"Matches processed: {self.matches_processed}\n")
            f.write(f"Total signals: {self.total_signals}\n")
            f.write(f"Tennis feed stats: {self.tennis_feed.get_statistics()}\n")
            f.write(f"--- END STATUS ---\n")
    
    def write_final_summary(self):
        """Write final summary to file"""
        elapsed = datetime.now() - self.start_time
        
        with open(self.output_file, "a") as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"FINAL SUMMARY\n")
            f.write(f"{'='*80}\n")
            f.write(f"Monitoring completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total duration: {elapsed}\n")
            f.write(f"Matches processed: {self.matches_processed}\n")
            f.write(f"Total signals generated: {self.total_signals}\n")
            f.write(f"Average signals per match: {self.total_signals / max(1, self.matches_processed):.2f}\n")
            f.write(f"Tennis feed statistics: {self.tennis_feed.get_statistics()}\n")
            f.write(f"{'='*80}\n")


def main():
    """Main function to run updated live signal generation"""
    print("🚀 LIVE TENNIS TRADING SIGNAL GENERATOR")
    print("=" * 70)
    print("This uses API-Tennis.com for live tennis data")
    print("LIVE TRADING ENABLED - orders will be placed!")
    print("=" * 70)
    
    # Get user input for interval time
    try:
        print("\nEnter check interval in seconds (default: 30):")
        interval_input = input().strip()
        if interval_input:
            interval = int(interval_input)
            if interval < 5:
                print("Warning: Interval less than 5 seconds may cause rate limiting issues")
        else:
            interval = 30
    except KeyboardInterrupt:
        print("\nExiting...")
        return
    except ValueError:
        print("Invalid input, using default interval of 30 seconds")
        interval = 30
    
    output_file = "api_live_trading_signals.txt"
    
    print(f"\nStarting live monitoring:")
    print(f"  Mode: Indefinite (press Ctrl+C to stop)")
    print(f"  Check interval: {interval} seconds")
    print(f"  Output file: {output_file}")
    print(f"  Data source: API-Tennis.com")
    print(f"  LIVE TRADING ENABLED")
    print(f"\nPress Ctrl+C to stop monitoring at any time...")
    
    # Create and run signal generator
    generator = UpdatedLiveSignalGenerator(output_file)
    
    try:
        asyncio.run(generator.run_live_monitoring(interval, run_indefinitely=True))
    except KeyboardInterrupt:
        print("\nMonitoring interrupted by user")
        generator.write_final_summary()
    except Exception as e:
        print(f"Error during monitoring: {e}")
        generator.write_final_summary()


if __name__ == "__main__":
    import asyncio
    main()
