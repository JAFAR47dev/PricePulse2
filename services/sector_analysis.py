import requests
from typing import Dict, Optional, List
import time
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class SectorAnalysisService:
    """Analyzes performance of different crypto sectors using CoinGecko API"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize with CoinGecko API key from environment or parameter
        Looks for COINGECKO_API_KEY in .env file
        """
        self.cache = {}
        self.cache_duration = 1800  # 30 minutes
        
        # Get API key from parameter, env, or use free tier
        self.api_key = api_key or os.getenv('COINGECKO_API_KEY')
        
        # Set base URL and headers based on API key availability
        if self.api_key:
            self.base_url = "https://api.coingecko.com/api/v3"
            self.headers = {"x-cg-demo-api-key": self.api_key}
        else:
            self.base_url = "https://api.coingecko.com/api/v3"
            self.headers = {}
        
        # CoinGecko coin ID mapping for sector representatives
        self.coin_id_map = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
            "AVAX": "avalanche-2",
            "MATIC": "matic-network",
            "UNI": "uniswap",
            "AAVE": "aave",
            "MKR": "maker",
            "CRV": "curve-dao-token",
            "LINK": "chainlink",
            "DOGE": "dogecoin",
            "SHIB": "shiba-inu",
            "PEPE": "pepe",
            "FLOKI": "floki",
            "BONK": "bonk",
            "RNDR": "render-token",
            "FET": "fetch-ai",
            "AGIX": "singularitynet",
            "GRT": "the-graph",
            "OCEAN": "ocean-protocol"
        }
        
        # Define sector representatives (using symbols for readability)
        self.sectors = {
            "layer1": ["BTC", "ETH", "SOL", "AVAX", "MATIC"],
            "defi": ["UNI", "AAVE", "MKR", "CRV", "LINK"],
            "meme": ["DOGE", "SHIB", "PEPE", "FLOKI", "BONK"],
            "ai": ["RNDR", "FET", "AGIX", "GRT", "OCEAN"]
        }
    
    def get_sector_analysis(self) -> Optional[Dict]:
        """Get performance analysis for all sectors"""
        cache_key = "sector_analysis"
        
        # Check cache
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration:
                return cached_data
        
        try:
            result = {}
            
            for sector_name, coins in self.sectors.items():
                sector_performance = self._analyze_sector_performance(coins)
                result[sector_name] = sector_performance
            
            # Cache result
            self.cache[cache_key] = (result, time.time())
            return result
            
        except Exception as e:
            print(f"Error analyzing sectors: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _analyze_sector_performance(self, coins: List[str]) -> Dict:
        """
        Analyze average performance of a sector
        Uses batch API call for efficiency
        """
        try:
            # Convert symbols to CoinGecko IDs
            coin_ids = [self.coin_id_map.get(symbol) for symbol in coins if symbol in self.coin_id_map]
            
            if not coin_ids:
                return {
                    "momentum": "unknown",
                    "emoji": "❓",
                    "avg_change": 0,
                    "avg_volume": 0,
                    "coins_tracked": 0,
                    "status": "no_valid_coins"
                }
            
            # Fetch market data for all coins in one batch call
            url = f"{self.base_url}/coins/markets"
            params = {
                "vs_currency": "usd",
                "ids": ",".join(coin_ids),
                "order": "market_cap_desc",
                "per_page": len(coin_ids),
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "24h"
            }
            
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            response.raise_for_status()
            coins_data = response.json()
            
            if not coins_data:
                return {
                    "momentum": "unknown",
                    "emoji": "❓",
                    "avg_change": 0,
                    "avg_volume": 0,
                    "coins_tracked": 0,
                    "status": "no_data"
                }
            
            # Extract performance metrics
            changes = []
            volumes = []
            market_caps = []
            
            for coin in coins_data:
                change_24h = coin.get('price_change_percentage_24h')
                volume_24h = coin.get('total_volume')
                market_cap = coin.get('market_cap')
                
                if change_24h is not None:
                    changes.append(change_24h)
                
                if volume_24h is not None:
                    volumes.append(volume_24h)
                
                if market_cap is not None:
                    market_caps.append(market_cap)
            
            if not changes:
                return {
                    "momentum": "unknown",
                    "emoji": "❓",
                    "avg_change": 0,
                    "avg_volume": 0,
                    "coins_tracked": 0,
                    "status": "no_data"
                }
            
            # Calculate weighted average (by market cap) for more accurate sector performance
            if market_caps and len(market_caps) == len(changes):
                total_mcap = sum(market_caps)
                weighted_change = sum(changes[i] * (market_caps[i] / total_mcap) 
                                    for i in range(len(changes)))
                avg_change = weighted_change
            else:
                # Fallback to simple average if market cap data missing
                avg_change = sum(changes) / len(changes)
            
            avg_volume = sum(volumes) / len(volumes) if volumes else 0
            
            # Determine momentum and assign emoji
            if avg_change > 2:
                momentum = "strong"
                emoji = "🟢"
                status = "bullish"
            elif avg_change > 0.5:
                momentum = "moderate"
                emoji = "🟢"
                status = "slightly_bullish"
            elif avg_change > -0.5:
                momentum = "neutral"
                emoji = "🔶"
                status = "neutral"
            elif avg_change > -2:
                momentum = "weak"
                emoji = "🔶"
                status = "slightly_bearish"
            else:
                momentum = "very_weak"
                emoji = "🔴"
                status = "bearish"
            
            return {
                "momentum": momentum,
                "emoji": emoji,
                "avg_change": round(avg_change, 2),
                "avg_volume": round(avg_volume, 2),
                "coins_tracked": len(changes),
                "status": status,
                "individual_performances": self._get_top_performers(coins_data, changes)
            }
            
        except Exception as e:
            print(f"Error in sector analysis: {e}")
            import traceback
            traceback.print_exc()
            return {
                "momentum": "unknown",
                "emoji": "❓",
                "avg_change": 0,
                "avg_volume": 0,
                "coins_tracked": 0,
                "status": "error"
            }
    
    def _get_top_performers(self, coins_data: List[Dict], changes: List[float]) -> Dict:
        """
        Identify best and worst performers in the sector
        Returns top 2 gainers and top 2 losers
        """
        try:
            if not coins_data or not changes:
                return {"best": [], "worst": []}
            
            # Create list of (coin_name, symbol, change) tuples
            performances = []
            for coin in coins_data:
                change = coin.get('price_change_percentage_24h')
                if change is not None:
                    performances.append({
                        "name": coin.get('name', 'Unknown'),
                        "symbol": coin.get('symbol', '').upper(),
                        "change": round(change, 2)
                    })
            
            # Sort by performance
            performances.sort(key=lambda x: x['change'], reverse=True)
            
            # Get top 2 and bottom 2
            best_performers = performances[:2] if len(performances) >= 2 else performances
            worst_performers = performances[-2:] if len(performances) >= 2 else []
            worst_performers.reverse()  # Show worst first
            
            return {
                "best": best_performers,
                "worst": worst_performers
            }
            
        except Exception as e:
            print(f"Error identifying top performers: {e}")
            return {"best": [], "worst": []}
    
    def get_sector_comparison(self) -> Optional[Dict]:
        """
        Get a comparative analysis of all sectors
        Returns sectors ranked by performance
        """
        cache_key = "sector_comparison"
        
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration:
                return cached_data
        
        try:
            sector_analysis = self.get_sector_analysis()
            
            if not sector_analysis:
                return None
            
            # Rank sectors by performance
            sector_rankings = []
            for sector_name, data in sector_analysis.items():
                sector_rankings.append({
                    "sector": sector_name,
                    "avg_change": data['avg_change'],
                    "momentum": data['momentum'],
                    "emoji": data['emoji']
                })
            
            # Sort by performance (descending)
            sector_rankings.sort(key=lambda x: x['avg_change'], reverse=True)
            
            # Determine market leadership
            best_sector = sector_rankings[0]
            worst_sector = sector_rankings[-1]
            
            # Calculate overall market breadth
            positive_sectors = sum(1 for s in sector_rankings if s['avg_change'] > 0)
            total_sectors = len(sector_rankings)
            breadth_pct = (positive_sectors / total_sectors) * 100
            
            if breadth_pct >= 75:
                market_breadth = "strong"
                breadth_desc = "Broad market strength"
            elif breadth_pct >= 50:
                market_breadth = "moderate"
                breadth_desc = "Mixed sector performance"
            else:
                market_breadth = "weak"
                breadth_desc = "Broad market weakness"
            
            result = {
                "rankings": sector_rankings,
                "best_sector": best_sector,
                "worst_sector": worst_sector,
                "market_breadth": market_breadth,
                "breadth_pct": round(breadth_pct, 1),
                "breadth_desc": breadth_desc
            }
            
            self.cache[cache_key] = (result, time.time())
            return result
            
        except Exception as e:
            print(f"Error in sector comparison: {e}")
            return None