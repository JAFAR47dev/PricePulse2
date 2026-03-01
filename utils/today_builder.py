from typing import Dict, Optional, List
from datetime import datetime

class TodayAnalyzer:
    """
    Comprehensive market analyzer with pro-level recommendations
    Enhanced with advanced scoring and macro integration
    NOW USES HTML MARKUP FOR TELEGRAM
    """
    
    # Scoring weights for different factors
    WEIGHTS = {
        "btc_technical": 25,
        "eth_technical": 15,
        "sentiment": 10,
        "sectors": 20,
        "macro": 15,
        "volume": 10,
        "momentum": 5
    }
    
    def analyze_market(self, btc_data: Dict, eth_data: Dict, sentiment_data: Dict, 
                      sector_data: Dict, macro_data: Dict) -> Dict:
        """
        Master analysis function - combines all data sources with weighted scoring
        Returns complete market assessment
        """
        # Calculate overall market verdict with enhanced scoring
        market_verdict = self._determine_market_verdict(
            btc_data, eth_data, sentiment_data, sector_data, macro_data
        )
        
        # Identify best opportunities with sector details
        opportunities = self._identify_opportunities(sector_data, btc_data, eth_data, macro_data)
        
        # Determine strategy recommendation
        strategy = self._get_strategy_recommendation(market_verdict, sentiment_data, macro_data)
        
        # Generate market warnings
        warnings = self._generate_warnings(btc_data, eth_data, sentiment_data, macro_data)
        
        return {
            "verdict": market_verdict,
            "btc": btc_data,
            "eth": eth_data,
            "sentiment": sentiment_data,
            "sectors": sector_data,
            "macro": macro_data,
            "opportunities": opportunities,
            "strategy": strategy,
            "warnings": warnings,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def _determine_market_verdict(self, btc: Dict, eth: Dict, sentiment: Dict, 
                                  sectors: Dict, macro: Dict) -> Dict:
        """
        Enhanced market verdict with weighted scoring system
        Total possible score: 100 points
        """
        score = 0
        max_score = 100
        reasons = []
        warnings = []
        
        # === BTC TECHNICAL ANALYSIS (25 points) ===
        btc_score = 0
        
        # Regime (12 points)
        if btc['regime'] == "Bullish":
            if btc['trend_strength'] == "strong":
                btc_score += 12
                reasons.append("BTC showing strong bullish momentum")
            elif btc['trend_strength'] == "medium":
                btc_score += 8
                reasons.append("BTC in moderate bullish trend")
            else:
                btc_score += 5
        elif btc['regime'] == "Bearish":
            if btc['trend_strength'] == "strong":
                btc_score -= 8
                warnings.append("BTC in strong bearish trend")
            else:
                btc_score -= 4
                warnings.append("BTC showing bearish bias")
        else:  # Neutral
            btc_score += 3
        
        # RSI (8 points)
        if 40 <= btc['rsi'] <= 60:
            btc_score += 8  # Ideal range
        elif 30 < btc['rsi'] < 40 or 60 < btc['rsi'] < 70:
            btc_score += 5  # Acceptable
        elif 25 < btc['rsi'] <= 30:
            btc_score += 3
            warnings.append("BTC approaching oversold (potential bounce)")
        elif btc['rsi'] <= 25:
            btc_score -= 3
            warnings.append("BTC severely oversold - high risk")
        elif 70 <= btc['rsi'] < 75:
            btc_score += 2
            warnings.append("BTC overbought - caution advised")
        else:  # RSI >= 75
            btc_score -= 4
            warnings.append("BTC extremely overbought - correction likely")
        
        # Volume (5 points)
        if btc['volume_trend'] == "increasing":
            btc_score += 5
            reasons.append("Strong volume confirms price action")
        elif btc['volume_trend'] == "decreasing":
            btc_score -= 2
            warnings.append("Declining volume - weak conviction")
        
        score += btc_score
        
        # === ETH TECHNICAL ANALYSIS (15 points) ===
        eth_score = 0
        
        # Regime alignment (10 points)
        if eth['regime'] == btc['regime']:
            if eth['regime'] == "Bullish":
                eth_score += 10
                reasons.append("BTC and ETH aligned bullish")
            elif eth['regime'] == "Bearish":
                eth_score -= 6
            else:
                eth_score += 5
        else:
            eth_score += 2
            warnings.append("BTC and ETH showing divergence")
        
        # ETH RSI (5 points)
        if 40 <= eth['rsi'] <= 65:
            eth_score += 5
        elif eth['rsi'] > 75:
            eth_score -= 2
        elif eth['rsi'] < 30:
            eth_score += 2  # Oversold = potential opportunity
        
        score += eth_score
        
        # === SENTIMENT ANALYSIS (10 points) ===
        sentiment_score = 0
        sent_value = sentiment['value']
        
        if 45 <= sent_value <= 65:
            sentiment_score += 10  # Healthy range
        elif 35 <= sent_value < 45 or 65 < sent_value <= 75:
            sentiment_score += 6
        elif 25 <= sent_value < 35:
            sentiment_score += 4
            reasons.append("Fear levels creating opportunity")
        elif sent_value < 25:
            sentiment_score += 2
            warnings.append("Extreme fear - potential capitulation")
        elif 75 < sent_value <= 85:
            sentiment_score += 3
            warnings.append("High greed - watch for reversal")
        else:  # > 85
            sentiment_score -= 5
            warnings.append("Extreme greed - major correction risk")
        
        score += sentiment_score
        
        # === SECTOR ANALYSIS (20 points) ===
        sector_score = 0
        
        # Count sector momentum with quality filter
        sectors_with_data = [s for s in sectors.values() if s.get('data_quality') in ['high', 'medium']]
        
        if sectors_with_data:
            very_strong = sum(1 for s in sectors_with_data if s.get('momentum') == 'very_strong')
            strong = sum(1 for s in sectors_with_data if s.get('momentum') in ['strong', 'moderate'])
            weak = sum(1 for s in sectors_with_data if s.get('momentum') in ['weak', 'poor', 'very_poor'])
            
            # Strong sectors
            if very_strong >= 2:
                sector_score += 20
                reasons.append(f"{very_strong} sectors showing exceptional strength")
            elif strong >= 4:
                sector_score += 15
                reasons.append(f"{strong} sectors showing positive momentum")
            elif strong >= 2:
                sector_score += 10
            elif strong == 1:
                sector_score += 5
            
            # Weak sectors penalty
            if weak >= 4:
                sector_score -= 5
                warnings.append("Broad sector weakness detected")
        
        score += sector_score
        
        # === MACRO ANALYSIS (15 points) ===
        macro_score = 0
        
        # BTC Dominance (5 points)
        btc_dom = macro.get('btc_dominance', 50)
        if 48 <= btc_dom <= 55:
            macro_score += 5  # Healthy range
        elif btc_dom > 60:
            macro_score += 3
            warnings.append("High BTC dominance - alts may lag")
        elif btc_dom < 40:
            macro_score += 3
            reasons.append("Alt season conditions present")
        
        # Market Structure (5 points)
        market_structure = macro.get('market_structure', 'unknown')
        if market_structure in ['balanced', 'alt_season']:
            macro_score += 5
        elif market_structure == 'btc_leading':
            macro_score += 3
        elif market_structure == 'risk_off':
            macro_score -= 5
            warnings.append("Risk-off environment - capital fleeing to stables")
        elif market_structure == 'risk_on':
            macro_score += 4
            reasons.append("Risk-on environment - capital deployment")
        
        # Exchange Flow (5 points)
        exchange_flow = macro.get('exchange_flow', 'neutral')
        flow_signal = macro.get('exchange_flow_signal', 'neutral')
        
        if flow_signal == 'bullish':
            macro_score += 5
            reasons.append("Coins flowing off exchanges (accumulation)")
        elif flow_signal == 'slightly_bullish':
            macro_score += 3
        elif flow_signal == 'slightly_bearish':
            macro_score -= 2
        elif flow_signal == 'bearish':
            macro_score -= 5
            warnings.append("Heavy inflow to exchanges (distribution)")
        
        score += macro_score
        
        # === MARKET SENTIMENT (from macro) (5 points) ===
        market_sentiment = macro.get('market_sentiment', {})
        sentiment_status = market_sentiment.get('sentiment', 'neutral')
        
        if sentiment_status in ['bullish', 'very_bullish']:
            score += 5
            reasons.append(f"{market_sentiment.get('positive_pct', 0):.0f}% of top coins positive")
        elif sentiment_status == 'bearish':
            score -= 3
        elif sentiment_status == 'very_bearish':
            score -= 5
            warnings.append("Broad market weakness - most coins negative")
        
        # === ALTCOIN SEASON BONUS (5 points) ===
        if 'altcoin_season' in macro:
            alt_season = macro['altcoin_season']
            alt_index = alt_season.get('index', 50)
            
            if alt_index >= 70:
                score += 5
                reasons.append(f"Strong alt season ({alt_season.get('season', '')})")
            elif alt_index >= 55:
                score += 3
            elif alt_index <= 30:
                score -= 2
        
        # === NORMALIZE SCORE (0-100) ===
        normalized_score = max(0, min(100, score))
        
        # === DETERMINE FINAL VERDICT ===
        if normalized_score >= 70:
            status = "HIGHLY FAVORABLE"
            risk_level = "Very Low"
            emoji = "🟢🟢"
            action = "STRONG BUY CONDITIONS"
        elif normalized_score >= 55:
            status = "FAVORABLE"
            risk_level = "Low"
            emoji = "🟢"
            action = "GOOD TO TRADE"
        elif normalized_score >= 45:
            status = "NEUTRAL"
            risk_level = "Medium"
            emoji = "🔶"
            action = "SELECTIVE TRADING"
        elif normalized_score >= 30:
            status = "UNFAVORABLE"
            risk_level = "High"
            emoji = "🔴"
            action = "STAY CAUTIOUS"
        else:
            status = "HIGHLY UNFAVORABLE"
            risk_level = "Very High"
            emoji = "🔴🔴"
            action = "AVOID TRADING"
        
        return {
            "status": status,
            "risk_level": risk_level,
            "emoji": emoji,
            "action": action,
            "score": normalized_score,
            "raw_score": score,
            "reasons": reasons[:5],  # Top 5 reasons
            "warnings": warnings[:3],  # Top 3 warnings
            "breakdown": {
                "btc_technical": btc_score,
                "eth_technical": eth_score,
                "sentiment": sentiment_score,
                "sectors": sector_score,
                "macro": macro_score
            }
        }
    
    def _identify_opportunities(self, sectors: Dict, btc: Dict, eth: Dict, macro: Dict) -> Dict:
        """
        Enhanced opportunity identification with quality scoring
        """
        opportunities = []
        avoid_list = []
        
        # === BTC OPPORTUNITY ===
        btc_quality_score = 0
        
        if btc['regime'] == "Bullish":
            btc_quality_score += 3
        if btc['rsi'] < 65:
            btc_quality_score += 2
        if btc['volume_trend'] == "increasing":
            btc_quality_score += 2
        if btc['key_level_status'] == "above_support":
            btc_quality_score += 1
        
        if btc_quality_score >= 5:
            opportunities.append({
                "asset": "BTC",
                "reason": f"{btc['regime']}, RSI {btc['rsi']:.0f}, strong setup",
                "quality_score": btc_quality_score,
                "timeframe": "swing"
            })
        elif btc['rsi'] > 75:
            avoid_list.append({
                "asset": "BTC",
                "reason": f"Overbought (RSI {btc['rsi']:.0f})",
                "severity": "high"
            })
        
        # === ETH OPPORTUNITY ===
        eth_quality_score = 0
        
        if eth['regime'] == "Bullish":
            eth_quality_score += 3
        if eth['rsi'] < 65:
            eth_quality_score += 2
        if eth['key_level_status'] in ["above_support", "at_key_level"]:
            eth_quality_score += 2
        if eth['volume_trend'] == "increasing":
            eth_quality_score += 1
        
        if eth_quality_score >= 5:
            opportunities.append({
                "asset": "ETH",
                "reason": f"{eth['regime']}, holding key levels well",
                "quality_score": eth_quality_score,
                "timeframe": "swing"
            })
        elif eth['regime'] == "Bearish" and eth['trend_strength'] == "strong":
            avoid_list.append({
                "asset": "ETH",
                "reason": "Strong bearish momentum",
                "severity": "medium"
            })
        
        # === SECTOR OPPORTUNITIES ===
        sector_opportunities = []
        
        for sector_name, data in sectors.items():
            if data.get('data_quality') not in ['high', 'medium']:
                continue
            
            quality_score = 0
            momentum = data.get('momentum', 'unknown')
            avg_change = data.get('avg_change', 0)
            
            # Score the sector
            if momentum in ['very_strong', 'strong']:
                quality_score += 3
            elif momentum == 'moderate':
                quality_score += 2
            
            if avg_change > 5:
                quality_score += 3
            elif avg_change > 2:
                quality_score += 2
            elif avg_change > 0:
                quality_score += 1
            
            # Check for top performers
            if 'individual_performances' in data:
                best = data['individual_performances'].get('best', [])
                if best and len(best) > 0:
                    top_performer = best[0]
                    quality_score += 1
            
            if quality_score >= 4:
                display_name = sector_name.replace('_', ' ').title()
                reason = f"Strong momentum (+{avg_change:.1f}%)"
                
                # Add top performer if available
                if 'individual_performances' in data:
                    best = data['individual_performances'].get('best', [])
                    if best:
                        top_coin = best[0]
                        reason += f", {top_coin['symbol']} leading"
                
                sector_opportunities.append({
                    "asset": display_name,
                    "sector": sector_name,
                    "reason": reason,
                    "quality_score": quality_score,
                    "timeframe": "short-medium"
                })
            elif momentum in ['poor', 'very_poor'] or avg_change < -3:
                display_name = sector_name.replace('_', ' ').title()
                avoid_list.append({
                    "asset": display_name,
                    "reason": f"Weak performance ({avg_change:.1f}%)",
                    "severity": "medium" if avg_change > -5 else "high"
                })
        
        # Sort opportunities by quality score
        sector_opportunities.sort(key=lambda x: x['quality_score'], reverse=True)
        opportunities.extend(sector_opportunities[:3])  # Top 3 sectors
        
        # === ALTCOIN SEASON OPPORTUNITY ===
        if 'altcoin_season' in macro:
            alt_season = macro['altcoin_season']
            if alt_season.get('index', 0) >= 70:
                opportunities.append({
                    "asset": "Altcoins (General)",
                    "reason": f"{alt_season.get('season', '')} - broad alt strength",
                    "quality_score": 7,
                    "timeframe": "medium"
                })
        
        # Sort all opportunities by quality score
        opportunities.sort(key=lambda x: x.get('quality_score', 0), reverse=True)
        
        # Sort avoid list by severity
        avoid_list.sort(key=lambda x: 0 if x.get('severity') == 'high' else 1)
        
        return {
            "top_picks": opportunities[:5],  # Top 5 best opportunities
            "avoid": avoid_list[:3],  # Top 3 to avoid
            "total_opportunities": len(opportunities),
            "total_avoid": len(avoid_list)
        }
    
    def _get_strategy_recommendation(self, verdict: Dict, sentiment: Dict, macro: Dict) -> Dict:
        """
        Enhanced strategy with macro integration
        """
        risk_level = verdict['risk_level']
        score = verdict['score']
        market_structure = macro.get('market_structure', 'unknown')
        
        # Base strategy on score
        if score >= 70:
            return {
                "position_sizing": "Normal to slightly aggressive (2.5-3% risk per trade)",
                "trade_style": "Swing trades, momentum plays, accumulation",
                "risk_management": "Trail stops aggressively, let winners run",
                "leverage": "Moderate leverage acceptable (3-5x max)",
                "focus": "BTC, ETH, strong sector leaders",
                "timeframe": "Multi-day to weeks",
                "confidence": "high"
            }
        elif score >= 55:
            return {
                "position_sizing": "Normal sizing (2% risk per trade)",
                "trade_style": "Swing trades and strategic entries",
                "risk_management": "Set stops at recent support, take partials at resistance",
                "leverage": "Low to moderate leverage (2-3x max)",
                "focus": "Quality Layer 1s, established DeFi",
                "timeframe": "Days to week",
                "confidence": "medium-high"
            }
        elif score >= 45:
            return {
                "position_sizing": "Reduced size (1-1.5% risk)",
                "trade_style": "Scalping, quick trades, range-bound",
                "risk_management": "Tight stops, quick profit-taking",
                "leverage": "Minimal leverage (1-2x)",
                "focus": "BTC, ETH only - highest liquidity",
                "timeframe": "Hours to 1-2 days",
                "confidence": "medium"
            }
        elif score >= 30:
            return {
                "position_sizing": "Very small (less than 1% risk) or cash",
                "trade_style": "Counter-trend scalps only (advanced traders)",
                "risk_management": "Extremely tight stops, don't hold overnight",
                "leverage": "No leverage",
                "focus": "BTC only, or stay in stablecoins",
                "timeframe": "Minutes to hours",
                "confidence": "low"
            }
        else:  # score < 30
            return {
                "position_sizing": "100% cash/stablecoins",
                "trade_style": "Do not trade - preservation mode",
                "risk_management": "Wait for market structure improvement",
                "leverage": "Absolutely no leverage",
                "focus": "Capital preservation - no active trades",
                "timeframe": "Wait for score &gt; 40",
                "confidence": "very_low"
            }
    
    def _generate_warnings(self, btc: Dict, eth: Dict, sentiment: Dict, macro: Dict) -> List[str]:
        """
        Generate critical warnings based on market conditions
        """
        warnings = []
        
        # RSI extremes
        if btc['rsi'] > 80:
            warnings.append("⚠️ BTC RSI extremely overbought - correction imminent")
        elif btc['rsi'] < 20:
            warnings.append("⚠️ BTC RSI extremely oversold - capitulation possible")
        
        # Sentiment extremes
        if sentiment['value'] > 85:
            warnings.append("⚠️ Extreme greed detected - historic top formation zone")
        elif sentiment['value'] < 15:
            warnings.append("⚠️ Extreme fear - potential capitulation bottom")
        
        # Macro warnings
        if macro.get('total_stablecoin_dominance', 0) > 10:
            warnings.append("⚠️ High stablecoin dominance - market in fear mode")
        
        if macro.get('market_structure') == 'risk_off':
            warnings.append("⚠️ Risk-off environment - capital fleeing crypto")
        
        # Volume warnings
        if btc['volume_trend'] == "decreasing" and btc['regime'] == "Bullish":
            warnings.append("⚠️ Bullish move on declining volume - weak hands")
        
        # Divergence warnings
        if btc['regime'] == "Bullish" and eth['regime'] == "Bearish":
            warnings.append("⚠️ BTC/ETH divergence - market uncertainty")
        
        # Funding rate warnings (if available)
        funding = macro.get('funding_rate', {})
        if isinstance(funding, dict):
            if funding.get('sentiment') == 'extremely_bullish':
                warnings.append("⚠️ Funding rates extreme - overleveraged longs")
            elif funding.get('sentiment') == 'extremely_bearish':
                warnings.append("⚠️ Negative funding - potential short squeeze setup")
        
        return warnings[:4]  # Max 4 warnings
    
    def format_full_analysis(self, analysis: Dict) -> str:
        """
        Full analysis format with HTML markup for Telegram
        """
        verdict = analysis['verdict']
        btc = analysis['btc']
        eth = analysis['eth']
        sentiment = analysis['sentiment']
        sectors = analysis['sectors']
        macro = analysis['macro']
        opps = analysis['opportunities']
        strategy = analysis['strategy']
        warnings = analysis.get('warnings', [])
        
        # Build message with HTML
        msg = f"📊 <b>CRYPTO MARKET INTELLIGENCE</b> — {datetime.utcnow().strftime('%A, %b %d')}\n\n"
        
        # === OVERALL VERDICT ===
        msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"{verdict['emoji']} <b>{verdict['status']}</b>\n"
        msg += f"Market Score: <b>{verdict['score']}/100</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += f"<b>{verdict['action']}</b>\n"
        if verdict['reasons']:
            msg += f"↳ {verdict['reasons'][0]}\n"
        msg += "\n"
        
        # === CRITICAL WARNINGS (if any) ===
        if warnings:
            msg += "🚨 <b>CRITICAL ALERTS:</b>\n"
            for warning in warnings:
                msg += f"{warning}\n"
            msg += "\n"
        
        # === MARKET PULSE ===
        msg += "📈 <b>Market Pulse:</b>\n"
        msg += f"• <b>BTC:</b> ${btc['price']:,.0f} ({btc['change_24h']:+.1f}%) — {btc['regime']}"
        if btc['trend_strength'] == 'strong':
            msg += " 💪\n"
        else:
            msg += f" ({btc['trend_strength']})\n"
        
        msg += f"• <b>ETH:</b> ${eth['price']:,.0f} ({eth['change_24h']:+.1f}%) — {eth['regime']}\n"
        msg += f"• <b>BTC Dominance:</b> {macro['btc_dominance']:.1f}%"
        
        # Add market structure context
        market_struct = macro.get('market_structure', 'balanced')
        if market_struct == 'alt_season':
            msg += " 🚀 (Alt season!)\n"
        elif market_struct == 'btc_dominant':
            msg += " ⚠️ (BTC flight to safety)\n"
        elif market_struct == 'risk_off':
            msg += " 🔴 (Risk-off mode)\n"
        else:
            msg += "\n"
        msg += "\n"
        
        # === TECHNICAL INDICATORS ===
        msg += "⚡ <b>Technical Snapshot:</b>\n"
        msg += f"• <b>RSI:</b> BTC {btc['rsi']:.0f}"
        if btc['rsi'] > 70:
            msg += " (Overbought ⚠️)"
        elif btc['rsi'] < 30:
            msg += " (Oversold 👀)"
        msg += f" | ETH {eth['rsi']:.0f}\n"
        
        msg += f"• <b>Volume:</b> {btc['volume_trend'].title()}"
        msg += " ✓\n" if btc['volume_trend'] in ['increasing', 'increasing_strong'] else " ⚠️\n"
        
        msg += f"• <b>Volatility:</b> {btc['volatility_level']} ({btc['volatility_pct']:.1f}%)\n"
        
        msg += f"• <b>Sentiment:</b> {sentiment['classification']} ({sentiment['value']}) {sentiment['emoji']}\n"
        msg += f"  ↳ {sentiment['context']}\n"
        msg += "\n"
        
        # === MACRO ENVIRONMENT ===
        msg += "🌍 <b>Macro Environment:</b>\n"
        
        # Market sentiment from macro
        if 'market_sentiment' in macro:
            market_sent = macro['market_sentiment']
            msg += f"• <b>Market Breadth:</b> {market_sent['positive_pct']:.0f}% positive\n"
        
        # Exchange flow
        exchange_flow = macro.get('exchange_flow', 'neutral')
        flow_signal = macro.get('exchange_flow_signal', 'neutral')
        msg += f"• <b>Exchange Flow:</b> {exchange_flow.replace('_', ' ').title()}"
        if flow_signal == 'bullish':
            msg += " 🟢 (Accumulation)\n"
        elif flow_signal == 'bearish':
            msg += " 🔴 (Distribution)\n"
        else:
            msg += "\n"
        
        # Stablecoin dominance
        stable_dom = macro.get('total_stablecoin_dominance', 0)
        msg += f"• <b>Stablecoin Dom:</b> {stable_dom:.1f}%"
        if stable_dom > 10:
            msg += " ⚠️ (High fear)\n"
        elif stable_dom < 5:
            msg += " 🟢 (Capital deployed)\n"
        else:
            msg += "\n"
        
        # Altcoin season
        if 'altcoin_season' in macro:
            alt_season = macro['altcoin_season']
            msg += f"• <b>Alt Season Index:</b> {alt_season['index']}/100 {alt_season['emoji']}\n"
            msg += f"  ↳ {alt_season['description']}\n"
        
        msg += "\n"
        
        # === SECTOR PERFORMANCE ===
        msg += "🎯 <b>Sector Performance:</b>\n"
        
        # Filter and sort sectors by performance
        valid_sectors = [(name, data) for name, data in sectors.items() 
                        if data.get('data_quality') in ['high', 'medium']]
        valid_sectors.sort(key=lambda x: x[1].get('avg_change', 0), reverse=True)
        
        for sector_name, data in valid_sectors[:6]:  # Top 6 sectors
            display_name = sector_name.replace('_', ' ').title()
            msg += f"• {display_name}: {data['emoji']} ({data['avg_change']:+.1f}%)"
            
            # Add top performer if available
            if 'individual_performances' in data:
                best = data['individual_performances'].get('best', [])
                if best:
                    msg += f" — {best[0]['symbol']} leads"
            msg += "\n"
        
        msg += "\n"
        
        # === OPPORTUNITIES ===
        if opps['top_picks']:
            msg += "🎯 <b>Best Opportunities Today:</b>\n"
            for i, opp in enumerate(opps['top_picks'][:5], 1):
                msg += f"{i}. <b>{opp['asset']}</b> — {opp['reason']}\n"
            msg += "\n"
        
        # === AVOID LIST ===
        if opps['avoid']:
            msg += "⚠️ <b>Avoid Today:</b>\n"
            for item in opps['avoid']:
                severity_emoji = "🔴" if item.get('severity') == 'high' else "🔶"
                msg += f"{severity_emoji} {item['asset']} — {item['reason']}\n"
            msg += "\n"
        
        # === STRATEGY RECOMMENDATION ===
        msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"💡 <b>TRADING STRATEGY</b> (Confidence: {strategy.get('confidence', 'medium')})\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += f"✓ <b>Position Size:</b> {strategy['position_sizing']}\n"
        msg += f"✓ <b>Style:</b> {strategy['trade_style']}\n"
        msg += f"✓ <b>Risk Mgmt:</b> {strategy['risk_management']}\n"
        msg += f"✓ <b>Leverage:</b> {strategy['leverage']}\n"
        msg += f"✓ <b>Focus:</b> {strategy['focus']}\n"
        msg += f"✓ <b>Timeframe:</b> {strategy['timeframe']}\n\n"
        
        # === KEY FACTORS ===
        if verdict.get('reasons'):
            msg += "📝 <b>Key Bullish Factors:</b>\n"
            for reason in verdict['reasons'][:4]:
                msg += f"• {reason}\n"
            msg += "\n"
        
        # Add warnings if present
        if verdict.get('warnings'):
            msg += "⚠️ <b>Risk Factors:</b>\n"
            for warning in verdict['warnings'][:3]:
                msg += f"• {warning}\n"
            msg += "\n"
        
        # === SCORE BREAKDOWN ===
        if 'breakdown' in verdict:
            breakdown = verdict['breakdown']
            msg += "📊 <b>Score Breakdown:</b>\n"
            msg += f"• BTC Technical: {breakdown.get('btc_technical', 0):+.0f} pts\n"
            msg += f"• ETH Technical: {breakdown.get('eth_technical', 0):+.0f} pts\n"
            msg += f"• Sectors: {breakdown.get('sectors', 0):+.0f} pts\n"
            msg += f"• Macro: {breakdown.get('macro', 0):+.0f} pts\n"
            msg += f"• Sentiment: {breakdown.get('sentiment', 0):+.0f} pts\n"
            msg += "\n"
        
        # === FOOTER ===
        msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += (
            "📊 <b>/today Modes</b>\n"
            "• <code>/today</code> — Full market analysis\n"
            "• <code>/today btc</code> — BTC deep dive\n"
            "• <code>/today eth</code> — ETH deep dive (NEW)\n"
            "• <code>/today sectors</code> — Sector breakdown\n"
            "• <code>/today risk</code> — Quick risk assessment\n"
            "• <code>/today macro</code> — Macro market view\n"
        )
        return msg
    
    def format_btc_deep_dive(self, analysis: Dict) -> str:
        """BTC deep dive with HTML markup"""
        btc = analysis['btc']
        sentiment = analysis['sentiment']
        macro = analysis['macro']
        
        msg = f"₿ <b>BITCOIN DEEP DIVE</b>\n\n"
        
        # === PRICE ACTION ===
        msg += "<b>Price Action:</b>\n"
        msg += f"• Current: ${btc['price']:,.0f}\n"
        msg += f"• 24h Change: {btc['change_24h']:+.2f}%\n"
        msg += f"• 24h Range: ${btc['low_24h']:,.0f} - ${btc['high_24h']:,.0f}\n"
        msg += f"• Market Cap: ${btc.get('market_cap', 0):,.0f}\n\n"
        
        # === TECHNICAL ANALYSIS ===
        msg += "<b>Technical Analysis:</b>\n"
        msg += f"• <b>Regime:</b> {btc['regime']} ({btc['trend_strength']} trend)\n"
        msg += f"• <b>50 MA:</b> ${btc['ma_50']:,.0f} ({btc['distance_ma50_pct']:+.1f}%)\n"
        msg += f"• <b>200 MA:</b> ${btc['ma_200']:,.0f} ({btc['distance_ma200_pct']:+.1f}%)\n"
        
        # MA interpretation
        if btc['distance_ma50_pct'] > 5:
            msg += "  ↳ Price extended above 50 MA - potential pullback\n"
        elif btc['distance_ma50_pct'] < -5:
            msg += "  ↳ Price below 50 MA - potential bounce opportunity\n"
        
        msg += f"• <b>RSI(14):</b> {btc['rsi']:.1f}"
        if btc['rsi'] > 70:
            msg += " — Overbought ⚠️\n"
        elif btc['rsi'] < 30:
            msg += " — Oversold 👀\n"
        else:
            msg += " — Neutral ✓\n"
        
        msg += f"• <b>Key Levels:</b> {btc['key_level_status'].replace('_', ' ').title()}\n\n"
        
        # === VOLUME & MOMENTUM ===
        msg += "<b>Volume &amp; Momentum:</b>\n"
        msg += f"• Volume Trend: {btc['volume_trend'].title()}"
        msg += " ✓\n" if btc['volume_trend'] in ['increasing', 'increasing_strong'] else " ⚠️\n"
        msg += f"• Volatility: {btc['volatility_level']} ({btc['volatility_pct']:.1f}%)\n"
        
        # Volume interpretation
        if btc['volume_trend'] == 'increasing' and btc['change_24h'] > 0:
            msg += "  ↳ Rising price on rising volume - healthy\n"
        elif btc['volume_trend'] == 'decreasing' and btc['change_24h'] > 0:
            msg += "  ↳ Rising price on falling volume - weak\n"
        msg += "\n"
        
        # === MARKET CONTEXT ===
        msg += "<b>Market Context:</b>\n"
        msg += f"• BTC Dominance: {macro['btc_dominance']:.1f}%\n"
        msg += f"• Market Structure: {macro.get('market_structure', 'unknown').replace('_', ' ').title()}\n"
        msg += f"• Sentiment: {sentiment['classification']} ({sentiment['value']})\n\n"
        
        # === TRADING ASSESSMENT ===
        msg += "<b>Trading Assessment:</b>\n"
        
        # Generate specific trading advice
        if btc['regime'] == "Bullish" and btc['rsi'] < 70 and btc['volume_trend'] in ['increasing', 'increasing_strong']:
            msg += "✅ <b>FAVORABLE CONDITIONS</b>\n"
            msg += f"• Entry zone: ${btc['ma_50']:,.0f} - ${btc['ma_50'] * 1.02:,.0f}\n"
            msg += f"• Stop loss: Below ${btc['ma_50'] * 0.97:,.0f}\n"
            msg += f"• Target 1: ${btc['price'] * 1.05:,.0f} (+5%)\n"
            msg += f"• Target 2: ${btc['price'] * 1.10:,.0f} (+10%)\n"
            msg += "• Risk/Reward: 1:3 or better\n"
        elif btc['regime'] == "Bearish":
            msg += "⚠️ <b>BEARISH CONDITIONS</b>\n"
            msg += "• Avoid long positions\n"
            msg += f"• Resistance: ${btc['ma_50']:,.0f}\n"
            msg += "• Consider waiting for trend reversal\n"
            msg += "• Watch for capitulation (RSI &lt; 25)\n"
        elif btc['rsi'] > 75:
            msg += "⚠️ <b>OVERBOUGHT</b>\n"
            msg += "• Take profits if in position\n"
            msg += "• Wait for pullback to enter\n"
            msg += f"• Watch ${btc['ma_50']:,.0f} as support on pullback\n"
        elif btc['rsi'] < 30:
            msg += "👀 <b>OVERSOLD - OPPORTUNITY ZONE</b>\n"
            msg += "• Potential bounce setup forming\n"
            msg += "• Wait for RSI &gt; 35 for confirmation\n"
            msg += f"• First resistance: ${btc['ma_50']:,.0f}\n"
        else:
            msg += "🔶 <b>NEUTRAL - WAIT FOR SETUP</b>\n"
            msg += "• No clear directional edge\n"
            msg += "• Range-bound trading only\n"
            msg += f"• Support: ${btc['low_24h']:,.0f}\n"
            msg += f"• Resistance: ${btc['high_24h']:,.0f}\n"
        
        msg += f"\n🕒 Updated: {datetime.utcnow().strftime('%H:%M')} UTC"
        
        return msg
    
    def format_eth_deep_dive(self, analysis: Dict) -> str:
        """ETH-focused deep dive with HTML markup"""
        eth = analysis['eth']
        btc = analysis['btc']
        sentiment = analysis['sentiment']
        macro = analysis['macro']
        
        msg = f"Ξ <b>ETHEREUM DEEP DIVE</b>\n\n"
        
        # === PRICE ACTION ===
        msg += "<b>Price Action:</b>\n"
        msg += f"• Current: ${eth['price']:,.0f}\n"
        msg += f"• 24h Change: {eth['change_24h']:+.2f}%\n"
        msg += f"• 24h Range: ${eth['low_24h']:,.0f} - ${eth['high_24h']:,.0f}\n"
        msg += f"• Market Cap: ${eth.get('market_cap', 0):,.0f}\n"
        msg += f"• ETH/BTC Ratio: {eth['price'] / btc['price']:.4f}\n\n"
        
        # === TECHNICAL ANALYSIS ===
        msg += "<b>Technical Analysis:</b>\n"
        msg += f"• <b>Regime:</b> {eth['regime']} ({eth['trend_strength']} trend)\n"
        msg += f"• <b>50 MA:</b> ${eth['ma_50']:,.0f} ({eth['distance_ma50_pct']:+.1f}%)\n"
        msg += f"• <b>200 MA:</b> ${eth['ma_200']:,.0f} ({eth['distance_ma200_pct']:+.1f}%)\n"
        msg += f"• <b>RSI(14):</b> {eth['rsi']:.1f}"
        
        if eth['rsi'] > 70:
            msg += " — Overbought ⚠️\n"
        elif eth['rsi'] < 30:
            msg += " — Oversold 👀\n"
        else:
            msg += " — Neutral ✓\n"
        
        msg += f"• <b>Key Levels:</b> {eth['key_level_status'].replace('_', ' ').title()}\n\n"
        
        # === ETH-SPECIFIC METRICS ===
        msg += "<b>Volume &amp; Momentum:</b>\n"
        msg += f"• Volume Trend: {eth['volume_trend'].title()}\n"
        msg += f"• Volatility: {eth['volatility_level']} ({eth['volatility_pct']:.1f}%)\n"
        
        # BTC correlation
        if eth['regime'] == btc['regime']:
            msg += f"• BTC Alignment: ✓ Both {eth['regime']}\n"
        else:
            msg += f"• BTC Divergence: ⚠️ ETH {eth['regime']}, BTC {btc['regime']}\n"
        msg += "\n"
        
        # === MARKET CONTEXT ===
        msg += "<b>Market Context:</b>\n"
        msg += f"• ETH Dominance: {macro['eth_dominance']:.1f}%\n"
        msg += f"• Market Structure: {macro.get('market_structure', 'unknown').replace('_', ' ').title()}\n"
        msg += f"• Sentiment: {sentiment['classification']} ({sentiment['value']})\n\n"
        
        # === TRADING ASSESSMENT ===
        msg += "<b>Trading Assessment:</b>\n"
        
        if eth['regime'] == "Bullish" and eth['rsi'] < 70:
            msg += "✅ <b>FAVORABLE CONDITIONS</b>\n"
            msg += f"• Entry zone: ${eth['ma_50']:,.0f} - ${eth['ma_50'] * 1.02:,.0f}\n"
            msg += f"• Stop loss: Below ${eth['ma_50'] * 0.97:,.0f}\n"
            msg += f"• Target 1: ${eth['price'] * 1.05:,.0f} (+5%)\n"
            msg += f"• Target 2: ${eth['price'] * 1.10:,.0f} (+10%)\n"
        elif eth['regime'] == "Bearish":
            msg += "⚠️ <b>BEARISH CONDITIONS</b>\n"
            msg += "• Avoid long positions\n"
            msg += f"• Resistance: ${eth['ma_50']:,.0f}\n"
            msg += "• Wait for trend reversal confirmation\n"
        elif eth['rsi'] > 75:
            msg += "⚠️ <b>OVERBOUGHT</b>\n"
            msg += "• Take profits if holding\n"
            msg += f"• Wait for pullback to ${eth['ma_50']:,.0f}\n"
        else:
            msg += "🔶 <b>NEUTRAL - WAIT FOR SETUP</b>\n"
            msg += "• No clear directional edge\n"
            msg += f"• Support: ${eth['low_24h']:,.0f}\n"
            msg += f"• Resistance: ${eth['high_24h']:,.0f}\n"
        
        msg += f"\n🕒 Updated: {datetime.utcnow().strftime('%H:%M')} UTC"
        
        return msg
    
    def format_sectors_only(self, analysis: Dict) -> str:
        """Sector breakdown with HTML markup"""
        sectors = analysis['sectors']
        opps = analysis['opportunities']
        macro = analysis.get('macro', {})
        
        msg = f"🎯 <b>SECTOR ANALYSIS</b>\n\n"
        
        # === MARKET BREADTH ===
        if 'market_sentiment' in macro:
            market_sent = macro['market_sentiment']
            msg += f"<b>Market Breadth:</b> {market_sent['emoji']} {market_sent['sentiment'].title()}\n"
            msg += f"{market_sent['positive_pct']:.0f}% of top 100 coins positive\n\n"
        
        # === ALTCOIN SEASON ===
        if 'altcoin_season' in macro:
            alt_season = macro['altcoin_season']
            msg += f"<b>Alt Season Index:</b> {alt_season['index']}/100 {alt_season['emoji']}\n"
            msg += f"{alt_season['description']}\n\n"
        
        msg += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # === SECTOR PERFORMANCE ===
        msg += "<b>Sector Performance:</b>\n\n"
        
        # Filter valid sectors and sort by performance
        valid_sectors = [
            (name, data) for name, data in sectors.items() 
            if data.get('data_quality') in ['high', 'medium']
        ]
        valid_sectors.sort(key=lambda x: x[1].get('avg_change', 0), reverse=True)
        
        for sector_name, data in valid_sectors:
            display_name = sector_name.replace('_', ' ').title()
            
            msg += f"{data['emoji']} <b>{display_name}</b>\n"
            msg += f"   • Change: {data['avg_change']:+.2f}% (weighted avg)\n"
            msg += f"   • Momentum: {data['momentum'].replace('_', ' ').title()}\n"
            msg += f"   • Coins Tracked: {data['coins_tracked']}/{data.get('total_coins', 0)}\n"
            msg += f"   • Data Quality: {data['data_quality'].title()}\n"
            
            # Add top/bottom performers if available
            if 'individual_performances' in data:
                perfs = data['individual_performances']
                
                if perfs.get('best'):
                    best = perfs['best'][:2]  # Top 2
                    msg += f"   • Top: "
                    msg += ", ".join([f"{coin['symbol']} ({coin['change']:+.1f}%)" for coin in best])
                    msg += "\n"
                
                if perfs.get('worst'):
                    worst = perfs['worst'][:1]  # Bottom 1
                    msg += f"   • Worst: "
                    msg += ", ".join([f"{coin['symbol']} ({coin['change']:+.1f}%)" for coin in worst])
                    msg += "\n"
            
            # Trading recommendation
            msg += f"   • Status: "
            if data['momentum'] in ['very_strong', 'strong']:
                msg += "✓ Good for trading\n"
            elif data['momentum'] == 'moderate':
                msg += "Selective opportunities\n"
            elif data['momentum'] == 'neutral':
                msg += "Mixed signals\n"
            else:
                msg += "⚠️ Avoid for now\n"
            
            msg += "\n"
        
        # === OPPORTUNITIES ===
        if opps['top_picks']:
            msg += "<b>🎯 Best Opportunities:</b>\n"
            for opp in opps['top_picks'][:5]:
                quality = "★" * min(5, opp.get('quality_score', 0))
                msg += f"• {opp['asset']} {quality}\n"
                msg += f"  ↳ {opp['reason']}\n"
            msg += "\n"
        
        # === AVOID ===
        if opps['avoid']:
            msg += "<b>⚠️ Sectors to Avoid:</b>\n"
            for item in opps['avoid'][:3]:
                msg += f"• {item['asset']} — {item['reason']}\n"
            msg += "\n"
        
        msg += f"🕒 Updated: {datetime.utcnow().strftime('%H:%M')} UTC"
        
        return msg
    
    def format_risk_only(self, analysis: Dict) -> str:
        """Quick risk assessment with HTML markup"""
        verdict = analysis['verdict']
        btc = analysis['btc']
        eth = analysis['eth']
        sentiment = analysis['sentiment']
        macro = analysis['macro']
        strategy = analysis['strategy']
        warnings = analysis.get('warnings', [])
        
        msg = f"⚡ <b>QUICK RISK CHECK</b>\n\n"
        
        # === OVERALL STATUS ===
        msg += f"{verdict['emoji']} <b>{verdict['status']}</b>\n"
        msg += f"<b>Market Score:</b> {verdict['score']}/100\n"
        msg += f"<b>Risk Level:</b> {verdict['risk_level']}\n\n"
        
        # === QUICK STATS ===
        msg += "<b>Market Snapshot:</b>\n"
        msg += f"• BTC: ${btc['price']:,.0f} ({btc['change_24h']:+.1f}%) — {btc['regime']}\n"
        msg += f"• ETH: ${eth['price']:,.0f} ({eth['change_24h']:+.1f}%) — {eth['regime']}\n"
        msg += f"• RSI: BTC {btc['rsi']:.0f} | ETH {eth['rsi']:.0f}\n"
        msg += f"• Volatility: {btc['volatility_level']}\n"
        msg += f"• Sentiment: {sentiment['classification']} ({sentiment['value']})\n"
        msg += f"• BTC Dom: {macro['btc_dominance']:.1f}%\n\n"
        
        # === ACTION ===
        msg += f"<b>Recommended Action:</b>\n"
        msg += f"✓ {verdict['action']}\n\n"
        
        # === STRATEGY ===
        msg += "<b>Today's Strategy:</b>\n"
        msg += f"• Size: {strategy['position_sizing']}\n"
        msg += f"• Style: {strategy['trade_style']}\n"
        msg += f"• Leverage: {strategy['leverage']}\n"
        msg += f"• Focus: {strategy['focus']}\n\n"
        
        # === WARNINGS ===
        if warnings:
            msg += "<b>⚠️ Alerts:</b>\n"
            for warning in warnings[:3]:
                msg += f"{warning}\n"
            msg += "\n"
        elif verdict['score'] >= 70:
            msg += "<b>✅ All Clear:</b>\n"
            msg += "No major red flags detected\n\n"
        
        # === CONFIDENCE ===
        confidence = strategy.get('confidence', 'medium')
        msg += f"<b>Confidence:</b> {confidence.title()}\n"
        
        msg += f"\n🕒 {datetime.utcnow().strftime('%H:%M')} UTC\n"
        msg += "💬 <code>/today</code> for full analysis | <code>/today btc</code> for BTC deep dive"
        
        return msg
    
    def format_macro_only(self, analysis: Dict) -> str:
        """Macro-focused view with HTML markup"""
        macro = analysis['macro']
        verdict = analysis['verdict']
        
        msg = f"🌍 <b>MACRO MARKET VIEW</b>\n\n"
        
        # === MARKET STRUCTURE ===
        msg += "<b>Market Structure:</b>\n"
        msg += f"• Status: {macro.get('market_structure', 'unknown').replace('_', ' ').title()}\n"
        msg += f"• Overall Score: {verdict['score']}/100 {verdict['emoji']}\n\n"
        
        # === DOMINANCE ===
        msg += "<b>Dominance Breakdown:</b>\n"
        msg += f"• BTC: {macro['btc_dominance']:.1f}%\n"
        msg += f"• ETH: {macro['eth_dominance']:.1f}%\n"
        msg += f"• Stablecoins: {macro['total_stablecoin_dominance']:.1f}%\n"
        msg += f"• Others: {macro['others_dominance']:.1f}%\n\n"
        
        # === FLOWS ===
        msg += "<b>Capital Flows:</b>\n"
        msg += f"• Exchange Flow: {macro['exchange_flow'].replace('_', ' ').title()}\n"
        msg += f"  ↳ Signal: {macro['exchange_flow_signal'].replace('_', ' ').title()}\n"
        
        if 'volume_trend' in macro:
            msg += f"• Volume Trend: {macro['volume_trend'].replace('_', ' ').title()}\n"
            if 'volume_change_7d' in macro:
                msg += f"  ↳ 7d Change: {macro['volume_change_7d']:+.1f}%\n"
        msg += "\n"
        
        # === SENTIMENT ===
        if 'market_sentiment' in macro:
            market_sent = macro['market_sentiment']
            msg += "<b>Market Sentiment:</b>\n"
            msg += f"• Status: {market_sent['sentiment'].title()} {market_sent['emoji']}\n"
            msg += f"• Breadth: {market_sent['positive_pct']:.0f}% positive\n\n"
        
        # === ALTCOIN SEASON ===
        if 'altcoin_season' in macro:
            alt_season = macro['altcoin_season']
            msg += "<b>Altcoin Season Index:</b>\n"
            msg += f"• Score: {alt_season['index']}/100 {alt_season['emoji']}\n"
            msg += f"• Status: {alt_season['season'].replace('_', ' ').title()}\n"
            msg += f"• BTC 30d: {alt_season.get('btc_performance_30d', 0):+.1f}%\n"
            
            if 'breakdown' in alt_season:
                breakdown = alt_season['breakdown']
                msg += f"• Large caps outperforming: {breakdown.get('large_cap', {}).get('pct', 0):.0f}%\n"
                msg += f"• Mid caps outperforming: {breakdown.get('mid_cap', {}).get('pct', 0):.0f}%\n"
            msg += "\n"
        
        # === FUNDING ===
        if 'funding_rate' in macro:
            funding = macro['funding_rate']
            if isinstance(funding, dict):
                msg += "<b>Funding Rate Estimate:</b>\n"
                msg += f"• Rate: {funding.get('rate', 0):.4f}\n"
                msg += f"• Sentiment: {funding.get('sentiment', 'neutral').replace('_', ' ').title()}\n\n"
        
        # === INTERPRETATION ===
        msg += "<b>Interpretation:</b>\n"
        
        if macro.get('market_structure') == 'risk_off':
            msg += "⚠️ Risk-off: Capital fleeing to stables\n"
        elif macro.get('market_structure') == 'risk_on':
            msg += "✅ Risk-on: Capital deploying into crypto\n"
        elif macro.get('market_structure') == 'alt_season':
            msg += "🚀 Alt season: Broad altcoin strength\n"
        elif macro.get('market_structure') == 'btc_dominant':
            msg += "₿ BTC dominance: Flight to safety\n"
        
        msg += f"\n🕒 Updated: {datetime.utcnow().strftime('%H:%M')} UTC"
        
        return msg