"""
Official Kalshi API Client using the official Python SDK

This implementation uses the official kalshi-python package for proper
authentication and API interaction.
"""

import os
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from kalshi_python import Configuration, KalshiClient

logger = logging.getLogger(__name__)

@dataclass
class KalshiEvent:
    event_id: str
    title: str
    status: str
    close_time: Optional[str] = None
    open_time: Optional[str] = None

@dataclass
class KalshiMarket:
    market_id: str
    ticker: str
    yes_price: float
    no_price: float
    yes_bid: Optional[float] = None
    yes_ask: Optional[float] = None
    no_bid: Optional[float] = None
    no_ask: Optional[float] = None
    last_price: Optional[float] = None
    volume: int = 0

class OfficialKalshiClient:
    """Official Kalshi API client using the official Python SDK"""
    
    def __init__(self):
        self.client = self._create_client()
        
        if not self.client:
            logger.warning("No Kalshi client available - Kalshi integration disabled")
    
    def _create_client(self) -> Optional[KalshiClient]:
        """Create Kalshi client using official SDK"""
        try:
            # Load key ID from environment
            key_id = os.getenv('KALSHI_KEY_ID')
            if not key_id:
                logger.warning("KALSHI_KEY_ID not found in environment variables")
                return None
            
            # Load RSA private key from file
            key_file = os.path.join(os.path.dirname(__file__), 'config', 'kalshi_secret_key.txt')
            if not os.path.exists(key_file):
                logger.warning(f"RSA private key file not found: {key_file}")
                return None
            
            with open(key_file, 'r') as f:
                private_key = f.read()
            
            # Configure the client
            config = Configuration(
                host="https://api.elections.kalshi.com/trade-api/v2"
            )
            config.api_key_id = key_id
            config.private_key_pem = private_key
            
            # Initialize the client
            client = KalshiClient(config)
            logger.info("Official Kalshi client created successfully")
            return client
            
        except Exception as e:
            logger.error(f"Error creating official Kalshi client: {e}")
            return None
    
    def get_tennis_events(self) -> List[KalshiEvent]:
        """Get all tennis events from Kalshi using series API"""
        if not self.client:
            logger.warning("No Kalshi client - returning empty events list")
            return []
        
        try:
            # Get all series first
            series_response = self.client.get_series()
            series_list = series_response.series
            
            # Filter for tennis series
            tennis_series = []
            for series_data in series_list:
                if hasattr(series_data, 'title') and 'tennis' in series_data.title.lower():
                    tennis_series.append(series_data)
            
            events = []
            for series_data in tennis_series:
                # Get markets for this series
                markets_response = self.client.get_markets(series_ticker=series_data.ticker)
                markets_list = markets_response.markets
                
                # Create events from markets
                for market_data in markets_list:
                    # Map status to valid enum values
                    status = market_data.status
                    if status == 'finalized':
                        status = 'settled'
                    elif status not in ['initialized', 'active', 'closed', 'settled', 'determined']:
                        status = 'active'  # Default to active for unknown statuses
                    
                    events.append(KalshiEvent(
                        event_id=market_data.ticker,  # Use ticker as event_id
                        title=market_data.title,
                        status=status,
                        close_time=str(market_data.close_time) if market_data.close_time else None,
                        open_time=str(market_data.open_time) if market_data.open_time else None
                    ))
            
            logger.info(f"Found {len(events)} tennis events from {len(tennis_series)} tennis series")
            return events
            
        except Exception as e:
            logger.error(f"Error fetching tennis events: {e}")
            return []
    
    def get_event_markets(self, event_id: str) -> List[KalshiMarket]:
        """Get markets for a specific event (using ticker as event_id)"""
        if not self.client:
            logger.warning("No Kalshi client - returning empty markets list")
            return []
        
        try:
            # Get all series first
            series_response = self.client.get_series()
            series_list = series_response.series
            
            # Filter for tennis series
            tennis_series = []
            for series_data in series_list:
                if hasattr(series_data, 'title') and 'tennis' in series_data.title.lower():
                    tennis_series.append(series_data)
            
            markets = []
            for series_data in tennis_series:
                markets_response = self.client.get_markets(series_ticker=series_data.ticker)
                markets_list = markets_response.markets
                
                for market_data in markets_list:
                    if market_data.ticker == event_id:
                        # Convert prices from cents to dollars
                        yes_price = float(market_data.yes_ask_dollars) if market_data.yes_ask_dollars else 0.0
                        no_price = float(market_data.no_ask_dollars) if market_data.no_ask_dollars else 0.0
                        yes_bid = float(market_data.yes_bid_dollars) if market_data.yes_bid_dollars else None
                        yes_ask = float(market_data.yes_ask_dollars) if market_data.yes_ask_dollars else None
                        no_bid = float(market_data.no_bid_dollars) if market_data.no_bid_dollars else None
                        no_ask = float(market_data.no_ask_dollars) if market_data.no_ask_dollars else None
                        last_price = float(market_data.last_price_dollars) if market_data.last_price_dollars else None
                        
                        markets.append(KalshiMarket(
                            market_id=market_data.ticker,
                            ticker=market_data.ticker,
                            yes_price=yes_price,
                            no_price=no_price,
                            yes_bid=yes_bid,
                            yes_ask=yes_ask,
                            no_bid=no_bid,
                            no_ask=no_ask,
                            last_price=last_price,
                            volume=market_data.volume or 0
                        ))
            
            logger.info(f"Found {len(markets)} markets for event {event_id}")
            return markets
            
        except Exception as e:
            logger.error(f"Error fetching markets for event {event_id}: {e}")
            return []


# Global instance
official_kalshi_client = OfficialKalshiClient()
