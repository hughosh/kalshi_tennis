"""
State Reconciliation with Kalshi

This module implements reconciliation between tennis feed state and Kalshi market state
to ensure we're not trading on stale or inconsistent data.
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging
import requests
import json
from dataclasses import dataclass
from data.data_integration import ValidatedMatchState

logger = logging.getLogger(__name__)


@dataclass
class KalshiMarketData:
    """Kalshi market data structure"""
    market_id: str
    status: str  # 'open', 'closed', 'resolved'
    yes_price: float
    no_price: float
    volume: int
    last_trade_time: Optional[datetime]
    resolution: Optional[str] = None
    score_data: Optional[Dict] = None


@dataclass
class ReconciliationResult:
    """Result of state reconciliation"""
    is_consistent: bool
    issues: List[str]
    kalshi_market: Optional[KalshiMarketData]
    tennis_state: Optional[ValidatedMatchState]
    timestamp: datetime


class KalshiConnector:
    """
    Enhanced Kalshi API connector with proper authentication and error handling.
    
    Handles RSA secret key authentication and provides market data access.
    """
    
    def __init__(self, secret_key: str, username: str, base_url: str = "https://trading-api.kalshi.com"):
        self.secret_key = secret_key
        self.username = username
        self.base_url = base_url
        self.session = requests.Session()
        
        # Set up authentication headers
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "TennisTradingBot/1.0"
        })
        
        # Authentication state
        self.authenticated = False
        self.auth_token = None
        self.auth_expires = None
        
        # Statistics
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.auth_failures = 0
    
    def _ensure_authenticated(self):
        """Ensure we have a valid authentication token"""
        if self.auth_token and self.auth_expires and datetime.now() < self.auth_expires:
            return
        
        try:
            # Authenticate with RSA key
            auth_data = {
                "username": self.username,
                "secret_key": self.secret_key
            }
            
            response = self.session.post(
                f"{self.base_url}/login",
                json=auth_data,
                timeout=10
            )
            
            if response.status_code == 200:
                auth_response = response.json()
                self.auth_token = auth_response.get('token')
                self.auth_expires = datetime.now() + timedelta(hours=1)  # Assume 1 hour expiry
                self.authenticated = True
                
                # Update session headers
                self.session.headers.update({
                    "Authorization": f"Bearer {self.auth_token}"
                })
                
                logger.info("Successfully authenticated with Kalshi")
            else:
                logger.error(f"Authentication failed: {response.status_code} - {response.text}")
                self.auth_failures += 1
                raise Exception(f"Authentication failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            self.authenticated = False
            raise
    
    def get_market(self, market_id: str) -> Optional[KalshiMarketData]:
        """
        Get market data from Kalshi.
        
        Args:
            market_id: Kalshi market identifier
        
        Returns:
            KalshiMarketData or None if not found
        """
        try:
            self._ensure_authenticated()
            
            response = self.session.get(
                f"{self.base_url}/markets/{market_id}",
                timeout=10
            )
            
            self.total_requests += 1
            
            if response.status_code == 404:
                logger.warning(f"Market {market_id} not found")
                return None
            
            response.raise_for_status()
            data = response.json()
            
            self.successful_requests += 1
            
            # Parse market data
            market_data = KalshiMarketData(
                market_id=market_id,
                status=data.get('status', 'unknown'),
                yes_price=data.get('yes_price', 0.0),
                no_price=data.get('no_price', 0.0),
                volume=data.get('volume', 0),
                last_trade_time=self._parse_timestamp(data.get('last_trade_time')),
                resolution=data.get('resolution'),
                score_data=data.get('score_data')
            )
            
            return market_data
            
        except Exception as e:
            logger.error(f"Failed to get market {market_id}: {e}")
            self.failed_requests += 1
            return None
    
    def get_markets_by_ticker(self, ticker: str) -> List[KalshiMarketData]:
        """
        Get markets by ticker symbol.
        
        Args:
            ticker: Market ticker (e.g., "TENNIS-DJOKOVIC-SINNER")
        
        Returns:
            List of KalshiMarketData
        """
        try:
            self._ensure_authenticated()
            
            response = self.session.get(
                f"{self.base_url}/markets",
                params={"ticker": ticker},
                timeout=10
            )
            
            self.total_requests += 1
            response.raise_for_status()
            
            data = response.json()
            markets = []
            
            for market_data in data.get('markets', []):
                market = KalshiMarketData(
                    market_id=market_data.get('id'),
                    status=market_data.get('status', 'unknown'),
                    yes_price=market_data.get('yes_price', 0.0),
                    no_price=market_data.get('no_price', 0.0),
                    volume=market_data.get('volume', 0),
                    last_trade_time=self._parse_timestamp(market_data.get('last_trade_time')),
                    resolution=market_data.get('resolution'),
                    score_data=market_data.get('score_data')
                )
                markets.append(market)
            
            self.successful_requests += 1
            return markets
            
        except Exception as e:
            logger.error(f"Failed to get markets for ticker {ticker}: {e}")
            self.failed_requests += 1
            return []
    
    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """Parse timestamp string to datetime"""
        if not timestamp_str:
            return None
        
        try:
            # Handle various timestamp formats
            if 'T' in timestamp_str:
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                return datetime.fromisoformat(timestamp_str)
        except:
            return None
    
    def get_statistics(self) -> Dict[str, any]:
        """Get connector statistics"""
        success_rate = (self.successful_requests / max(1, self.total_requests)) * 100
        
        return {
            'authenticated': self.authenticated,
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'auth_failures': self.auth_failures,
            'success_rate': f"{success_rate:.1f}%",
            'auth_expires': self.auth_expires
        }


class StateReconciliation:
    """
    Ensures tennis feed state matches Kalshi market state.
    
    This is critical for preventing trades on stale or inconsistent data.
    """
    
    def __init__(self, kalshi_connector: KalshiConnector):
        self.kalshi = kalshi_connector
        self.discrepancies: List[ReconciliationResult] = []
        self.max_discrepancies = 100  # Keep last 100 discrepancies
    
    def reconcile(self, tennis_state: ValidatedMatchState, 
                 market_id: str) -> ReconciliationResult:
        """
        Check if tennis feed state matches Kalshi market data.
        
        Args:
            tennis_state: Current tennis match state
            market_id: Kalshi market identifier
        
        Returns:
            ReconciliationResult with consistency check
        """
        issues = []
        
        try:
            # Get Kalshi market data
            kalshi_market = self.kalshi.get_market(market_id)
            
            if not kalshi_market:
                issues.append(f"Market {market_id} not found on Kalshi")
                result = ReconciliationResult(
                    is_consistent=False,
                    issues=issues,
                    kalshi_market=None,
                    tennis_state=tennis_state,
                    timestamp=datetime.now()
                )
                self._record_discrepancy(result)
                return result
            
            # Check 1: Market status
            if kalshi_market.status != 'open':
                issues.append(f"Market is {kalshi_market.status}, not open")
            
            # Check 2: Match completion consistency
            if tennis_state.is_match_complete():
                if kalshi_market.status == 'open':
                    issues.append("Match is complete but market still open")
            else:
                if kalshi_market.status == 'resolved':
                    issues.append("Match is ongoing but market is resolved")
            
            # Check 3: Score consistency (if Kalshi provides score data)
            if kalshi_market.score_data:
                kalshi_score = kalshi_market.score_data
                tennis_score = {
                    'sets': tennis_state.sets,
                    'games': tennis_state.games,
                    'points': tennis_state.points
                }
                
                if not self._scores_match(kalshi_score, tennis_score):
                    issues.append("Score mismatch between Kalshi and tennis feed")
            
            # Check 4: Data staleness
            if tennis_state.is_stale(max_staleness_seconds=10.0):
                issues.append(f"Tennis data is stale ({tennis_state.staleness_seconds:.1f}s)")
            
            # Check 5: Market activity
            if kalshi_market.last_trade_time:
                time_since_trade = datetime.now() - kalshi_market.last_trade_time
                if time_since_trade.total_seconds() > 300:  # 5 minutes
                    issues.append(f"Market inactive for {time_since_trade.total_seconds():.0f}s")
            
            is_consistent = len(issues) == 0
            
            result = ReconciliationResult(
                is_consistent=is_consistent,
                issues=issues,
                kalshi_market=kalshi_market,
                tennis_state=tennis_state,
                timestamp=datetime.now()
            )
            
            if not is_consistent:
                self._record_discrepancy(result)
            
            return result
            
        except Exception as e:
            issues.append(f"Reconciliation error: {e}")
            result = ReconciliationResult(
                is_consistent=False,
                issues=issues,
                kalshi_market=None,
                tennis_state=tennis_state,
                timestamp=datetime.now()
            )
            self._record_discrepancy(result)
            return result
    
    def _scores_match(self, kalshi_score: Dict, tennis_score: Dict) -> bool:
        """Check if scores match between Kalshi and tennis feed"""
        try:
            # Compare sets
            if kalshi_score.get('sets') != tennis_score['sets']:
                return False
            
            # Compare games
            if kalshi_score.get('games') != tennis_score['games']:
                return False
            
            # Compare points (if available)
            if 'points' in kalshi_score and kalshi_score['points'] != tennis_score['points']:
                return False
            
            return True
            
        except Exception:
            return False
    
    def _record_discrepancy(self, result: ReconciliationResult):
        """Record discrepancy for analysis"""
        self.discrepancies.append(result)
        
        # Keep only recent discrepancies
        if len(self.discrepancies) > self.max_discrepancies:
            self.discrepancies = self.discrepancies[-self.max_discrepancies:]
        
        logger.warning(f"Reconciliation discrepancy: {result.issues}")
    
    def get_discrepancy_summary(self) -> Dict[str, any]:
        """Get summary of reconciliation discrepancies"""
        if not self.discrepancies:
            return {"total_discrepancies": 0}
        
        recent_discrepancies = [
            d for d in self.discrepancies 
            if (datetime.now() - d.timestamp).total_seconds() < 3600  # Last hour
        ]
        
        issue_counts = {}
        for discrepancy in recent_discrepancies:
            for issue in discrepancy.issues:
                issue_counts[issue] = issue_counts.get(issue, 0) + 1
        
        return {
            "total_discrepancies": len(self.discrepancies),
            "recent_discrepancies": len(recent_discrepancies),
            "common_issues": issue_counts,
            "last_discrepancy": self.discrepancies[-1].timestamp if self.discrepancies else None
        }


# Test the reconciliation
if __name__ == "__main__":
    print("Testing State Reconciliation...")
    
    # Mock Kalshi connector for testing
    class MockKalshiConnector(KalshiConnector):
        def __init__(self):
            pass
        
        def get_market(self, market_id: str) -> Optional[KalshiMarketData]:
            return KalshiMarketData(
                market_id=market_id,
                status="open",
                yes_price=0.55,
                no_price=0.45,
                volume=1000,
                last_trade_time=datetime.now(),
                score_data={
                    'sets': (0, 0),
                    'games': (0, 0),
                    'points': (0, 0)
                }
            )
    
    # Test reconciliation
    mock_kalshi = MockKalshiConnector()
    reconciler = StateReconciliation(mock_kalshi)
    
    # Create test tennis state
    tennis_state = ValidatedMatchState(
        match_id="test_match",
        player_names=("Djokovic", "Sinner"),
        match_format="BO3",
        sets=(0, 0),
        games=(0, 0),
        points=(0, 0),
        server_serving=True,
        total_games_played=0,
        timestamp=datetime.now(),
        data_source="test",
        staleness_seconds=1.0
    )
    
    # Test reconciliation
    result = reconciler.reconcile(tennis_state, "test_market")
    
    print(f"Reconciliation result: {result.is_consistent}")
    print(f"Issues: {result.issues}")
    print(f"Kalshi market: {result.kalshi_market}")
    
    print("\nState Reconciliation test complete!")
