from typing import Dict
from datetime import datetime
from typing import Dict, Optional, List

class TodayAnalyzer:
    """Comprehensive market analyzer with pro-level recommendations"""
    
    def analyze_market(self, btc_data: Dict, eth_data: Dict, sentiment_data: Dict, 
                      sector_data: Dict, macro_data: Dict) -> Dict:
        """
        Master analysis function - combines all data sources
        Returns complete market assessment
        """
        # Calculate overall market verdict
        market_verdict = self._determine_market_verdict(
            btc_data, eth_data, sentiment_data, sector_data, macro_data
        )
        
        # Identify best opportunities
        opportunities = self._identify_opportunities(sector_data, btc_data, eth_data)
        
        # Determine strategy recommendation
        strategy = self._get_strategy_recommendation(market_verdict, sentiment_data)
        
        return {
            "verdict": market_verdict,
            "btc": btc_data,
            "eth": eth_data,
            "sentiment": sentiment_data,
            "sectors": sector_data,
            "macro": macro_data,
            "opportunities": opportunities,
            "strategy": strategy,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def _determine_market_verdict(self, btc: Dict, eth: Dict, sentiment: Dict, 
                                  sectors: Dict, macro: Dict) -> Dict:
        """
        Determine overall market condition: FAVORABLE / NEUTRAL / UNFAVORABLE
        """
        score = 0
        reasons = []
        
        # BTC Analysis (40% weight)
        if btc['regime'] == "Bullish" and btc['trend_strength'] in ["strong", "medium"]:
            score += 4
            reasons.append("BTC showing bullish strength")
        elif btc['regime'] == "Bearish":
            score -= 3
            reasons.append("BTC in bearish regime")
        
        # Volume confirmation
        if btc['volume_trend'] == "increasing":
            score += 1
            reasons.append("Rising volume confirms moves")
        
        # RSI check
        if 30 < btc['rsi'] < 70:
            score += 1
        elif btc['rsi'] > 75:
            score -= 1
            reasons.append("BTC overbought (RSI > 75)")
        elif btc['rsi'] < 25:
            score -= 1
            reasons.append("BTC oversold - risky zone")
        
        # ETH Analysis (30% weight)
        if eth['regime'] == "Bullish":
            score += 2
            reasons.append("ETH aligned bullish")
        elif eth['regime'] == "Bearish":
            score -= 2
        
        # Sentiment (10% weight)
        sent_value = sentiment['value']
        if 40 < sent_value < 70:
            score += 1
        elif sent_value > 75:
            score -= 1
            reasons.append("Extreme greed - caution advised")
        elif sent_value < 25:
            reasons.append("Extreme fear - potential opportunity")
        
        # Sector momentum (20% weight)
        strong_sectors = sum(1 for s in sectors.values() if s.get('momentum') in ['strong', 'moderate'])
        if strong_sectors >= 3:
            score += 2
            reasons.append(f"{strong_sectors} sectors showing strength")
        elif strong_sectors <= 1:
            score -= 1
            reasons.append("Most sectors weak")
        
        # Macro factors
        if macro['btc_dominance'] > 55:
            reasons.append("High BTC dominance - altcoins may lag")
        
        # Final verdict
        if score >= 5:
            status = "FAVORABLE"
            risk_level = "Low"
            emoji = "🟢"
            action = "TRADE TODAY"
        elif score >= 2:
            status = "NEUTRAL"
            risk_level = "Medium"
            emoji = "🔶"
            action = "SELECTIVE TRADING"
        else:
            status = "UNFAVORABLE"
            risk_level = "High"
            emoji = "🔴"
            action = "STAY CAUTIOUS"
        
        return {
            "status": status,
            "risk_level": risk_level,
            "emoji": emoji,
            "action": action,
            "score": score,
            "reasons": reasons
        }
    
    def _identify_opportunities(self, sectors: Dict, btc: Dict, eth: Dict) -> List[Dict]:
        """Identify top 3 trading opportunities today"""
        opportunities = []
        avoid_list = []
        
        # Check BTC
        if btc['regime'] == "Bullish" and btc['rsi'] < 70 and btc['volume_trend'] == "increasing":
            opportunities.append({
                "asset": "BTC",
                "reason": f"{btc['regime']}, RSI {btc['rsi']:.0f}, volume ↑"
            })
        elif btc['rsi'] > 75 or btc['volume_trend'] == "decreasing":
            avoid_list.append({
                "asset": "BTC",
                "reason": "Overbought" if btc['rsi'] > 75 else "Low volume"
            })
        
        # Check ETH
        if eth['regime'] == "Bullish" and eth['key_level_status'] == "above_support":
            opportunities.append({
                "asset": "ETH",
                "reason": f"{eth['regime']}, holding support well"
            })
        elif eth['regime'] == "Bearish":
            avoid_list.append({
                "asset": "ETH",
                "reason": "Bearish momentum"
            })
        
        # Check sectors
        for sector_name, data in sectors.items():
            if data.get('momentum') == 'strong' and data.get('avg_change', 0) > 2:
                display_name = sector_name.replace('_', ' ').title()
                opportunities.append({
                    "asset": f"{display_name}",
                    "reason": f"Strong momentum (+{data['avg_change']:.1f}%)"
                })
            elif data.get('momentum') == 'very_weak':
                display_name = sector_name.replace('_', ' ').title()
                avoid_list.append({
                    "asset": display_name,
                    "reason": f"Weak performance ({data['avg_change']:.1f}%)"
                })
        
        return {
            "top_picks": opportunities[:3],
            "avoid": avoid_list[:2]
        }
    
    def _get_strategy_recommendation(self, verdict: Dict, sentiment: Dict) -> Dict:
        """Generate actionable strategy based on market conditions"""
        risk_level = verdict['risk_level']
        
        if risk_level == "Low":
            return {
                "position_sizing": "Normal sizing OK",
                "trade_style": "Swing trades and holds work well",
                "risk_management": "Set stops at recent support levels",
                "leverage": "Moderate leverage acceptable (2-3x max)",
                "focus": "Quality Layer 1s and established projects"
            }
        elif risk_level == "Medium":
            return {
                "position_sizing": "Reduce size by 30-50%",
                "trade_style": "Scalping and quick trades preferred",
                "risk_management": "Tight stops, take profits quickly",
                "leverage": "Low leverage only (1-2x)",
                "focus": "BTC, ETH, high-liquidity assets only"
            }
        else:  # High risk
            return {
                "position_sizing": "Cash or minimal exposure",
                "trade_style": "Stay in stablecoins",
                "risk_management": "Wait for better conditions",
                "leverage": "No leverage",
                "focus": "Preservation mode - don't force trades"
            }
    
    def format_full_analysis(self, analysis: Dict) -> str:
        """Format complete market analysis message"""
        verdict = analysis['verdict']
        btc = analysis['btc']
        eth = analysis['eth']
        sentiment = analysis['sentiment']
        sectors = analysis['sectors']
        macro = analysis['macro']
        opps = analysis['opportunities']
        strategy = analysis['strategy']
        
        # Build message
        msg = f"📊 **CRYPTO MARKET** — {datetime.utcnow().strftime('%A, %b %d')}\n\n"
        
        # Overall Verdict
        msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"{verdict['emoji']} **{verdict['status']} CONDITIONS**\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += f"✅ **{verdict['action']}** — {verdict['reasons'][0] if verdict['reasons'] else 'Market showing mixed signals'}\n\n"
        
        # Market Pulse
        msg += "📈 **Market Pulse:**\n"
        msg += f"• **BTC:** ${btc['price']:,.0f} ({btc['change_24h']:+.1f}%) — {btc['regime']}"
        if btc['trend_strength'] == 'strong':
            msg += " 💪\n"
        else:
            msg += "\n"
        msg += f"• **ETH:** ${eth['price']:,.0f} ({eth['change_24h']:+.1f}%) — {eth['regime']}\n"
        
        # Get market cap data if available
        msg += f"• **BTC Dominance:** {macro['btc_dominance']:.1f}%"
        if macro['btc_dominance'] > 55:
            msg += " ⚠️ Alts may lag\n"
        else:
            msg += "\n"
        msg += "\n"
        
        # Risk Factors
        msg += "⚡ **Risk Factors:**\n"
        msg += f"• Volatility: {btc['volatility_level']} ({btc['volatility_pct']:.1f}%)\n"
        msg += f"• Volume: {btc['volume_trend'].title()}"
        msg += " ✓\n" if btc['volume_trend'] == 'increasing' else " ⚠️\n"
        msg += f"• Sentiment: {sentiment['classification']} ({sentiment['value']}) {sentiment['emoji']}\n"
        msg += f"  ↳ {sentiment['context']}\n"
        msg += f"• RSI: BTC {btc['rsi']:.0f}"
        if btc['rsi'] > 70:
            msg += " (Overbought ⚠️)"
        elif btc['rsi'] < 30:
            msg += " (Oversold 👀)"
        msg += "\n\n"
        
        # Sector Performance
        msg += "🎯 **Sector Performance:**\n"        
# Sector Performance (continued)
        for sector_name, data in sectors.items():
            display_name = sector_name.replace('_', ' ').title()
            msg += f"• {display_name}: {data['emoji']} "
            msg += f"({data['avg_change']:+.1f}% avg)\n"
        msg += "\n"
        
        # Top Opportunities
        if opps['top_picks']:
            msg += "🎯 **Best Opportunities Today:**\n"
            for i, opp in enumerate(opps['top_picks'], 1):
                msg += f"{i}. **{opp['asset']}** — {opp['reason']}\n"
            msg += "\n"
        
        # What to Avoid
        if opps['avoid']:
            msg += "⚠️ **Avoid Today:**\n"
            for item in opps['avoid']:
                msg += f"• {item['asset']} — {item['reason']}\n"
            msg += "\n"
        
        # Strategy Recommendation
        msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "💡 **STRATEGY RECOMMENDATION**\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += f"✓ {strategy['position_sizing']}\n"
        msg += f"✓ {strategy['trade_style']}\n"
        msg += f"✓ {strategy['risk_management']}\n"
        msg += f"✓ Leverage: {strategy['leverage']}\n"
        msg += f"✓ Focus: {strategy['focus']}\n\n"
        
        # Additional Context
        if len(verdict['reasons']) > 1:
            msg += "📝 **Key Factors:**\n"
            for reason in verdict['reasons'][:3]:
                msg += f"• {reason}\n"
            msg += "\n"
        
        # Footer
        msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"🕒 Updated: {datetime.utcnow().strftime('%H:%M')} UTC | Valid for next 4 hours\n"
        msg += "💬 Use `/today risk` for quick view\n"
        
        return msg
    
    def format_btc_deep_dive(self, analysis: Dict) -> str:
        """Format BTC-focused deep dive"""
        btc = analysis['btc']
        sentiment = analysis['sentiment']
        
        msg = f"₿ **BITCOIN DEEP DIVE**\n\n"
        
        # Price Action
        msg += f"**Current Price:** ${btc['price']:,.0f}\n"
        msg += f"**24h Change:** {btc['change_24h']:+.2f}%\n"
        msg += f"**24h Range:** ${btc['low_24h']:,.0f} - ${btc['high_24h']:,.0f}\n\n"
        
        # Technical Indicators
        msg += "**Technical Analysis:**\n"
        msg += f"• 50 MA: ${btc['ma_50']:,.0f} ({btc['distance_ma50_pct']:+.1f}%)\n"
        msg += f"• 200 MA: ${btc['ma_200']:,.0f} ({btc['distance_ma200_pct']:+.1f}%)\n"
        msg += f"• RSI(14): {btc['rsi']:.1f}"
        if btc['rsi'] > 70:
            msg += " — Overbought ⚠️\n"
        elif btc['rsi'] < 30:
            msg += " — Oversold 👀\n"
        else:
            msg += " — Neutral\n"
        msg += f"• Regime: {btc['regime']}\n"
        msg += f"• Trend Strength: {btc['trend_strength'].title()}\n\n"
        
        # Volume & Volatility
        msg += "**Market Dynamics:**\n"
        msg += f"• Volume: {btc['volume_trend'].title()}\n"
        msg += f"• Volatility: {btc['volatility_level']} ({btc['volatility_pct']:.1f}%)\n"
        msg += f"• Key Levels: {btc['key_level_status'].replace('_', ' ').title()}\n\n"
        
        # Trading Recommendation
        msg += "**Trading Assessment:**\n"
        if btc['regime'] == "Bullish" and btc['rsi'] < 70:
            msg += "✅ Conditions favorable for long positions\n"
            msg += f"• Entry zone: Around ${btc['ma_50']:,.0f} support\n"
            msg += f"• Stop loss: Below ${btc['ma_50'] * 0.97:,.0f}\n"
        elif btc['regime'] == "Bearish":
            msg += "⚠️ Bearish conditions - avoid longs\n"
            msg += "• Consider waiting for trend reversal\n"
        else:
            msg += "🔶 Neutral - wait for clearer direction\n"
            msg += "• Range-bound trading only\n"
        
        msg += f"\n🕒 Updated: {datetime.utcnow().strftime('%H:%M')} UTC"
        
        return msg
    
    def format_sectors_only(self, analysis: Dict) -> str:
        """Format sector breakdown view"""
        sectors = analysis['sectors']
        opps = analysis['opportunities']
        
        msg = f"🎯 **SECTOR ANALYSIS**\n\n"
        
        # Sector Performance
        msg += "**Current Performance:**\n\n"
        
        for sector_name, data in sectors.items():
            display_name = sector_name.replace('_', ' ').title()
            msg += f"{data['emoji']} **{display_name}**\n"
            msg += f"   • Avg Change: {data['avg_change']:+.2f}%\n"
            msg += f"   • Momentum: {data['momentum'].replace('_', ' ').title()}\n"
            msg += f"   • Status: "
            
            if data['momentum'] in ['strong', 'moderate']:
                msg += "Good for trading ✓\n"
            elif data['momentum'] == 'neutral':
                msg += "Mixed signals\n"
            else:
                msg += "Avoid for now\n"
            msg += "\n"
        
        # Best Opportunities
        if opps['top_picks']:
            msg += "**🎯 Top Picks:**\n"
            for opp in opps['top_picks']:
                msg += f"• {opp['asset']}\n"
            msg += "\n"
        
        # What to Avoid
        if opps['avoid']:
            msg += "**⚠️ Avoid:**\n"
            for item in opps['avoid']:
                msg += f"• {item['asset']} — {item['reason']}\n"
        
        msg += f"\n🕒 Updated: {datetime.utcnow().strftime('%H:%M')} UTC"
        
        return msg
    
    def format_risk_only(self, analysis: Dict) -> str:
        """Format quick risk assessment"""
        verdict = analysis['verdict']
        btc = analysis['btc']
        sentiment = analysis['sentiment']
        strategy = analysis['strategy']
        
        msg = f"⚡ **QUICK RISK CHECK**\n\n"
        
        # Overall Status
        msg += f"{verdict['emoji']} **{verdict['status']}**\n"
        msg += f"Risk Level: **{verdict['risk_level']}**\n\n"
        
        # Quick Stats
        msg += f"BTC: ${btc['price']:,.0f} ({btc['change_24h']:+.1f}%) — {btc['regime']}\n"
        msg += f"RSI: {btc['rsi']:.0f} | Vol: {btc['volatility_level']} | "
        msg += f"Sentiment: {sentiment['value']}\n\n"
        
        # Action
        msg += f"**Action:** {verdict['action']}\n\n"
        
        # Strategy
        msg += "**Today's Strategy:**\n"
        msg += f"• {strategy['position_sizing']}\n"
        msg += f"• {strategy['trade_style']}\n"
        msg += f"• {strategy['leverage']}\n\n"
        
        # Key Warning
        if verdict['risk_level'] == "High":
            msg += "⚠️ **High risk conditions** — preservation mode\n"
        elif btc['rsi'] > 75:
            msg += "⚠️ **BTC overbought** — be cautious\n"
        elif sentiment['value'] > 75:
            msg += "⚠️ **Extreme greed** — potential top forming\n"
        
        msg += f"\n🕒 {datetime.utcnow().strftime('%H:%M')} UTC"
        msg += "\nUse `/today` for full analysis"
        
        return msg