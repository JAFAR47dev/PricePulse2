from typing import Dict

class TodayAnalyzer:
    """Analyzes market data and builds actionable recommendations"""
    
    # Risk matrix: (regime, volatility) -> risk_level
    RISK_MATRIX = {
        ("Bearish", "High"): "High",
        ("Bearish", "Medium"): "High",
        ("Bearish", "Low"): "Medium",
        ("Neutral", "High"): "Medium",
        ("Neutral", "Medium"): "Medium",
        ("Neutral", "Low"): "Low",
        ("Bullish", "High"): "Medium",
        ("Bullish", "Medium"): "Low",
        ("Bullish", "Low"): "Low",
    }
    
    # Action recommendations based on risk level
    ACTIONS = {
        "High": {
            "emoji": "🔴",
            "title": "HIGH RISK",
            "actions": [
                "Stay in stablecoins",
                "Avoid swing trades",
                "Wait for better conditions"
            ]
        },
        "Medium": {
            "emoji": "🔶",
            "title": "MEDIUM RISK",
            "actions": [
                "Reduce position size",
                "Range/scalp trading only",
                "Stay nimble and quick"
            ]
        },
        "Low": {
            "emoji": "🟢",
            "title": "LOW RISK",
            "actions": [
                "Normal trading allowed",
                "Good conditions for holding",
                "Consider adding to positions"
            ]
        }
    }
    
    def analyze(self, market_data: Dict, sentiment_data: Dict) -> Dict:
        """
        Main analysis function
        Returns complete analysis with risk level and recommendations
        """
        regime = market_data['regime']
        volatility = market_data['volatility_level']
        
        # Determine risk level from matrix
        risk_level = self.RISK_MATRIX.get((regime, volatility), "Medium")
        
        # Get action recommendation
        action_data = self.ACTIONS[risk_level]
        
        return {
            "regime": regime,
            "volatility": volatility,
            "risk_level": risk_level,
            "risk_emoji": action_data["emoji"],
            "risk_title": action_data["title"],
            "recommended_actions": action_data["actions"],
            "market_data": market_data,
            "sentiment": sentiment_data
        }
    
    def format_message(self, analysis: Dict) -> str:
        """
        Format the /today message for Telegram
        """
        md = analysis['market_data']
        sentiment = analysis['sentiment']
        
        # Build message
        msg = f"📊 **Market Snapshot** (BTC 4H)\n\n"
        
        # Current price and change
        price_emoji = "📈" if md['change_24h'] > 0 else "📉"
        msg += f"{price_emoji} **${md['price']:,.0f}** "
        msg += f"({md['change_24h']:+.2f}% 24h)\n\n"
        
        # Indicators
        msg += f"📍 **50 MA:** ${md['ma_50']:,.0f}\n"
        msg += f"📍 **200 MA:** ${md['ma_200']:,.0f}\n"
        msg += f"⚡ **Volatility:** {md['volatility_level']} ({md['volatility_pct']}%)\n"
        msg += f"🧠 **Fear & Greed:** {sentiment['value']} ({sentiment['classification']})\n\n"
        
        # Regime
        regime_emoji = {"Bullish": "🟢", "Bearish": "🔴", "Neutral": "🔶"}[analysis['regime']]
        msg += f"{regime_emoji} **Regime:** {analysis['regime']}\n\n"
        
        # Risk Assessment (BIG)
        msg += f"━━━━━━━━━━━━━━━━\n"
        msg += f"{analysis['risk_emoji']} **{analysis['risk_title']}**\n"
        msg += f"━━━━━━━━━━━━━━━━\n\n"
        
        # Recommended Actions
        msg += f"✅ **Best Action Today:**\n"
        for action in analysis['recommended_actions']:
            msg += f"  • {action}\n"
        
        # Timestamp
        msg += f"\n🕒 Last updated: {md['timestamp'][:16]} UTC"
        
        return msg