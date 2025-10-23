"""
Simplified Kalshi API Client using raw HTTP requests

This implementation bypasses the SDK validation issues by using direct HTTP requests
with proper RSA authentication.
"""

import os
import requests
import base64
import time
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.exceptions import InvalidSignature

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

class SimpleKalshiClient:
    """Simplified Kalshi API client using raw HTTP requests"""
    
    def __init__(self):
        # Use the correct production URL (elections.kalshi.com for production)
        self.base_url = "https://api.elections.kalshi.com"
        self.private_key = self._load_private_key()
        self.key_id = self._load_key_id()
        
        if not self.private_key or not self.key_id:
            logger.warning("No Kalshi RSA credentials provided - Kalshi integration disabled")
    
    def _load_private_key(self):
        """Load RSA private key from file"""
        key_file = os.path.join(os.path.dirname(__file__), 'config', 'kalshi_secret_key.txt')
        if os.path.exists(key_file):
            try:
                with open(key_file, 'rb') as f:
                    private_key = serialization.load_pem_private_key(
                        f.read(),
                        password=None,
                    )
                return private_key
            except Exception as e:
                logger.error(f"Error loading RSA private key: {e}")
        return None
    
    def _load_key_id(self):
        """Load Kalshi key ID from environment or file"""
        # Load environment variables from .env file
        from dotenv import load_dotenv
        load_dotenv()
        
        key_id = os.getenv('KALSHI_KEY_ID')
        if key_id:
            return key_id
        
        # Try loading from file as fallback
        key_id_file = os.path.join(os.path.dirname(__file__), 'config', 'kalshi_username.txt')
        if os.path.exists(key_id_file):
            try:
                with open(key_id_file, 'r') as f:
                    return f.read().strip()
            except Exception as e:
                logger.error(f"Error loading Kalshi key ID: {e}")
        return None
    
    def _sign_request(self, method: str, path: str) -> Dict[str, str]:
        """Sign a request with RSA private key according to Kalshi API specs"""
        if not self.private_key or not self.key_id:
            return {}
        
        # Generate timestamp in milliseconds as required by Kalshi API
        timestamp = str(int(time.time() * 1000))
        
        # Strip query parameters from path before signing (Kalshi API requirement)
        # e.g., for '/portfolio/orders?limit=5', sign only '/trade-api/v2/portfolio/orders'
        path_parts = path.split('?')
        clean_path = path_parts[0]
        
        # Create message: timestamp + HTTP_METHOD + path (without query parameters)
        message = timestamp + method + clean_path
        
        signature = self.private_key.sign(
            message.encode('utf-8'),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH
            ),
            hashes.SHA256()
        )
        
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        
        return {
            'KALSHI-ACCESS-KEY': self.key_id,
            'KALSHI-ACCESS-SIGNATURE': signature_b64,
            'KALSHI-ACCESS-TIMESTAMP': timestamp,
            'Content-Type': 'application/json'
        }
    
    def _make_request(self, method: str, path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make authenticated request to Kalshi API"""
        if not self.private_key or not self.key_id:
            logger.warning("No Kalshi credentials - returning empty response")
            return {}
        
        try:
            headers = self._sign_request(method, path)
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
                markets_response = self._make_request('GET', '/trade-api/v2/markets', 
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
                markets_response = self._make_request('GET', '/trade-api/v2/markets', 
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

    def get_all_tennis_market_tickers(self) -> List[str]:
        """Get all open tennis market tickers for order placement"""
        try:
            # Use specific tennis series tickers
            tennis_series_tickers = [
                'KXWTAMATCH',  # WTA Tennis Match
                'KXATPMATCH'   # ATP Tennis Match
            ]
            
            all_tickers = []
            for series_ticker in tennis_series_tickers:
                markets_response = self._make_request('GET', '/trade-api/v2/markets', 
                                                    {'series_ticker': series_ticker})
                markets_list = markets_response.get('markets', [])
                
                # Filter for only 'active' status markets
                active_markets = [market for market in markets_list if market.get('status') == 'active']
                
                for market_data in active_markets:
                    all_tickers.append(market_data['ticker'])
            
            logger.info(f"Found {len(all_tickers)} active tennis market tickers")
            return all_tickers
            
        except Exception as e:
            logger.error(f"Error fetching tennis market tickers: {e}")
            return []

    def place_order(self, ticker: str, side: str, count: int, price_cents: int, order_type: str = "market") -> Dict[str, Any]:
        """Place an order on Kalshi using the correct API format from docs"""
        try:
            import uuid
            
            # Use the exact Kalshi API order format from documentation
            order_data = {
                "ticker": ticker,
                "action": "buy" if side == "yes" else "sell",
                "side": side,
                "count": count,
                "type": order_type,  # "market" or "limit"
                "client_order_id": str(uuid.uuid4()),  # UUID for deduplication as required
            }
            
            # Add time_in_force and price based on order type
            if order_type == "limit":
                order_data["time_in_force"] = "good_till_cancel"  # More lenient than immediate_or_cancel
                # Add price field for limit orders
                if side == "yes":
                    order_data["yes_price"] = price_cents
                else:
                    order_data["no_price"] = price_cents
            elif order_type == "market":
                # For market orders, we might need to specify a max price or use different format
                # Let's try without price first, but some APIs require a max price for market orders
                if price_cents > 0:  # If a price is provided, use it as max price
                    if side == "yes":
                        order_data["yes_price"] = price_cents
                    else:
                        order_data["no_price"] = price_cents
            
            response = self._make_request('POST', '/trade-api/v2/portfolio/orders', order_data)
            logger.info(f"Order placed for {ticker}: {side} {count} @ {price_cents} cents ({order_type})")
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
                markets_response = self._make_request('GET', '/trade-api/v2/markets', 
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

    def get_portfolio_balance(self) -> Dict[str, Any]:
        """Get current portfolio balance from Kalshi"""
        try:
            response = self._make_request('GET', '/trade-api/v2/portfolio/balance')
            if response:
                logger.info(f"Portfolio balance retrieved: {response}")
                return response
            return {}
        except Exception as e:
            logger.error(f"Error getting portfolio balance: {e}")
            return {}

    def get_portfolio_positions(self) -> List[Dict[str, Any]]:
        """Get current portfolio positions from Kalshi"""
        try:
            response = self._make_request('GET', '/trade-api/v2/portfolio/positions')
            if response and 'positions' in response:
                return response['positions']
            return []
        except Exception as e:
            logger.error(f"Error getting portfolio positions: {e}")
            return []


# Global instance
simple_kalshi_client = SimpleKalshiClient()
