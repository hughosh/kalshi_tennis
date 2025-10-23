"""
Kalshi API Client for Tennis Trading

Real integration with Kalshi API using simplified HTTP requests.
"""

from simple_kalshi_client import simple_kalshi_client, KalshiEvent, KalshiMarket
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class KalshiAPIClient:
    """Kalshi API client wrapper for tennis trading"""
    
    def __init__(self):
        self.client = simple_kalshi_client
        
        if not self.client.private_key or not self.client.key_id:
            logger.warning("No Kalshi client available - Kalshi integration disabled")
    
    def get_tennis_events(self) -> List[KalshiEvent]:
        """Get all tennis events from Kalshi using simplified client"""
        return simple_kalshi_client.get_tennis_events()
    
    def get_event_markets(self, event_id: str) -> List[KalshiMarket]:
        """Get markets for a specific event using simplified client"""
        return simple_kalshi_client.get_event_markets(event_id)
    
    def get_all_tennis_market_tickers(self) -> List[str]:
        """Get all tennis market tickers for order placement"""
        return simple_kalshi_client.get_all_tennis_market_tickers()
    
    def place_order(self, ticker: str, side: str, count: int, price_cents: int) -> Dict[str, Any]:
        """Place an order on Kalshi"""
        return simple_kalshi_client.place_order(ticker, side, count, price_cents)
    
    def find_matching_kalshi_markets(self, player_names: List[str]) -> List[Dict[str, Any]]:
        """Find Kalshi markets that match live tennis players"""
        return simple_kalshi_client.find_matching_kalshi_markets(player_names)


# Global instances
kalshi_api_client = KalshiAPIClient()