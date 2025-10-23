"""
API-Tennis.com Client Integration

This module provides a secure, maintainable client for the API-Tennis.com service
with proper authentication, error handling, and rate limiting.
"""

import os
import asyncio
import httpx
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import json
import time
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class TennisMatch:
    """Structured representation of a tennis match from API-Tennis.com"""
    match_id: str
    player_names: Tuple[str, str]
    sets: Tuple[int, int]
    games: Tuple[int, int]
    points: Tuple[int, int]
    server_serving: bool
    is_live: bool
    tournament: str
    surface: str
    match_format: str
    timestamp: datetime
    status: str
    current_set: int
    duration: Optional[int] = None
    data_source: str = "api-tennis.com"


class APITennisClient:
    """
    Secure client for API-Tennis.com with proper authentication and error handling.
    """
    
    def __init__(self, api_key: Optional[str] = None, rate_limit_delay: float = 1.0):
        # Load API key from environment or parameter
        self.api_key = api_key or os.getenv("API_TENNIS_KEY")
        
        if not self.api_key:
            raise ValueError("API key not found. Please set API_TENNIS_KEY in .env file or pass as parameter.")
        
        self.base_url = "https://api.api-tennis.com/tennis"
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0
        
        # Headers for all requests
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "TennisTradingBot/1.0"
        }
        
        # Statistics
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        
        logger.info("APITennisClient initialized")
    
    async def _rate_limit(self):
        """Enforce rate limiting between requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last
            await asyncio.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    async def _make_request(self, method: str, params: Dict[str, Any] = None, retries: int = 3) -> Optional[Dict[str, Any]]:
        """
        Make a rate-limited request to the API-Tennis.com API with retries.
        
        Args:
            method: API method (e.g., 'get_livescore', 'get_fixtures')
            params: Additional parameters for the request
            retries: Number of retry attempts
            
        Returns:
            JSON response data or None if all retries fail
        """
        # Build query parameters
        query_params = {
            "method": method,
            "APIkey": self.api_key
        }
        
        if params:
            query_params.update(params)
        
        url = f"{self.base_url}/"
        self.total_requests += 1
        
        for attempt in range(retries + 1):
            await self._rate_limit()
            
            try:
                async with httpx.AsyncClient(headers=self.headers, timeout=15.0) as client:
                    response = await client.get(url, params=query_params)
                    
                    logger.debug(f"API request attempt {attempt + 1}: {method} - Status: {response.status_code}")
                    
                    if response.status_code == 200:
                        data = response.json()
                        self.successful_requests += 1
                        logger.info(f"API request successful: {method}")
                        return data
                    elif response.status_code == 401:
                        logger.error(f"API authentication failed (401): Invalid API key")
                        self.failed_requests += 1
                        return None
                    elif response.status_code == 403:
                        logger.error(f"API access forbidden (403): Check API key permissions")
                        self.failed_requests += 1
                        return None
                    elif response.status_code == 429:
                        logger.warning(f"Rate limited (429): {method} - Attempt {attempt + 1}")
                        if attempt < retries:
                            # Wait longer for rate limit
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        else:
                            logger.error(f"Rate limited after {retries + 1} attempts: {method}")
                            self.failed_requests += 1
                            return None
                    elif response.status_code == 404:
                        logger.warning(f"API method not found (404): {method}")
                        self.failed_requests += 1
                        return None
                    else:
                        logger.warning(f"API request failed ({response.status_code}): {method} - Attempt {attempt + 1}")
                        if attempt < retries:
                            await asyncio.sleep(1)
                            continue
                        else:
                            logger.error(f"API request failed after {retries + 1} attempts: {method}")
                            self.failed_requests += 1
                            return None
                            
            except httpx.TimeoutException:
                logger.warning(f"API request timeout: {method} - Attempt {attempt + 1}")
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                else:
                    logger.error(f"API request timeout after {retries + 1} attempts: {method}")
                    self.failed_requests += 1
                    return None
            except Exception as e:
                logger.warning(f"API request error: {e} - Attempt {attempt + 1}")
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                else:
                    logger.error(f"API request error after {retries + 1} attempts: {e}")
                    self.failed_requests += 1
                    return None
        
        return None
    
    async def get_live_matches(self) -> List[TennisMatch]:
        """
        Get all live tennis matches from API-Tennis.com.
        
        Returns:
            List of TennisMatch objects
        """
        logger.info("Fetching live tennis matches from API-Tennis.com")
        
        try:
            data = await self._make_request("get_livescore")
            
            if not data:
                logger.warning("No data returned from live matches endpoint")
                return []
            
            matches = self._parse_matches_from_data(data)
            logger.info(f"Found {len(matches)} live tennis matches")
            return matches
            
        except Exception as e:
            logger.error(f"Failed to fetch live matches: {e}")
            return []
    
    def _parse_matches_from_data(self, data: Dict[str, Any]) -> List[TennisMatch]:
        """
        Parse matches from API response data.
        
        Args:
            data: API response data
            
        Returns:
            List of TennisMatch objects
        """
        matches = []
        
        try:
            # API-Tennis.com response format: {"success": 1, "result": [...]}
            if data.get("success") == 1 and "result" in data:
                match_list = data["result"]
            elif isinstance(data, list):
                match_list = data
            else:
                logger.warning(f"Unexpected API response format: {data}")
                return matches
            
            for match_data in match_list:
                try:
                    match = self._parse_match_data(match_data)
                    if match:
                        matches.append(match)
                except Exception as e:
                    logger.warning(f"Failed to parse match data: {e}")
                    continue
            
            logger.debug(f"Parsed {len(matches)} matches from API response")
            
        except Exception as e:
            logger.error(f"Failed to parse matches from API response: {e}")
        
        return matches
    
    def _parse_match_data(self, match_data: Dict[str, Any]) -> Optional[TennisMatch]:
        """
        Parse raw match data into TennisMatch object.
        
        Args:
            match_data: Raw match data from API
            
        Returns:
            TennisMatch object or None if parsing fails
        """
        try:
            match_id = str(match_data.get("event_key", ""))
            
            if not match_id:
                return None
            
            # Extract player names from API-Tennis.com format
            player1_name = match_data.get("event_first_player", "Unknown Player")
            player2_name = match_data.get("event_second_player", "Unknown Player")
            
            # Parse set scores from final result (e.g., "1 - 1")
            final_result = match_data.get("event_final_result", "0 - 0")
            try:
                set_scores = final_result.split(" - ")
                sets = (int(set_scores[0]), int(set_scores[1]))
            except:
                sets = (0, 0)
            
            # Parse game scores from game result (e.g., "40 - 40")
            game_result = match_data.get("event_game_result", "0 - 0")
            try:
                game_scores = game_result.split(" - ")
                # Convert tennis scores to game numbers
                def tennis_to_game_score(score):
                    if score in ["0", "15", "30", "40"]:
                        return int(score) // 15 if score != "40" else 3
                    elif score == "A":
                        return 4  # Advantage
                    else:
                        return 0
                
                games = (tennis_to_game_score(game_scores[0]), tennis_to_game_score(game_scores[1]))
            except:
                games = (0, 0)
            
            # For points, we'll use the game scores as a proxy
            points = games
            
            # Determine server
            server_info = match_data.get("event_serve", "First Player")
            server_serving = server_info == "First Player"
            
            # Check if match is live
            is_live = match_data.get("event_live", "0") == "1"
            status = match_data.get("event_status", "unknown")
            
            # Extract additional match info
            tournament = match_data.get("tournament_name", "Unknown Tournament")
            surface = "Hard"  # Default, not provided in API
            match_format = "BO3"  # Default, not provided in API
            
            # Current set from status (e.g., "Set 3")
            try:
                current_set = int(status.split()[-1]) if "Set" in status else 1
            except:
                current_set = 1
            
            # Duration not provided in this API response
            duration = None
            
            return TennisMatch(
                match_id=match_id,
                player_names=(player1_name, player2_name),
                sets=sets,
                games=games,
                points=points,
                server_serving=server_serving,
                is_live=is_live,
                tournament=tournament,
                surface=surface,
                match_format=match_format,
                timestamp=datetime.now(),
                status=status,
                current_set=current_set,
                duration=duration,
                data_source="api-tennis.com"
            )
            
        except Exception as e:
            logger.error(f"Failed to parse match data: {e}")
            return None
    
    async def get_match_details(self, match_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed statistics for a specific match.
        
        Args:
            match_id: API-Tennis.com match ID
            
        Returns:
            Detailed match data or None if not found
        """
        try:
            data = await self._make_request("get_livescore", {"match_key": match_id})
            return data
            
        except Exception as e:
            logger.error(f"Failed to get match details for {match_id}: {e}")
            return None
    
    async def get_player_profile(self, player_id: str) -> Optional[Dict[str, Any]]:
        """
        Get player profile information.
        
        Args:
            player_id: API-Tennis.com player ID
            
        Returns:
            Player profile data or None if not found
        """
        try:
            data = await self._make_request("get_players", {"player_key": player_id})
            return data
            
        except Exception as e:
            logger.error(f"Failed to get player profile for {player_id}: {e}")
            return None
    
    async def get_tournament_matches(self, tournament_id: str) -> Optional[Dict[str, Any]]:
        """
        Get tournament schedule and matches.
        
        Args:
            tournament_id: API-Tennis.com tournament ID
            
        Returns:
            Tournament data or None if not found
        """
        try:
            data = await self._make_request("get_fixtures", {"tournament_key": tournament_id})
            return data
            
        except Exception as e:
            logger.error(f"Failed to get tournament matches for {tournament_id}: {e}")
            return None
    
    async def health_check(self) -> bool:
        """
        Perform a health check on the API.
        
        Returns:
            True if API is healthy, False otherwise
        """
        try:
            # Try a simple endpoint
            data = await self._make_request("get_livescore")
            
            if data is not None:
                logger.info("API health check passed")
                return True
            else:
                logger.warning("API health check failed - no data returned")
                return False
                
        except Exception as e:
            logger.error(f"API health check failed: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get client statistics"""
        success_rate = (self.successful_requests / max(1, self.total_requests)) * 100
        
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": f"{success_rate:.1f}%",
            "api_key_configured": bool(self.api_key),
            "base_url": self.base_url
        }


