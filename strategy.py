import pandas as pd
import numpy as np
import ta

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tính toán đầy đủ các chỉ báo kỹ thuật cốt lõi:
    - MACD (12, 26, 9)
    - RSI (14)
    - Khối lượng: SMA 9, SMA 20
    - Bollinger Bands: Mid (20), Upper, Lower, Width
    - Đường xu hướng: EMA 20, EMA 50, SMA 200
    - Ichimoku Cloud: Tenkan-sen (9), Kijun-sen (26), Senkou Span A, Senkou Span B, Chikou Span
    - ADX (14)
    """
    if df.empty or len(df) < 5:
        return df

    df = df.copy()

    # 1. MACD (12, 26, 9)
    if len(df) >= 26:
        macd = ta.trend.MACD(close=df['close'], window_slow=26, window_fast=12, window_sign=9)
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_hist'] = macd.macd_diff()
    else:
        df['macd'] = 0.0
        df['macd_signal'] = 0.0
        df['macd_hist'] = 0.0

    # 2. RSI (14)
    if len(df) >= 14:
        df['rsi'] = ta.momentum.rsi(close=df['close'], window=14)
    else:
        df['rsi'] = 50.0

    # 3. Volume SMA
    df['vol_sma9'] = df['volume'].rolling(window=min(9, len(df)), min_periods=1).mean()
    df['vol_sma20'] = df['volume'].rolling(window=min(20, len(df)), min_periods=1).mean()

    # 4. Moving Averages: EMA 20, EMA 50, SMA 200
    df['ema20'] = ta.trend.ema_indicator(close=df['close'], window=min(20, len(df)))
    df['ema50'] = ta.trend.ema_indicator(close=df['close'], window=min(50, len(df))) if len(df) >= 30 else df['ema20']
    df['sma200'] = ta.trend.sma_indicator(close=df['close'], window=min(200, len(df))) if len(df) >= 100 else df['ema50']

    # 5. Bollinger Bands (20, 2)
    if len(df) >= 20:
        bb = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
        df['bb_mid'] = bb.bollinger_mavg()
        df['bb_high'] = bb.bollinger_hband()
        df['bb_low'] = bb.bollinger_lband()
        df['bb_width'] = bb.bollinger_wband()
    else:
        df['bb_mid'] = df['close']
        df['bb_high'] = df['close'] * 1.05
        df['bb_low'] = df['close'] * 0.95
        df['bb_width'] = 0.1

    # 6. Ichimoku Cloud (9, 26, 52)
    high = df['high']
    low = df['low']
    close = df['close']

    # Tenkan-sen (Conversion Line): (9-period high + 9-period low) / 2
    nine_high = high.rolling(window=min(9, len(df)), min_periods=1).max()
    nine_low = low.rolling(window=min(9, len(df)), min_periods=1).min()
    df['ichimoku_tenkan'] = (nine_high + nine_low) / 2

    # Kijun-sen (Base Line): (26-period high + 26-period low) / 2
    period26_high = high.rolling(window=min(26, len(df)), min_periods=1).max()
    period26_low = low.rolling(window=min(26, len(df)), min_periods=1).min()
    df['ichimoku_kijun'] = (period26_high + period26_low) / 2

    # Senkou Span A (Leading Span A): (Conversion Line + Base Line) / 2
    df['ichimoku_span_a'] = ((df['ichimoku_tenkan'] + df['ichimoku_kijun']) / 2).shift(26)

    # Senkou Span B (Leading Span B): (52-period high + 52-period low) / 2
    period52_high = high.rolling(window=min(52, len(df)), min_periods=1).max()
    period52_low = low.rolling(window=min(52, len(df)), min_periods=1).min()
    df['ichimoku_span_b'] = ((period52_high + period52_low) / 2).shift(26)

    # Chikou Span (Lagging Span): Close shifted back 26 periods
    df['ichimoku_chikou'] = close.shift(-26)

    # 7. ADX (14)
    if len(df) >= 15:
        try:
            adx_indicator = ta.trend.ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14)
            df['adx'] = adx_indicator.adx()
        except Exception:
            df['adx'] = 20.0
    else:
        df['adx'] = 20.0

    return df


def generate_signals(
    df: pd.DataFrame,
    strategy_type: str = 'trend',
    market_regime: pd.Series = None,
    use_mtf: bool = False
) -> pd.DataFrame:
    """
    Sinh tín hiệu giao dịch định lượng chuẩn hóa:
    - strategy_type: 'trend', 'momentum', 'mean_reversion'
    - market_regime: Series boolean thể hiện điều kiện thị trường chung (VNINDEX > SMA50)
    - use_mtf: Kiểm tra xu hướng khung thời gian lớn hơn (Weekly/EMA50)
    
    Trả về DataFrame bổ sung các cột:
    - 'signal': 'Buy', 'Sell', 'Hold'
    - 'score': 0 -> 100
    - 'reason': Chuỗi giải thích chi tiết tín hiệu
    """
    if df.empty:
        return df

    df = df.copy()
    if 'rsi' not in df.columns or 'macd' not in df.columns:
        df = compute_indicators(df)

    n = len(df)
    signals = ['Hold'] * n
    scores = [50.0] * n
    reasons = ['Chờ đợi tín hiệu rõ ràng hơn'] * n

    for i in range(n):
        row = df.iloc[i]
        score = 50.0
        signal = 'Hold'
        reason_list = []

        close_price = row.get('close', 0)
        ema20 = row.get('ema20', close_price)
        ema50 = row.get('ema50', close_price)
        rsi = row.get('rsi', 50)
        macd = row.get('macd', 0)
        macd_signal = row.get('macd_signal', 0)
        macd_hist = row.get('macd_hist', 0)
        vol = row.get('volume', 0)
        vol_sma20 = row.get('vol_sma20', vol)
        bb_low = row.get('bb_low', close_price * 0.95)
        bb_high = row.get('bb_high', close_price * 1.05)
        bb_mid = row.get('bb_mid', close_price)
        adx = row.get('adx', 20)

        # Kiểm tra market regime nếu có
        is_market_bull = True
        if market_regime is not None and not market_regime.empty:
            date_key = str(row.name) if not isinstance(row.name, int) else None
            if date_key and date_key in market_regime.index:
                is_market_bull = bool(market_regime.loc[date_key])
            elif 'time' in df.columns:
                t_str = pd.to_datetime(row['time']).strftime('%Y-%m-%d')
                if t_str in market_regime.index:
                    is_market_bull = bool(market_regime.loc[t_str])

        # Phân tích theo từng chiến lược
        if strategy_type == 'trend':
            # Trend Following: Giá > EMA20 > EMA50, MACD > Signal, RSI 50-70, ADX > 20
            bullish_count = 0
            
            if close_price > ema20 and ema20 >= ema50:
                bullish_count += 2
                reason_list.append("Giá trên EMA20 và EMA50")
            elif close_price > ema20:
                bullish_count += 1
                reason_list.append("Giá trên EMA20")
                
            if macd > macd_signal and macd_hist > 0:
                bullish_count += 2
                reason_list.append("MACD cắt lên Signal")
                
            if 50 < rsi < 70:
                bullish_count += 1
                reason_list.append(f"RSI thuận lợi ({rsi:.1f})")
                
            if vol > vol_sma20:
                bullish_count += 1
                reason_list.append("Khối lượng trên TB 20 phiên")
                
            if adx > 22:
                bullish_count += 1
                reason_list.append(f"Xu hướng mạnh (ADX {adx:.1f})")

            # MTF check
            if use_mtf and close_price > ema50:
                bullish_count += 1

            if is_market_bull:
                bullish_count += 1
            else:
                bullish_count -= 2  # Phạt điểm nếu thị trường chung downtrend

            score = min(100.0, max(0.0, 30.0 + bullish_count * 8.0))

            if score >= 75 and is_market_bull:
                signal = 'Buy'
                reasons[i] = "Xu hướng tăng mạnh: " + ", ".join(reason_list)
            elif score <= 35 or close_price < ema50:
                signal = 'Sell'
                reasons[i] = "Xu hướng suy yếu: Giá gãy hỗ trợ EMA hoặc áp lực bán lớn"
            else:
                signal = 'Hold'
                reasons[i] = "Đi ngang tích lũy hoặc chờ tín hiệu xác nhận"

        elif strategy_type == 'momentum':
            # Momentum Breakout: Giá vượt BB High hoặc đỉnh gần nhất kèm Vol lớn
            is_breakout = (close_price >= bb_high) or (close_price > ema20 and macd_hist > 0)
            vol_surge = vol > 1.3 * vol_sma20 if vol_sma20 > 0 else False

            if is_breakout and vol_surge and 55 <= rsi <= 75:
                signal = 'Buy'
                score = 85.0
                reasons[i] = f"Bùng nổ xung lực: Vượt biên trên BB kèm vol tăng {(vol/vol_sma20 if vol_sma20 else 1):.1f}x"
            elif rsi > 78 or close_price < bb_mid:
                signal = 'Sell'
                score = 30.0
                reasons[i] = "Quá mua hoặc rơi khỏi đường trung bình Bollinger"
            else:
                signal = 'Hold'
                score = 50.0
                reasons[i] = "Chưa có bùng nổ khối lượng hoặc giá chưa bứt phá"

        elif strategy_type == 'mean_reversion':
            # Mean Reversion: Quá bán chạm BB Low đảo chiều
            is_oversold = (rsi < 35) or (close_price <= bb_low)
            reversal_sign = macd_hist > df.iloc[max(0, i-1)].get('macd_hist', 0) if i > 0 else False

            if is_oversold and reversal_sign:
                signal = 'Buy'
                score = 80.0
                reasons[i] = f"Bắt đáy quá bán: RSI {rsi:.1f}, giá chạm cận dưới BB và chớm phục hồi"
            elif rsi > 65 or close_price >= bb_high:
                signal = 'Sell'
                score = 35.0
                reasons[i] = "Đạt mục tiêu chốt lời ngắn hạn (chạm biên trên BB)"
            else:
                signal = 'Hold'
                score = 50.0
                reasons[i] = "Giá dao động quanh biên bình thường"

        signals[i] = signal
        scores[i] = round(score, 1)
        if signal == 'Buy' and not reasons[i]:
            reasons[i] = "Thỏa mãn tiêu chí MUA theo chiến lược " + strategy_type

    df['signal'] = signals
    df['score'] = scores
    df['reason'] = reasons

    return df
