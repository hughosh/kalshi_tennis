"""
Bearer Token Kalshi API Client

This implementation uses Bearer token authentication as specified in the Kalshi API documentation.
"""

import os
import requests
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

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

class BearerKalshiClient:
    """Kalshi API client using Bearer token authentication"""
    
    def __init__(self):
        # Use the correct trading API URL from documentation
        self.base_url = "https://trading-api.kalshi.com/trade-api/v2"
        self.token = None
        self.email = os.getenv('KALSHI_EMAIL')
        self.password = os.getenv('KALSHI_PASSWORD')
        
        if not self.email or not self.password:
            logger.warning("No Kalshi email/password provided - Kalshi integration disabled")
        else:
            self._login()
    
    def _login(self) -> bool:
        """Login to Kalshi and get Bearer token"""
        try:
            login_data = {
                "email": self.email,
                "password": self.password
            }
            
            response = requests.post(f"{self.base_url}/login", json=login_data)
            response.raise_for_status()
            
            login_response = response.json()
            self.token = login_response.get('token')
            
            if self.token:
                logger.info("Successfully logged into Kalshi and obtained Bearer token")
                return True
            else:
                logger.error("Login successful but no token received")
                return False
                
        except Exception as e:
            logger.error(f"Error logging into Kalshi: {e}")
            return False
    
    def _get_headers(self) -> Dict[str, str]:
        """Get authenticated headers with Bearer token"""
        if not self.token:
            logger.warning("No Bearer token available")
            return {}
        
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
    
    def _make_request(self, method: str, path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make authenticated request to Kalshi API"""
        if not self.token:
            logger.warning("No Kalshi token - returning empty response")
            return {}
        
        try:
            headers = self._get_headers()
            url = f"{self.base_url}{path}"
            
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params)
            else:
                response = requests.request(method, url, headers=headers, json=params)
            
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Error making Kalshi API request: {e}")
            return {}
    
    def get_tennis_events(self) -> List[KalshiEvent]:
        """Get all tennis events from Kalshi using specific WTA/ATP series tickers, filtered for 'open' status"""
        try:
            # Use specific tennis series tickers
            tennis_series_tickers = [
                'KXWTAMATCH',  # WTA Tennis Match
                'KXATPMATCH'   # ATP Tennis Match
            ]
            
            events = []
            for series_ticker in tennis_series_tickers:
                # Get markets for this series
                markets_response = self._make_request('GET', '/markets', 
                                                    {'series_ticker': series_ticker})
                markets_list = markets_response.get('markets', [])
                
                # Filter for only 'active' status markets
                active_markets = [market for market in markets_list if market.get('status') == 'active']
                
                # Create events from active markets only
                for market_data in active_markets:
                    events.append(KalshiEvent(
                        event_id=market_data['ticker'],  # Use ticker as event_id
                        title=market_data.get('title', f'{series_ticker} Market'),
                        status=market_data.get('status', 'active'),
                        close_time=market_data.get('close_time'),
                        open_time=market_data.get('open_time')
                    ))
            
            logger.info(f"Found {len(events)} active tennis events from {len(tennis_series_tickers)} tennis series")
            return events
            
        except Exception as e:
            logger.error(f"Error fetching tennis events: {e}")
            return []
    
    def get_event_markets(self, event_id: str) -> List[KalshiMarket]:
        """Get markets for a specific event (using ticker as event_id)"""
        try:
            # Use specific tennis series tickers
            tennis_series_tickers = [
                'KXWTAMATCH',  # WTA Tennis Match
                'KXATPMATCH'   # ATP Tennis Match
            ]
            
            markets = []
            for series_ticker in tennis_series_tickers:
                markets_response = self._make_request('GET', '/markets', 
                                                    {'series_ticker': series_ticker})
                markets_list = markets_response.get('markets', [])
                
                for market_data in markets_list:
                    if market_data['ticker'] == event_id:
                        # Convert prices from cents to dollars
                        yes_price = float(market_data.get('yes_ask_dollars', 0)) if market_data.get('yes_ask_dollars') else 0.0
                        no_price = float(market_data.get('no_ask_dollars', 0)) if market_data.get('no_ask_dollars') else 0.0
                        yes_bid = float(market_data.get('yes_bid_dollars', 0)) if market_data.get('yes_bid_dollars') else None
                        yes_ask = float(market_data.get('yes_ask_dollars', 0)) if market_data.get('yes_ask_dollars') else None
                        no_bid = float(market_data.get('no_bid_dollars', 0)) if market_data.get('no_bid_dollars') else None
                        no_ask = float(market_data.get('no_ask_dollars', 0)) if market_data.get('no_ask_dollars') else None
                        last_price = float(market_data.get('last_price_dollars', 0)) if market_data.get('last_price_dollars') else None
                        
                        markets.append(KalshiMarket(
                            market_id=market_data['ticker'],
                            ticker=market_data['ticker'],
                            yes_price=yes_price,
                            no_price=no_price,
                            yes_bid=yes_bid,
                            yes_ask=yes_ask,
                            no_bid=no_bid,
                            no_ask=no_ask,
                            last_price=last_price,
                            volume=market_data.get('volume', 0)
                        ))
            
            logger.info(f"Found {len(markets)} markets for event {event_id}")
            return markets
            
        except Exception as e:
            logger.error(f"Error fetching markets for event {event_id}: {e}")
            return []

    def place_order(self, ticker: str, side: str, count: int, price_cents: int) -> Dict[str, Any]:
        """Place an order on Kalshi using the correct API format from docs"""
        try:
            import uuid
            
            # Use the exact Kalshi API order format from documentation
            order_data = {
                "contract_id": ticker,  # Use ticker as contract_id
                "client_order_id": str(uuid.uuid4()),  # UUID for deduplication as required
                "side": "buy" if side == "yes" else "sell",
                "type": "limit",  # Use limit orders as specified in docs
                "count": count
            }
            
            # Add price field based on side (yes_price or no_price)
            if side == "yes":
                order_data["yes_price"] = price_cents
            else:
                order_data["no_price"] = price_cents
            
            response = self._make_request('POST', '/orders', order_data)
            logger.info(f"Order placed for {ticker}: {side} {count} @ {price_cents} cents")
            return response
            
        except Exception as e:
            logger.error(f"Error placing order for {ticker}: {e}")
            return {}

    def find_matching_kalshi_markets(self, player_names: List[str]) -> List[Dict[str, Any]]:
        """Find Kalshi markets that match live tennis players"""
        try:
            # Get all open tennis markets
            tennis_series_tickers = [
                'KXWTAMATCH',  # WTA Tennis Match
                'KXATPMATCH'   # ATP Tennis Match
            ]
            
            matching_markets = []
            for series_ticker in tennis_series_tickers:
                markets_response = self._make_request('GET', '/markets', 
                                                    {'series_ticker': series_ticker})
                markets_list = markets_response.get('markets', [])
                
                # Filter for only 'active' status markets
                active_markets = [market for market in markets_list if market.get('status') == 'active']
                
                for market_data in active_markets:
                    market_title = market_data.get('title', '').lower()
                    
                    # Check if any player name appears in the market title
                    for player_name in player_names:
                        player_name_clean = player_name.lower().replace(' ', '').replace('/', '').replace('.', '')
                        if player_name_clean in market_title.replace(' ', '').replace('/', '').replace('.', ''):
                            matching_markets.append({
                                'ticker': market_data['ticker'],
                                'title': market_data['title'],
                                'status': market_data['status'],
                                'yes_price': float(market_data.get('yes_ask_dollars', 0)) if market_data.get('yes_ask_dollars') else 0.0,
                                'no_price': float(market_data.get('no_ask_dollars', 0)) if market_data.get('no_ask_dollars') else 0.0,
                                'volume': market_data.get('volume', 0),
                                'matched_player': player_name
                            })
                            break  # Found a match, move to next market
            
            logger.info(f"Found {len(matching_markets)} matching markets for players: {player_names}")
            return matching_markets
            
        except Exception as e:
            logger.error(f"Error finding matching markets: {e}")
            return []


# Global instance
bearer_kalshi_client = BearerKalshiClient()
