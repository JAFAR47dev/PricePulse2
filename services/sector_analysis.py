import requests
from typing import Dict, Optional, List
import time
import os
from dotenv import load_dotenv

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
        
        # Set base URL and headers
        self.base_url = "https://api.coingecko.com/api/v3"
        
        if self.api_key:
            self.headers = {"x-cg-demo-api-key": self.api_key}
        else:
            self.headers = {}
        
        # MASSIVELY EXPANDED CoinGecko coin ID mapping
        self.coin_id_map = {
            # Layer 1s (20+ coins)
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
            "BNB": "binancecoin",
            "ADA": "cardano",
            "AVAX": "avalanche-2",
            "DOT": "polkadot",
            "MATIC": "matic-network",
            "ATOM": "cosmos",
            "TON": "the-open-network",
            "NEAR": "near",
            "APT": "aptos",
            "SUI": "sui",
            "INJ": "injective-protocol",
            "TIA": "celestia",
            "SEI": "sei-network",
            "FTM": "fantom",
            "ALGO": "algorand",
            "XTZ": "tezos",
            "EOS": "eos",
            
            # DeFi (25+ coins)
            "UNI": "uniswap",
            "AAVE": "aave",
            "MKR": "maker",
            "CRV": "curve-dao-token",
            "LINK": "chainlink",
            "LDO": "lido-dao",
            "SNX": "havven",
            "COMP": "compound-governance-token",
            "SUSHI": "sushi",
            "RUNE": "thorchain",
            "GMX": "gmx",
            "CAKE": "pancakeswap-token",
            "1INCH": "1inch",
            "BAL": "balancer",
            "YFI": "yearn-finance",
            "DYDX": "dydx",
            "PENDLE": "pendle",
            "JUP": "jupiter-exchange-solana",
            "RAY": "raydium",
            "ORCA": "orca",
            "WOO": "woo-network",
            "PERP": "perpetual-protocol",
            "ALPHA": "alpha-finance",
            "GALA": "gala",
            
            # Meme Coins (20+ coins)
            "DOGE": "dogecoin",
            "SHIB": "shiba-inu",
            "PEPE": "pepe",
            "FLOKI": "floki",
            "BONK": "bonk",
            "WIF": "dogwifcoin",
            "MEME": "memecoin",
            "DEGEN": "degen-base",
            "MYRO": "myro",
            "POPCAT": "popcat",
            "MEW": "cat-in-a-dogs-world",
            "BRETT": "based-brett",
            "MOG": "mog-coin",
            "BABYDOGE": "baby-doge-coin",
            "ELON": "dogelon-mars",
            "KISHU": "kishu-inu",
            "SAMO": "samoyedcoin",
            
            # AI/ML (20+ coins)
            "RNDR": "render-token",
            "FET": "fetch-ai",
            "AGIX": "singularitynet",
            "GRT": "the-graph",
            "OCEAN": "ocean-protocol",
            "TAO": "bittensor",
            "AKT": "akash-network",
            "NMR": "numeraire",
            "ARKM": "arkham",
            "PHB": "phoenix-global",
            "ROSE": "oasis-network",
            "IQAI": "iq",
            "CTXC": "cortex",
            "ORAI": "oraichain-token",
            "DBC": "deepbrain-chain",
            
            # Gaming (15+ coins)
            "IMX": "immutable-x",
            "SAND": "the-sandbox",
            "MANA": "decentraland",
            "AXS": "axie-infinity",
            "GALA": "gala",
            "ENJ": "enjincoin",
            "BEAM": "beam-2",
            "PRIME": "echelon-prime",
            "PIXEL": "pixels",
            "RONIN": "ronin",
            "ILV": "illuvium",
            "MAGIC": "magic",
            "YGG": "yield-guild-games",
            
            # NFT/Metaverse (12+ coins)
            "BLUR": "blur",
            "LOOKS": "looksrare",
            "APE": "apecoin",
            "RNDR": "render-token",
            "THETA": "theta-token",
            "CHZ": "chiliz",
            "FLOW": "flow",
            "CELO": "celo",
            
            # Privacy (10+ coins)
            "XMR": "monero",
            "ZEC": "zcash",
            "SCRT": "secret",
            "DASH": "dash",
            "FIRO": "zcoin",
            "ARRR": "pirate-chain",
            
            # Infrastructure (15+ coins)
            "FIL": "filecoin",
            "AR": "arweave",
            "STX": "blockstack",
            "RNDR": "render-token",
            "HNT": "helium",
            "STORJ": "storj",
            "ANKR": "ankr",
        }
        
        # EXPANDED SECTOR DEFINITIONS (10-20 coins per sector)
        self.sectors = {
            "layer1": [
                # Top by market cap for accuracy
                "BTC", "ETH", "BNB", "SOL", "ADA", "AVAX", "DOT", "MATIC", 
                "ATOM", "TON", "NEAR", "APT", "SUI", "INJ", "TIA", "SEI",
                "FTM", "ALGO", "XTZ", "EOS"
            ],
            
            "defi": [
                # Top DeFi protocols
                "UNI", "AAVE", "MKR", "LINK", "CRV", "LDO", "SNX", "COMP",
                "SUSHI", "RUNE", "GMX", "CAKE", "1INCH", "BAL", "YFI",
                "DYDX", "PENDLE", "JUP", "RAY", "ORCA", "WOO", "PERP"
            ],
            
            "meme": [
                # Top meme coins by market cap and volume
                "DOGE", "SHIB", "PEPE", "FLOKI", "BONK", "WIF", "MEME",
                "DEGEN", "MYRO", "Popcat", "MEW", "BRETT", "MOG",
                "BABYDOGE", "ELON", "KISHU", "SAMO"
            ],
            
            "ai": [
                # AI/ML focused tokens
                "RNDR", "FET", "AGIX", "GRT", "OCEAN", "TAO", "AKT",
                "NMR", "ARKM", "PHB", "ROSE", "IQAI", "CTXC", "ORAI"
            ],
            
            "gaming": [
                # Gaming & metaverse
                "IMX", "SAND", "MANA", "AXS", "GALA", "ENJ", "BEAM",
                "PRIME", "PIXEL", "RONIN", "ILV", "MAGIC", "YGG"
            ],
            
            "nft": [
                # NFT marketplaces and related
                "BLUR", "LOOKS", "APE", "RNDR", "THETA", "CHZ", "FLOW"
            ],
            
            "privacy": [
                # Privacy coins
                "XMR", "ZEC", "SCRT", "DASH", "FIRO", "ARRR"
            ],
            
            "infrastructure": [
                # Storage, compute, oracles
                "FIL", "AR", "STX", "HNT", "LINK", "STORJ", "ANKR"
            ]
        }
        
        # Minimum coins required per sector for valid analysis
        self.min_coins_for_analysis = 3
    
    def get_sector_analysis(self, sectors_to_analyze: Optional[List[str]] = None) -> Optional[Dict]:
        """
        Get performance analysis for all sectors or specific sectors
        
        Args:
            sectors_to_analyze: List of sector names to analyze, or None for all
        """
        cache_key = f"sector_analysis_{'_'.join(sectors_to_analyze) if sectors_to_analyze else 'all'}"
        
        # Check cache
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration:
                return cached_data
        
        try:
            result = {}
            
            # Determine which sectors to analyze
            sectors = sectors_to_analyze if sectors_to_analyze else self.sectors.keys()
            
            for sector_name in sectors:
                if sector_name not in self.sectors:
                    print(f"Unknown sector: {sector_name}")
                    continue
                
                coins = self.sectors[sector_name]
                sector_performance = self._analyze_sector_performance(coins, sector_name)
                result[sector_name] = sector_performance
            
            # Cache result
            self.cache[cache_key] = (result, time.time())
            return result
            
        except Exception as e:
            print(f"Error analyzing sectors: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _analyze_sector_performance(self, coins: List[str], sector_name: str) -> Dict:
        """
        Analyze average performance of a sector with improved accuracy
        Uses market-cap weighted average and filters out low-quality data
        """
        try:
            # Convert symbols to CoinGecko IDs
            coin_ids = [self.coin_id_map.get(symbol) for symbol in coins if symbol in self.coin_id_map]
            
            if len(coin_ids) < self.min_coins_for_analysis:
                return {
                    "momentum": "unknown",
                    "emoji": "❓",
                    "avg_change": 0,
                    "avg_volume": 0,
                    "coins_tracked": 0,
                    "status": "insufficient_data",
                    "data_quality": "low"
                }
            
            # Fetch market data for all coins in batches (API limit is 250 per request)
            all_coins_data = []
            batch_size = 50  # Process 50 coins at a time to avoid overwhelming API
            
            for i in range(0, len(coin_ids), batch_size):
                batch = coin_ids[i:i + batch_size]
                
                url = f"{self.base_url}/coins/markets"
                params = {
                    "vs_currency": "usd",
                    "ids": ",".join(batch),
                    "order": "market_cap_desc",
                    "per_page": len(batch),
                    "page": 1,
                    "sparkline": "false",
                    "price_change_percentage": "24h"
                }
                
                response = requests.get(url, params=params, headers=self.headers, timeout=15)
                response.raise_for_status()
                batch_data = response.json()
                
                all_coins_data.extend(batch_data)
                
                # Small delay to respect rate limits
                if i + batch_size < len(coin_ids):
                    time.sleep(0.3)
            
            if not all_coins_data:
                return {
                    "momentum": "unknown",
                    "emoji": "❓",
                    "avg_change": 0,
                    "avg_volume": 0,
                    "coins_tracked": 0,
                    "status": "no_data",
                    "data_quality": "none"
                }
            
            # Filter out coins with insufficient data
            valid_coins = []
            for coin in all_coins_data:
                # Require: price change data, volume > $100k, market cap > $1M
                if (coin.get('price_change_percentage_24h') is not None and
                    coin.get('total_volume', 0) > 100000 and
                    coin.get('market_cap', 0) > 1000000):
                    valid_coins.append(coin)
            
            if len(valid_coins) < self.min_coins_for_analysis:
                return {
                    "momentum": "unknown",
                    "emoji": "❓",
                    "avg_change": 0,
                    "avg_volume": 0,
                    "coins_tracked": len(all_coins_data),
                    "status": "insufficient_quality_data",
                    "data_quality": "low"
                }
            
            # Calculate market-cap weighted performance
            total_mcap = sum(coin['market_cap'] for coin in valid_coins)
            
            weighted_change = sum(
                coin['price_change_percentage_24h'] * (coin['market_cap'] / total_mcap)
                for coin in valid_coins
            )
            
            # Also calculate simple average for comparison
            simple_avg_change = sum(coin['price_change_percentage_24h'] for coin in valid_coins) / len(valid_coins)
            
            # Calculate volume metrics
            total_volume = sum(coin['total_volume'] for coin in valid_coins)
            avg_volume = total_volume / len(valid_coins)
            
            # Use weighted average as primary metric
            avg_change = weighted_change
            
            # Determine data quality
            data_coverage = len(valid_coins) / len(coin_ids)
            if data_coverage >= 0.8:
                data_quality = "high"
            elif data_coverage >= 0.5:
                data_quality = "medium"
            else:
                data_quality = "low"
            
            # Determine momentum with more granular levels
            if avg_change > 5:
                momentum = "very_strong"
                emoji = "🟢"
                status = "highly_bullish"
            elif avg_change > 2:
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
            elif avg_change > -5:
                momentum = "poor"
                emoji = "🔴"
                status = "bearish"
            else:
                momentum = "very_poor"
                emoji = "🔴"
                status = "highly_bearish"
            
            # Get top/bottom performers
            top_performers = self._get_top_performers(valid_coins)
            
            return {
                "momentum": momentum,
                "emoji": emoji,
                "avg_change": round(avg_change, 2),
                "simple_avg_change": round(simple_avg_change, 2),  # For comparison
                "avg_volume": round(avg_volume, 2),
                "total_volume": round(total_volume, 2),
                "total_market_cap": round(total_mcap, 2),
                "coins_tracked": len(valid_coins),
                "total_coins": len(coin_ids),
                "data_coverage": round(data_coverage * 100, 1),
                "data_quality": data_quality,
                "status": status,
                "individual_performances": top_performers
            }
            
        except Exception as e:
            print(f"Error in sector analysis for {sector_name}: {e}")
            import traceback
            traceback.print_exc()
            return {
                "momentum": "unknown",
                "emoji": "❓",
                "avg_change": 0,
                "avg_volume": 0,
                "coins_tracked": 0,
                "status": "error",
                "data_quality": "none"
            }
    
    def _get_top_performers(self, coins_data: List[Dict]) -> Dict:
        """
        Identify best and worst performers in the sector
        Returns top 3 gainers and top 3 losers
        """
        try:
            if not coins_data:
                return {"best": [], "worst": []}
            
            # Create list of performances
            performances = []
            for coin in coins_data:
                change = coin.get('price_change_percentage_24h')
                if change is not None:
                    performances.append({
                        "name": coin.get('name', 'Unknown'),
                        "symbol": coin.get('symbol', '').upper(),
                        "change": round(change, 2),
                        "volume": coin.get('total_volume', 0),
                        "market_cap": coin.get('market_cap', 0)
                    })
            
            # Sort by performance
            performances.sort(key=lambda x: x['change'], reverse=True)
            
            # Get top 3 and bottom 3
            best_performers = performances[:3] if len(performances) >= 3 else performances
            worst_performers = performances[-3:] if len(performances) >= 3 else []
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
        Get a comparative analysis of all sectors with improved metrics
        """
        cache_key = "sector_comparison_v2"
        
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration:
                return cached_data
        
        try:
            sector_analysis = self.get_sector_analysis()
            
            if not sector_analysis:
                return None
            
            # Rank sectors by performance (weighted by data quality)
            sector_rankings = []
            for sector_name, data in sector_analysis.items():
                # Skip sectors with insufficient data
                if data['data_quality'] == 'none' or data['coins_tracked'] < self.min_coins_for_analysis:
                    continue
                
                sector_rankings.append({
                    "sector": sector_name,
                    "avg_change": data['avg_change'],
                    "momentum": data['momentum'],
                    "emoji": data['emoji'],
                    "data_quality": data['data_quality'],
                    "coverage": data.get('data_coverage', 0),
                    "coins_tracked": data['coins_tracked']
                })
            
            # Sort by performance (descending)
            sector_rankings.sort(key=lambda x: x['avg_change'], reverse=True)
            
            if not sector_rankings:
                return None
            
            # Determine market leadership
            best_sector = sector_rankings[0]
            worst_sector = sector_rankings[-1]
            
            # Calculate overall market breadth (weighted by data quality)
            high_quality_sectors = [s for s in sector_rankings if s['data_quality'] in ['high', 'medium']]
            positive_sectors = sum(1 for s in high_quality_sectors if s['avg_change'] > 0)
            total_quality_sectors = len(high_quality_sectors)
            
            if total_quality_sectors > 0:
                breadth_pct = (positive_sectors / total_quality_sectors) * 100
            else:
                breadth_pct = 50
            
            if breadth_pct >= 75:
                market_breadth = "strong"
                breadth_desc = "Broad market strength across sectors"
            elif breadth_pct >= 50:
                market_breadth = "moderate"
                breadth_desc = "Mixed sector performance"
            else:
                market_breadth = "weak"
                breadth_desc = "Broad market weakness"
            
            # Calculate sector rotation signal
            rotation = self._detect_sector_rotation(sector_rankings)
            
            result = {
                "rankings": sector_rankings,
                "best_sector": best_sector,
                "worst_sector": worst_sector,
                "market_breadth": market_breadth,
                "breadth_pct": round(breadth_pct, 1),
                "breadth_desc": breadth_desc,
                "total_sectors_analyzed": len(sector_rankings),
                "rotation_signal": rotation
            }
            
            self.cache[cache_key] = (result, time.time())
            return result
            
        except Exception as e:
            print(f"Error in sector comparison: {e}")
            return None
    
    def _detect_sector_rotation(self, rankings: List[Dict]) -> Dict:
        """Detect if money is rotating between sectors"""
        if len(rankings) < 2:
            return {"status": "insufficient_data", "description": "Not enough sectors to detect rotation"}
        
        # Check if traditional "risk-on" sectors (meme, gaming) outperforming "safe" sectors (layer1, defi)
        risk_on_sectors = ['meme', 'gaming', 'nft']
        safe_sectors = ['layer1', 'defi']
        
        risk_on_performance = []
        safe_performance = []
        
        for sector in rankings:
            if sector['sector'] in risk_on_sectors:
                risk_on_performance.append(sector['avg_change'])
            elif sector['sector'] in safe_sectors:
                safe_performance.append(sector['avg_change'])
        
        if risk_on_performance and safe_performance:
            avg_risk_on = sum(risk_on_performance) / len(risk_on_performance)
            avg_safe = sum(safe_performance) / len(safe_performance)
            
            diff = avg_risk_on - avg_safe
            
            if diff > 2:
                return {
                    "status": "risk_on",
                    "description": "Money rotating into risk-on sectors (memes, gaming)",
                    "strength": "strong" if diff > 5 else "moderate"
                }
            elif diff < -2:
                return {
                    "status": "risk_off",
                    "description": "Money rotating into safe sectors (BTC, ETH, DeFi)",
                    "strength": "strong" if diff < -5 else "moderate"
                }
        
        return {
            "status": "neutral",
            "description": "No clear sector rotation detected"
        }