class APITennisFeed:
    """
    Main tennis feed class using the API-Tennis.com client.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.client = APITennisClient(api_key)
        logger.info("APITennisFeed initialized")
    
    async def get_active_matches(self) -> List[str]:
        """
        Get active tennis match IDs.
        
        Returns:
            List of match IDs
        """
        matches = await self.get_live_matches()
        return [match.match_id for match in matches]
    
    async def get_live_matches(self) -> List[TennisMatch]:
        """
        Get live tennis matches.
        
        Returns:
            List of TennisMatch objects
        """
        return await self.client.get_live_matches()
    
    async def get_match_state(self, match_id: str) -> Optional[TennisMatch]:
        """
        Get current state of a specific match.
        
        Args:
            match_id: Match ID
            
        Returns:
            TennisMatch object or None if not found
        """
        matches = await self.get_live_matches()
        
        for match in matches:
            if match.match_id == match_id:
                return match
        
        return None
    
    async def health_check(self) -> bool:
        """Check if the API is healthy"""
        return await self.client.health_check()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get feed statistics"""
        return self.client.get_statistics()


# Test function
async def test_api_tennis_integration():
    """Test the API-Tennis.com integration"""
    print("🧪 Testing API-Tennis.com Integration")
    print("=" * 50)
    
    # Check if API key is configured
    api_key = os.getenv("API_TENNIS_KEY")
    if not api_key or api_key == "your-api-tennis-key-here":
        print("❌ API key not configured!")
        print("Please:")
        print("1. Copy .env.template to .env")
        print("2. Get your API key from https://api-tennis.com")
        print("3. Add your API key to the .env file")
        return
    
    feed = APITennisFeed()
    
    try:
        # Test health check
        print("Testing API health check...")
        is_healthy = await feed.health_check()
        
        if is_healthy:
            print("✅ API health check passed")
        else:
            print("❌ API health check failed")
            return
        
        # Test getting live matches
        print("\nTesting get_live_matches()...")
        matches = await feed.get_live_matches()
        
        print(f"✅ Found {len(matches)} live matches")
        
        if matches:
            print("\nMatch details:")
            for i, match in enumerate(matches[:3], 1):  # Show first 3
                print(f"  {i}. {match.player_names[0]} vs {match.player_names[1]}")
                print(f"     Match ID: {match.match_id}")
                print(f"     Score: {match.sets[0]}-{match.sets[1]} sets")
                print(f"     Tournament: {match.tournament}")
                print(f"     Status: {match.status}")
                print(f"     Live: {match.is_live}")
        else:
            print("ℹ️  No live matches found (this is normal during off-hours)")
        
        # Test getting match IDs
        print(f"\nTesting get_active_matches()...")
        match_ids = await feed.get_active_matches()
        print(f"✅ Found {len(match_ids)} match IDs")
        
        if match_ids:
            print(f"Match IDs: {match_ids[:3]}...")  # Show first 3
        
        # Show statistics
        print(f"\n📊 API Statistics:")
        stats = feed.get_statistics()
        for key, value in stats.items():
            print(f"   {key}: {value}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
    
    print("\n🎉 API-Tennis.com integration test completed!")


if __name__ == "__main__":
    asyncio.run(test_api_tennis_integration())
