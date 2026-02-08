import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import time
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class MarketDataService:
    """Fetches and processes market data for multiple coins using CoinGecko API"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize with CoinGecko API key from environment or parameter
        Looks for COINGECKO_API_KEY in .env file
        """
        self.cache = {}
        self.cache_duration = 1800  # 30 minutes
        
        # Get API key from parameter, env, or use free tier
        self.api_key = api_key or os.getenv('COINGECKO_API_KEY')
        
        # MASSIVELY EXPANDED CoinGecko coin ID mapping (100+ coins)
        self.coin_ids = {
            # Layer 1 Blockchains (20+ coins)
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
            "KAS": "kaspa",
            "HBAR": "hedera-hashgraph",
            "VET": "vechain",
            "ICP": "internet-computer",
            "XLM": "stellar",
            
            # DeFi Tokens (25+ coins)
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
            "CVX": "convex-finance",
            "FXS": "frax-share",
            
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
            "CORGI": "corgiai",
            
            # AI/ML Tokens (15+ coins)
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
            "CTXC": "cortex",
            "ORAI": "oraichain-token",
            "DBC": "deepbrain-chain",
            "AIOZ": "aioz-network",
            
            # Gaming & Metaverse (15+ coins)
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
            "GHST": "aavegotchi",
            "NAKA": "nakamoto-games",
            
            # NFT Platforms (10+ coins)
            "BLUR": "blur",
            "LOOKS": "looksrare",
            "APE": "apecoin",
            "THETA": "theta-token",
            "CHZ": "chiliz",
            "FLOW": "flow",
            "CELO": "celo",
            "AUDIO": "audius",
            
            # Privacy Coins (8+ coins)
            "XMR": "monero",
            "ZEC": "zcash",
            "SCRT": "secret",
            "DASH": "dash",
            "FIRO": "zcoin",
            "ARRR": "pirate-chain",
            "DERO": "dero",
            
            # Infrastructure (15+ coins)
            "FIL": "filecoin",
            "AR": "arweave",
            "STX": "blockstack",
            "HNT": "helium",
            "STORJ": "storj",
            "ANKR": "ankr",
            "IOTX": "iotex",
            "SC": "siacoin",
            
            # Exchange Tokens (10+ coins)
            "CRO": "crypto-com-chain",
            "OKB": "okb",
            "GT": "gatechain-token",
            "KCS": "kucoin-shares",
            "HT": "huobi-token",
            "MX": "mx-token",
            
            # Stable/Liquid Staking (8+ coins)
            "USDT": "tether",
            "USDC": "usd-coin",
            "DAI": "dai",
            "FRAX": "frax",
            "STETH": "staked-ether",
            "RETH": "rocket-pool-eth",
            "WSTETH": "wrapped-steth",
            
            # Other Notable Projects
            "OP": "optimism",
            "ARB": "arbitrum",
            "LTC": "litecoin",
            "BCH": "bitcoin-cash",
            "ETC": "ethereum-classic",
            "XRP": "ripple",
            "TRX": "tron",
            "MATIC": "matic-network",
        }
        
        # Set base URL and headers based on API key availability
        self.base_url = "https://api.coingecko.com/api/v3"
        
        if self.api_key:
            # Demo API key uses x-cg-demo-api-key header
            self.headers = {"x-cg-demo-api-key": self.api_key}
        else:
            self.headers = {}
    
    def get_coin_data(self, symbol: str) -> Optional[Dict]:
        """
        Get comprehensive data for a specific coin
        symbol: "BTC", "ETH", etc.
        """
        cache_key = f"{symbol}_data"
        
        # Check cache
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration:
                return cached_data
        
        try:
            coin_id = self.coin_ids.get(symbol)
            if not coin_id:
                print(f"Unknown symbol: {symbol}")
                return None
            
            # Fetch current price and 24h data
            market_data = self._fetch_coin_market_data(coin_id)
            
            # Fetch historical data for technical indicators (90 days)
            ohlc_data = self._fetch_ohlc_data(coin_id, days=90)
            
            if not market_data or not ohlc_data:
                return None
            
            # Extract current data
            current_price = market_data['current_price']['usd']
            high_24h = market_data['high_24h']['usd']
            low_24h = market_data['low_24h']['usd']
            change_24h = market_data['price_change_percentage_24h']
            volume_24h = market_data['total_volume']['usd']
            market_cap = market_data['market_cap']['usd']
            
            # Calculate technical indicators from OHLC data
            closes = [candle[4] for candle in ohlc_data]  # Close prices
            volumes = [candle[5] for candle in ohlc_data]  # Volumes
            
            ma_50 = self._calculate_ma(closes, period=50)
            ma_200 = self._calculate_ma(closes, period=200)
            rsi = self._calculate_rsi(closes, period=14)
            
            # Volume analysis (7-day average)
            volume_ma = self._calculate_volume_ma(volumes, period=42)  # 7 days * 6 (4H candles per day)
            
            # Volatility calculation
            volatility_pct = ((high_24h - low_24h) / current_price) * 100
            
            # Determine regime and signals
            regime = self._determine_regime(ohlc_data, current_price, ma_200)
            trend_strength = self._calculate_trend_strength(closes)
            
            # Distance from MAs
            distance_ma50 = ((current_price - ma_50) / ma_50) * 100 if ma_50 > 0 else 0
            distance_ma200 = ((current_price - ma_200) / ma_200) * 100 if ma_200 > 0 else 0
            
            data = {
                "symbol": symbol,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "price": round(current_price, 2),
                "ma_50": round(ma_50, 2),
                "ma_200": round(ma_200, 2),
                "rsi": round(rsi, 2),
                "change_24h": round(change_24h, 2),
                "volatility_pct": round(volatility_pct, 2),
                "volatility_level": self._classify_volatility(volatility_pct),
                "regime": regime,
                "trend_strength": trend_strength,
                "volume_24h": volume_24h,
                "volume_trend": "increasing" if volume_24h > volume_ma else "decreasing",
                "distance_ma50_pct": round(distance_ma50, 2),
                "distance_ma200_pct": round(distance_ma200, 2),
                "high_24h": high_24h,
                "low_24h": low_24h,
                "market_cap": market_cap,
                "key_level_status": self._check_key_levels(current_price, ma_50, ma_200)
            }
            
            # Cache result
            self.cache[cache_key] = (data, time.time())
            return data
            
        except Exception as e:
            print(f"Error fetching {symbol} data: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_multiple_coins_data(self, symbols: List[str]) -> Dict[str, Optional[Dict]]:
        """
        Get data for multiple coins efficiently
        Returns dict: {symbol: coin_data}
        """
        result = {}
        
        # Filter symbols that we support
        valid_symbols = [s for s in symbols if s in self.coin_ids]
        
        if not valid_symbols:
            return result
        
        # Check cache first
        uncached_symbols = []
        for symbol in valid_symbols:
            cache_key = f"{symbol}_data"
            if cache_key in self.cache:
                cached_data, timestamp = self.cache[cache_key]
                if time.time() - timestamp < self.cache_duration:
                    result[symbol] = cached_data
                else:
                    uncached_symbols.append(symbol)
            else:
                uncached_symbols.append(symbol)
        
        # Fetch uncached symbols
        for symbol in uncached_symbols:
            coin_data = self.get_coin_data(symbol)
            if coin_data:
                result[symbol] = coin_data
            
            # Small delay to respect rate limits
            if len(uncached_symbols) > 5:
                time.sleep(0.2)
        
        return result
    
    def get_market_cap_data(self) -> Optional[Dict]:
        """Get total crypto market cap and dominance data"""
        cache_key = "market_cap_data"
        
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration:
                return cached_data
        
        try:
            url = f"{self.base_url}/global"
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            data = response.json()['data']
            
            result = {
                "total_market_cap": data['total_market_cap']['usd'],
                "market_cap_change_24h": data['market_cap_change_percentage_24h_usd'],
                "btc_dominance": data['market_cap_percentage'].get('btc', 50),
                "eth_dominance": data['market_cap_percentage'].get('eth', 15),
                "total_volume_24h": data['total_volume']['usd']
            }
            
            self.cache[cache_key] = (result, time.time())
            return result
            
        except Exception as e:
            print(f"Error fetching market cap data: {e}")
            # Return fallback data
            return {
                "total_market_cap": 0,
                "market_cap_change_24h": 0,
                "btc_dominance": 50,
                "eth_dominance": 15,
                "total_volume_24h": 0
            }
    
    def get_supported_coins(self) -> List[str]:
        """Return list of all supported coin symbols"""
        return sorted(list(self.coin_ids.keys()))
    
    def is_coin_supported(self, symbol: str) -> bool:
        """Check if a coin symbol is supported"""
        return symbol.upper() in self.coin_ids
    
    def _fetch_coin_market_data(self, coin_id: str) -> Optional[Dict]:
        """Fetch current market data for a coin"""
        try:
            url = f"{self.base_url}/coins/{coin_id}"
            params = {
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "false",
                "developer_data": "false",
                "sparkline": "false"
            }
            
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            return data['market_data']
            
        except Exception as e:
            print(f"Error fetching market data for {coin_id}: {e}")
            return None
    
    def _fetch_ohlc_data(self, coin_id: str, days: int = 90) -> Optional[List]:
        """
        Fetch OHLC (candlestick) data
        Returns: List of [timestamp, open, high, low, close, volume]
        """
        try:
            url = f"{self.base_url}/coins/{coin_id}/ohlc"
            params = {
                "vs_currency": "usd",
                "days": days
            }
            
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            response.raise_for_status()
            ohlc_data = response.json()
            
            # Get volume data
            market_chart_url = f"{self.base_url}/coins/{coin_id}/market_chart"
            market_params = {
                "vs_currency": "usd",
                "days": days
            }
            
            market_response = requests.get(market_chart_url, params=market_params, headers=self.headers, timeout=15)
            market_response.raise_for_status()
            market_data = market_response.json()
            
            volumes = market_data.get('total_volumes', [])
            
            # Combine OHLC with volume
            combined_data = []
            for i, candle in enumerate(ohlc_data):
                volume = volumes[i][1] if i < len(volumes) else 0
                combined_data.append([
                    candle[0],  # timestamp
                    candle[1],  # open
                    candle[2],  # high
                    candle[3],  # low
                    candle[4],  # close
                    volume      # volume
                ])
            
            return combined_data
            
        except Exception as e:
            print(f"Error fetching OHLC data for {coin_id}: {e}")
            return None
    
    def _calculate_ma(self, prices: List[float], period: int) -> float:
        """Calculate simple moving average"""
        if len(prices) < period:
            return 0.0
        
        recent_prices = prices[-period:]
        return sum(recent_prices) / len(recent_prices)
    
    def _calculate_volume_ma(self, volumes: List[float], period: int) -> float:
        """Calculate volume moving average"""
        if len(volumes) < period:
            return 0.0
        
        recent_volumes = volumes[-period:]
        return sum(recent_volumes) / len(recent_volumes)
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calculate RSI indicator"""
        if len(prices) < period + 1:
            return 50.0
        
        # Get recent prices
        recent_prices = prices[-(period + 1):]
        
        gains = []
        losses = []
        
        for i in range(1, len(recent_prices)):
            change = recent_prices[i] - recent_prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _determine_regime(self, ohlc_data: List, current_price: float, ma_200: float) -> str:
        """Determine market regime: Bullish, Bearish, or Neutral"""
        if len(ohlc_data) < 5:
            return "Neutral"
        
        # Get recent highs (last 5 candles)
        recent_highs = [candle[2] for candle in ohlc_data[-5:]]  # candle[2] = high
        
        # Check for higher highs or lower highs
        higher_highs = all(recent_highs[i] >= recent_highs[i-1] for i in range(1, len(recent_highs)))
        lower_highs = all(recent_highs[i] <= recent_highs[i-1] for i in range(1, len(recent_highs)))
        
        # Distance from 200 MA
        if ma_200 == 0:
            return "Neutral"
        
        distance_from_ma = ((current_price - ma_200) / ma_200) * 100
        
        if current_price > ma_200 and higher_highs:
            return "Bullish"
        elif current_price < ma_200 and lower_highs:
            return "Bearish"
        elif abs(distance_from_ma) <= 2.5:
            return "Neutral"
        else:
            return "Neutral"
    
    def _calculate_trend_strength(self, prices: List[float]) -> str:
        """Calculate trend strength (simplified ADX logic)"""
        if len(prices) < 14:
            return "weak"
        
        # Check consistency of directional moves
        recent_prices = prices[-14:]
        positive_moves = sum(1 for i in range(1, len(recent_prices)) if recent_prices[i] > recent_prices[i-1])
        
        consistency = positive_moves / (len(recent_prices) - 1)
        
        if consistency > 0.7 or consistency < 0.3:
            return "strong"
        elif consistency > 0.6 or consistency < 0.4:
            return "medium"
        else:
            return "weak"
    
    def _classify_volatility(self, volatility_pct: float) -> str:
        """Classify volatility as Low, Medium, or High"""
        if volatility_pct < 3:
            return "Low"
        elif volatility_pct <= 6:
            return "Medium"
        else:
            return "High"
    
    def _check_key_levels(self, price: float, ma_50: float, ma_200: float) -> str:
        """Check if price is near key support/resistance"""
        if ma_50 == 0 or ma_200 == 0:
            return "unknown"
        
        distance_50 = abs((price - ma_50) / ma_50) * 100
        distance_200 = abs((price - ma_200) / ma_200) * 100
        
        if distance_50 < 1 or distance_200 < 1:
            return "at_key_level"
        elif price > ma_50 and price > ma_200:
            return "above_support"
        elif price < ma_50 and price < ma_200:
            return "below_resistance"
        else:
            return "between_levels"
