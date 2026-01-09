import requests
from typing import Dict, Optional
import time
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class MacroDataService:
    """Fetches macro indicators that affect crypto using CoinGecko API"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize with CoinGecko API key from environment or parameter
        Looks for COINGECKO_API_KEY in .env file
        """
        self.cache = {}
        self.cache_duration = 3600  # 1 hour
        
        # Get API key from parameter, env, or use free tier
        self.api_key = api_key or os.getenv('COINGECKO_API_KEY')
        
        # Set base URL and headers based on API key availability
        if self.api_key:
            self.base_url = "https://api.coingecko.com/api/v3"
            self.headers = {"x-cg-demo-api-key": self.api_key}
        else:
            self.base_url = "https://api.coingecko.com/api/v3"
            self.headers = {}
    
    def get_macro_indicators(self) -> Optional[Dict]:
        """Get macro market indicators"""
        cache_key = "macro_data"
        
        # Check cache
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration:
                return cached_data
        
        try:
            # Get BTC and USDT dominance from global data
            btc_dom, usdt_dom, total_stablecoin_dom = self._get_dominance_data()
            
            # Get exchange flow data (inflow/outflow from exchanges)
            exchange_flow = self._get_exchange_flow_indicator()
            
            # Get funding rate from derivatives
            funding_rate = self._get_funding_rate_estimate()
            
            result = {
                "btc_dominance": btc_dom,
                "usdt_dominance": usdt_dom,
                "total_stablecoin_dominance": total_stablecoin_dom,
                "exchange_flow": exchange_flow,
                "funding_rate": funding_rate
            }
            
            # Cache result
            self.cache[cache_key] = (result, time.time())
            return result
            
        except Exception as e:
            print(f"Error fetching macro data: {e}")
            import traceback
            traceback.print_exc()
            
            # Return fallback data
            return {
                "btc_dominance": 50.0,
                "usdt_dominance": 5.0,
                "total_stablecoin_dominance": 7.0,
                "exchange_flow": "neutral",
                "funding_rate": 0.01
            }
    
    def _get_dominance_data(self) -> tuple:
        """
        Get BTC dominance, USDT dominance, and total stablecoin dominance
        Returns: (btc_dom, usdt_dom, total_stable_dom)
        """
        try:
            # Get global market data
            url = f"{self.base_url}/global"
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            global_data = response.json()['data']
            
            # BTC dominance
            btc_dominance = round(global_data['market_cap_percentage'].get('btc', 50.0), 2)
            
            # Total market cap
            total_market_cap = global_data['total_market_cap']['usd']
            
            # Get stablecoin market caps
            stablecoins = {
                'tether': 'usdt',
                'usd-coin': 'usdc',
                'binance-usd': 'busd',
                'dai': 'dai',
                'true-usd': 'tusd'
            }
            
            total_stablecoin_mcap = 0
            usdt_mcap = 0
            
            for coin_id, symbol in stablecoins.items():
                try:
                    coin_url = f"{self.base_url}/coins/{coin_id}"
                    params = {
                        "localization": "false",
                        "tickers": "false",
                        "market_data": "true",
                        "community_data": "false",
                        "developer_data": "false"
                    }
                    
                    coin_response = requests.get(coin_url, params=params, headers=self.headers, timeout=10)
                    
                    if coin_response.status_code == 200:
                        coin_data = coin_response.json()
                        mcap = coin_data['market_data']['market_cap'].get('usd', 0)
                        total_stablecoin_mcap += mcap
                        
                        if symbol == 'usdt':
                            usdt_mcap = mcap
                    
                    # Small delay to avoid rate limiting
                    time.sleep(0.2)
                    
                except Exception as e:
                    print(f"Error fetching {coin_id}: {e}")
                    continue
            
            # Calculate dominances
            usdt_dominance = round((usdt_mcap / total_market_cap) * 100, 2) if total_market_cap > 0 else 5.0
            total_stablecoin_dominance = round((total_stablecoin_mcap / total_market_cap) * 100, 2) if total_market_cap > 0 else 7.0
            
            return btc_dominance, usdt_dominance, total_stablecoin_dominance
            
        except Exception as e:
            print(f"Error in _get_dominance_data: {e}")
            return 50.0, 5.0, 7.0
    
    def _get_exchange_flow_indicator(self) -> str:
        """
        Estimate exchange flow based on trading volume trends
        Returns: "inflow", "outflow", or "neutral"
        
        Note: True exchange flow data requires on-chain analytics APIs
        This is a simplified indicator based on volume changes
        """
        try:
            # Get BTC market data for volume trend analysis
            url = f"{self.base_url}/coins/bitcoin/market_chart"
            params = {
                "vs_currency": "usd",
                "days": 7,
                "interval": "daily"
            }
            
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            volumes = [v[1] for v in data['total_volumes']]
            
            if len(volumes) < 2:
                return "neutral"
            
            # Compare recent volume to average
            recent_volume = volumes[-1]
            avg_volume = sum(volumes[:-1]) / len(volumes[:-1])
            
            volume_change = ((recent_volume - avg_volume) / avg_volume) * 100
            
            # High volume increase suggests inflow to exchanges (bearish)
            # Volume decrease suggests outflow from exchanges (bullish)
            if volume_change > 20:
                return "inflow"  # More coins on exchanges (potential selling)
            elif volume_change < -20:
                return "outflow"  # Less coins on exchanges (potential accumulation)
            else:
                return "neutral"
                
        except Exception as e:
            print(f"Error in _get_exchange_flow_indicator: {e}")
            return "neutral"
    
    def _get_funding_rate_estimate(self) -> float:
        """
        Get funding rate estimate from derivatives data
        
        Note: CoinGecko doesn't provide funding rates directly
        This uses open interest and price momentum as a proxy
        For real funding rates, you'd need to use exchange APIs or specialized services
        """
        try:
            # Get BTC derivatives data
            url = f"{self.base_url}/coins/bitcoin"
            params = {
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "false",
                "developer_data": "false"
            }
            
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            response.raise_for_status()
            market_data = response.json()['market_data']
            
            # Use price momentum as funding rate proxy
            # Positive momentum typically correlates with positive funding
            price_change_24h = market_data.get('price_change_percentage_24h', 0)
            
            # Estimate funding rate based on momentum
            # Typical funding rates range from -0.05% to +0.05% (per 8h)
            if price_change_24h > 5:
                estimated_funding = 0.03  # Strong bullish momentum
            elif price_change_24h > 2:
                estimated_funding = 0.015
            elif price_change_24h > -2:
                estimated_funding = 0.005  # Neutral
            elif price_change_24h > -5:
                estimated_funding = -0.01
            else:
                estimated_funding = -0.02  # Strong bearish momentum
            
            return round(estimated_funding, 4)
            
        except Exception as e:
            print(f"Error in _get_funding_rate_estimate: {e}")
            return 0.01  # Default neutral funding rate
    
    def get_altcoin_season_index(self) -> Dict:
        """
        Calculate Altcoin Season Index
        Returns score 0-100 where >75 = alt season, <25 = BTC season
        """
        cache_key = "altseason_index"
        
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration:
                return cached_data
        
        try:
            # Get top 50 coins performance vs BTC
            url = f"{self.base_url}/coins/markets"
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 50,
                "page": 1,
                "price_change_percentage": "30d"
            }
            
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            response.raise_for_status()
            coins = response.json()
            
            # Get BTC 30d performance
            btc_performance = next((c['price_change_percentage_30d_in_currency'] 
                                   for c in coins if c['symbol'].lower() == 'btc'), 0)
            
            # Count how many alts outperformed BTC
            alts_outperforming = 0
            total_alts = 0
            
            for coin in coins:
                if coin['symbol'].lower() == 'btc':
                    continue
                
                alt_performance = coin.get('price_change_percentage_30d_in_currency', 0)
                if alt_performance and alt_performance > btc_performance:
                    alts_outperforming += 1
                total_alts += 1
            
            # Calculate index (0-100)
            if total_alts > 0:
                index = int((alts_outperforming / total_alts) * 100)
            else:
                index = 50
            
            # Determine season
            if index >= 75:
                season = "alt_season"
                description = "Strong alt season - Most alts outperforming BTC"
            elif index >= 60:
                season = "alt_favorable"
                description = "Alt-friendly market"
            elif index >= 40:
                season = "neutral"
                description = "Mixed market - No clear leader"
            elif index >= 25:
                season = "btc_favorable"
                description = "BTC-friendly market"
            else:
                season = "btc_season"
                description = "BTC season - Most alts underperforming"
            
            result = {
                "index": index,
                "season": season,
                "description": description,
                "alts_outperforming": alts_outperforming,
                "total_alts_checked": total_alts
            }
            
            self.cache[cache_key] = (result, time.time())
            return result
            
        except Exception as e:
            print(f"Error calculating altcoin season index: {e}")
            return {
                "index": 50,
                "season": "neutral",
                "description": "Unable to determine market leadership",
                "alts_outperforming": 0,
                "total_alts_checked": 0
            }