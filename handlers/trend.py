"""
Enhanced Trend Analysis Command - FIXED SIGNAL CALCULATION
Properly distinguishes between oversold (weakness) and bullish signals
"""

from utils.indicators import get_crypto_indicators
from models.user import get_user_plan
from utils.auth import is_pro_plan
from telegram import Update
from telegram.ext import ContextTypes
from tasks.handlers import handle_streak
from models.user_activity import update_last_active


async def trend_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/trend")
    await handle_streak(update, context)
    args = context.args

    if not args:
        await update.message.reply_text("❌ Usage: /trend [coin] [timeframe]\nExample: /trend ETH 4h")
        return

    symbol = args[0].upper().replace("USDT", "") + "/USDT"
    timeframe = args[1] if len(args) > 1 else "1h"
    
    # Mapping of user-friendly timeframes to API timeframes
    timeframe_map = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "1d": "1day",
        "1w": "1week",
        "1M": "1month"
    }
    
    allowed_timeframes = ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "1d", "1w", "1M"]

    if timeframe not in allowed_timeframes:
        await update.message.reply_text(
            f"❌ Invalid timeframe. Use one of: {', '.join(allowed_timeframes)}"
        )
        return

    plan = get_user_plan(user_id)
    if plan == "free" and timeframe != "1h":
        await update.message.reply_text(
            "🔒 Only the *1h* timeframe is available on Free Plan.\nUse /upgrade to unlock more.",
            parse_mode="Markdown"
        )
        return

    api_timeframe = timeframe_map[timeframe]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        indicators = await get_crypto_indicators(symbol, api_timeframe)
        if not indicators:
            await update.message.reply_text("⚠️ Could not fetch indicator data.")
            return

        def safe_float(v):
            try:
                return float(v)
            except:
                return None

        # ========================================================================
        # EXTRACT ALL INDICATORS
        # ========================================================================
        
        price = safe_float(indicators.get("price"))
        ema20 = safe_float(indicators.get("ema20"))
        
        # Momentum
        rsi = safe_float(indicators.get("rsi"))
        macd = safe_float(indicators.get("macd"))
        macd_signal = safe_float(indicators.get("macdSignal"))
        macd_hist = safe_float(indicators.get("macdHist"))
        stochK = safe_float(indicators.get("stochK"))
        stochD = safe_float(indicators.get("stochD"))
        cci = safe_float(indicators.get("cci"))
        williamsR = safe_float(indicators.get("williamsR"))
        roc = safe_float(indicators.get("roc"))
        
        # Volatility
        atr = safe_float(indicators.get("atr"))
        bbUpper = safe_float(indicators.get("bbUpper"))
        bbMiddle = safe_float(indicators.get("bbMiddle"))
        bbLower = safe_float(indicators.get("bbLower"))
        
        # Volume
        mfi = safe_float(indicators.get("mfi"))
        vwap = safe_float(indicators.get("vwap"))
        obv = safe_float(indicators.get("obv"))
        
        # Trend Strength
        adx = safe_float(indicators.get("adx"))
        plusDI = safe_float(indicators.get("plusDI"))
        minusDI = safe_float(indicators.get("minusDI"))

        # ========================================================================
        # BUILD COMPREHENSIVE MESSAGE
        # ========================================================================
        
        msg = f"📊 *Trend Analysis for {symbol}* ({timeframe})\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        # PRICE & TREND
        msg += "💰 *Price & Trend*\n"
        msg += f"• Price: `${price:.2f}`\n" if price else "• Price: `N/A`\n"
        msg += f"• EMA20: `${ema20:.2f}`\n" if ema20 else "• EMA20: `N/A`\n"
        
        if price and ema20:
            if price > ema20:
                msg += "  → 🟢 Above EMA (Bullish)\n"
            else:
                msg += "  → 🔴 Below EMA (Bearish)\n"
        
        msg += "\n"

        # MOMENTUM INDICATORS
        msg += "⚡ *Momentum*\n"
        
        # RSI
        if rsi:
            if rsi > 70:
                rsi_status = "🔺 Overbought"
            elif rsi < 30:
                rsi_status = "🔻 Oversold"
            else:
                rsi_status = "🟡 Neutral"
            msg += f"• RSI: `{rsi:.2f}` → {rsi_status}\n"
        else:
            msg += "• RSI: `N/A`\n"

        # MACD
        if macd is not None and macd_signal is not None:
            trend = "🔼 Bullish" if macd > macd_signal else "🔽 Bearish"
            msg += f"• MACD: `{macd:.2f}` | Signal: `{macd_signal:.2f}`\n"
            if macd_hist:
                msg += f"  Histogram: `{macd_hist:.2f}` → {trend}\n"
        else:
            msg += "• MACD: `N/A`\n"

        # Stochastic
        if stochK and stochD:
            if stochK > 80:
                stoch_status = "🔺 Overbought"
            elif stochK < 20:
                stoch_status = "🔻 Oversold"
            else:
                stoch_status = "🟡 Neutral"
            msg += f"• Stochastic: K=`{stochK:.2f}` | D=`{stochD:.2f}`\n"
            msg += f"  → {stoch_status}\n"
        else:
            msg += "• Stochastic: `N/A`\n"

        # CCI
        if cci:
            if cci > 100:
                cci_status = "🔺 Overbought"
            elif cci < -100:
                cci_status = "🔻 Oversold"
            else:
                cci_status = "🟡 Neutral"
            msg += f"• CCI: `{cci:.2f}` → {cci_status}\n"
        else:
            msg += "• CCI: `N/A`\n"

        # Williams %R
        if williamsR:
            if williamsR > -20:
                wr_status = "🔺 Overbought"
            elif williamsR < -80:
                wr_status = "🔻 Oversold"
            else:
                wr_status = "🟡 Neutral"
            msg += f"• Williams %R: `{williamsR:.2f}` → {wr_status}\n"
        else:
            msg += "• Williams %R: `N/A`\n"

        # ROC
        if roc:
            roc_status = "🔼 Positive" if roc > 0 else "🔽 Negative"
            msg += f"• ROC: `{roc:.2f}%` → {roc_status}\n"
        else:
            msg += "• ROC: `N/A`\n"

        msg += "\n"

        # VOLATILITY INDICATORS
        msg += "📉 *Volatility*\n"
        
        if atr:
            msg += f"• ATR: `{atr:.4f}`\n"
        else:
            msg += "• ATR: `N/A`\n"

        # Bollinger Bands
        if bbUpper and bbMiddle and bbLower and price:
            msg += f"• BB Upper: `${bbUpper:.2f}`\n"
            msg += f"• BB Middle: `${bbMiddle:.2f}`\n"
            msg += f"• BB Lower: `${bbLower:.2f}`\n"
            
            if price > bbUpper:
                msg += "  → 🔺 Above upper band (Overbought)\n"
            elif price < bbLower:
                msg += "  → 🔻 Below lower band (Oversold)\n"
            elif price > bbMiddle:
                msg += "  → 🟢 Upper half (Bullish bias)\n"
            else:
                msg += "  → 🔴 Lower half (Bearish bias)\n"
        else:
            msg += "• Bollinger Bands: `N/A`\n"

        msg += "\n"

        # VOLUME INDICATORS
        msg += "📊 *Volume*\n"
        
        # MFI
        if mfi:
            if mfi > 80:
                mfi_status = "🔺 Overbought"
            elif mfi < 20:
                mfi_status = "🔻 Oversold"
            else:
                mfi_status = "🟡 Neutral"
            msg += f"• MFI: `{mfi:.2f}` → {mfi_status}\n"
        else:
            msg += "• MFI: `N/A`\n"

        # VWAP
        if vwap and price:
            vwap_status = "🟢 Bullish" if price > vwap else "🔴 Bearish"
            msg += f"• VWAP: `${vwap:.2f}` → {vwap_status}\n"
        else:
            msg += "• VWAP: `N/A`\n"

        # OBV
        if obv:
            obv_status = "🔼 Buying pressure" if obv > 0 else "🔽 Selling pressure"
            if abs(obv) >= 1_000_000_000:
                obv_display = f"{obv / 1_000_000_000:.2f}B"
            elif abs(obv) >= 1_000_000:
                obv_display = f"{obv / 1_000_000:.2f}M"
            elif abs(obv) >= 1_000:
                obv_display = f"{obv / 1_000:.2f}K"
            else:
                obv_display = f"{obv:.2f}"
            msg += f"• OBV: `{obv_display}` → {obv_status}\n"
        else:
            msg += "• OBV: `N/A`\n"

        msg += "\n"

        # TREND STRENGTH
        msg += "💪 *Trend Strength*\n"
        
        if adx is not None:
            if adx >= 40:
                adx_status = "🔥 Very Strong"
            elif adx >= 25:
                adx_status = "💪 Strong"
            elif adx >= 20:
                adx_status = "⚡ Moderate"
            else:
                adx_status = "⚖️ Weak/No Trend"
            msg += f"• ADX: `{adx:.2f}` → {adx_status}\n"
        else:
            msg += "• ADX: `N/A`\n"

        # Directional Indicators
        if plusDI is not None and minusDI is not None:
            if plusDI > minusDI:
                di_status = "🔼 Uptrend"
            else:
                di_status = "🔽 Downtrend"
            msg += f"• +DI: `{plusDI:.2f}` | -DI: `{minusDI:.2f}`\n"
            msg += f"  → {di_status}\n"
        else:
            msg += "• Directional Indicators: `N/A`\n"

        # ========================================================================
        # FIXED SIGNAL CALCULATION
        # ========================================================================
        
        signal_score = 0
        total_weight = 0
        signal_details = {"bullish": [], "bearish": [], "neutral": []}
        
        # --- CRITICAL FIX: Oversold ≠ Bullish Signal ---
        # Oversold only becomes bullish when paired with reversal signs
        
        # RSI (weight: 12)
        if rsi:
            if rsi > 70:
                signal_score -= 12
                signal_details["bearish"].append("RSI Overbought (>70)")
            elif rsi > 55:
                signal_score -= 6
                signal_details["bearish"].append("RSI Elevated")
            elif rsi < 30:
                # Oversold is NOT bullish unless confirmed by reversal
                signal_score -= 8  # Still bearish momentum
                signal_details["bearish"].append("RSI Oversold (Weak Momentum)")
            elif rsi < 40:
                signal_score -= 4
                signal_details["bearish"].append("RSI Low (Bearish Bias)")
            elif rsi > 50:
                signal_score += 4
                signal_details["bullish"].append("RSI Above 50")
            total_weight += 12
        
        # MACD (weight: 15) - MOST IMPORTANT
        if macd is not None and macd_signal is not None and macd_hist is not None:
            macd_diff = macd - macd_signal
            
            # Strong bearish: MACD below signal AND histogram negative
            if macd < macd_signal and macd_hist < 0:
                if abs(macd_hist) > abs(macd_signal) * 0.1:  # Strong divergence
                    signal_score -= 15
                    signal_details["bearish"].append("MACD Strong Bearish Divergence")
                else:
                    signal_score -= 10
                    signal_details["bearish"].append("MACD Bearish")
            
            # Strong bullish: MACD above signal AND histogram positive
            elif macd > macd_signal and macd_hist > 0:
                if macd_hist > abs(macd_signal) * 0.1:
                    signal_score += 15
                    signal_details["bullish"].append("MACD Strong Bullish")
                else:
                    signal_score += 10
                    signal_details["bullish"].append("MACD Bullish")
            
            # Weak signals
            elif macd > macd_signal:
                signal_score += 5
                signal_details["bullish"].append("MACD Weakly Bullish")
            else:
                signal_score -= 5
                signal_details["bearish"].append("MACD Weakly Bearish")
            
            total_weight += 15
        
        # Stochastic (weight: 8)
        if stochK and stochD:
            if stochK > 80:
                signal_score -= 8
                signal_details["bearish"].append("Stochastic Overbought")
            elif stochK < 20:
                # Oversold stochastic = bearish until proven otherwise
                signal_score -= 6
                signal_details["bearish"].append("Stochastic Oversold (Weak)")
            elif stochK > stochD and stochK > 50:
                signal_score += 6
                signal_details["bullish"].append("Stochastic Bullish Cross")
            elif stochK < stochD and stochK < 50:
                signal_score -= 6
                signal_details["bearish"].append("Stochastic Bearish Cross")
            total_weight += 8
        
        # MFI (weight: 8)
        if mfi:
            if mfi > 80:
                signal_score -= 8
                signal_details["bearish"].append("MFI Overbought")
            elif mfi < 20:
                signal_score -= 6
                signal_details["bearish"].append("MFI Oversold (Weak Money Flow)")
            elif mfi > 50:
                signal_score += 4
                signal_details["bullish"].append("MFI Above 50")
            else:
                signal_score -= 4
                signal_details["bearish"].append("MFI Below 50")
            total_weight += 8
        
        # ROC (weight: 6)
        if roc:
            if roc > 5:
                signal_score += 6
                signal_details["bullish"].append("Strong Positive Momentum (ROC)")
            elif roc > 2:
                signal_score += 3
                signal_details["bullish"].append("Positive Momentum")
            elif roc < -5:
                signal_score -= 6
                signal_details["bearish"].append("Strong Negative Momentum (ROC)")
            elif roc < -2:
                signal_score -= 3
                signal_details["bearish"].append("Negative Momentum")
            total_weight += 6
        
        # --- TREND INDICATORS (35% weight) ---
        
        # Price vs EMA20 (weight: 12)
        if price and ema20:
            price_ema_diff = ((price - ema20) / ema20) * 100
            if price_ema_diff > 3:
                signal_score += 12
                signal_details["bullish"].append("Price Strong Above EMA20")
            elif price_ema_diff > 0:
                signal_score += 6
                signal_details["bullish"].append("Price Above EMA20")
            elif price_ema_diff < -3:
                signal_score -= 12
                signal_details["bearish"].append("Price Strong Below EMA20")
            else:
                signal_score -= 6
                signal_details["bearish"].append("Price Below EMA20")
            total_weight += 12
        
        # ADX + DI (weight: 13) - TREND STRENGTH MATTERS
        if adx and plusDI and minusDI:
            di_diff = plusDI - minusDI
            
            # Strong trend (ADX > 25)
            if adx >= 25:
                if di_diff > 10:
                    signal_score += 13
                    signal_details["bullish"].append("Strong Uptrend (ADX>25)")
                elif di_diff < -10:
                    signal_score -= 13
                    signal_details["bearish"].append("Strong Downtrend (ADX>25)")
                elif di_diff > 0:
                    signal_score += 7
                    signal_details["bullish"].append("Moderate Uptrend")
                else:
                    signal_score -= 7
                    signal_details["bearish"].append("Moderate Downtrend")
            # Weak trend
            else:
                signal_details["neutral"].append(f"Weak Trend (ADX={adx:.1f})")
            
            total_weight += 13
        
        # Price vs VWAP (weight: 10)
        if price and vwap:
            price_vwap_diff = ((price - vwap) / vwap) * 100
            if price_vwap_diff > 1:
                signal_score += 10
                signal_details["bullish"].append("Price Above VWAP")
            elif price_vwap_diff > 0:
                signal_score += 5
                signal_details["bullish"].append("Price Slightly Above VWAP")
            elif price_vwap_diff < -1:
                signal_score -= 10
                signal_details["bearish"].append("Price Below VWAP")
            else:
                signal_score -= 5
                signal_details["bearish"].append("Price Slightly Below VWAP")
            total_weight += 10
        
        # --- VOLATILITY (15% weight) ---
        
        # Bollinger Bands (weight: 15)
        if price and bbUpper and bbLower and bbMiddle:
            bb_width = bbUpper - bbLower
            bb_position = (price - bbLower) / bb_width if bb_width > 0 else 0.5
            
            if bb_position > 0.95:
                signal_score -= 15
                signal_details["bearish"].append("Price at BB Upper Band")
            elif bb_position > 0.7:
                signal_score -= 8
                signal_details["bearish"].append("Price in Upper BB Range")
            elif bb_position < 0.05:
                # Below BB lower = oversold but still bearish momentum
                signal_score -= 10
                signal_details["bearish"].append("Price at BB Lower Band (Oversold)")
            elif bb_position < 0.3:
                signal_score -= 5
                signal_details["bearish"].append("Price in Lower BB Range")
            elif bb_position > 0.5:
                signal_score += 5
                signal_details["bullish"].append("Price Above BB Middle")
            total_weight += 15
        
        # ========================================================================
        # NORMALIZE & DETERMINE SIGNAL
        # ========================================================================
        
        if total_weight > 0:
            normalized_score = (signal_score / total_weight) * 100
        else:
            normalized_score = 0
        
        # Determine signal with proper thresholds
        if normalized_score >= 35:
            signal = "🟢 STRONG BUY"
            confidence = min(95, 65 + abs(normalized_score) * 0.4)
        elif normalized_score >= 15:
            signal = "🟢 BUY"
            confidence = min(85, 60 + abs(normalized_score) * 0.4)
        elif normalized_score >= -15:
            signal = "🟡 NEUTRAL"
            confidence = 50 + abs(normalized_score) * 1.5
        elif normalized_score >= -35:
            signal = "🔴 SELL"
            confidence = min(85, 60 + abs(normalized_score) * 0.4)
        else:
            signal = "🔴 STRONG SELL"
            confidence = min(95, 65 + abs(normalized_score) * 0.4)
        
        # ========================================================================
        # ADD SIGNAL TO MESSAGE
        # ========================================================================
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"🎯 *Overall Signal: {signal}*\n"
        msg += f"📊 Confidence: `{confidence:.0f}%`\n"
        msg += f"📈 Score: `{normalized_score:+.1f}/100`\n\n"
        
        # Show supporting signals
        if signal_details["bullish"]:
            msg += "✅ *Bullish Factors:*\n"
            for detail in signal_details["bullish"][:6]:
                msg += f"  • {detail}\n"
        
        if signal_details["bearish"]:
            msg += "\n❌ *Bearish Factors:*\n"
            for detail in signal_details["bearish"][:6]:
                msg += f"  • {detail}\n"
        
        if signal_details["neutral"]:
            msg += "\n⚠️ *Neutral Factors:*\n"
            for detail in signal_details["neutral"][:3]:
                msg += f"  • {detail}\n"
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "_⚠️ Not financial advice. Always DYOR._"
    
        await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        print("Trend command error:", e)
        await update.message.reply_text("❌ Error fetching trend data.")
