import pandas as pd
import numpy as np
import ta

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates technical indicators using the 'ta' library.
    Required inputs: 'open', 'high', 'low', 'close', 'volume'
    """
    if df.empty:
        return df

    df = df.copy()

    # 1. Bollinger Bands (20, 2)
    bb = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
    df['bb_mid'] = bb.bollinger_mavg()
    df['bb_up'] = bb.bollinger_hband()
    df['bb_low'] = bb.bollinger_lband()

    # 2. Ichimoku Cloud (9, 26, 52, 26)
    ichimoku = ta.trend.IchimokuIndicator(
        high=df['high'], low=df['low'], 
        window1=9, window2=26, window3=52, visual=False
    )
    df['ichi_tenkan'] = ichimoku.ichimoku_conversion_line()
    df['ichi_kijun'] = ichimoku.ichimoku_base_line()
    df['ichi_senkou_a'] = ichimoku.ichimoku_a()
    df['ichi_senkou_b'] = ichimoku.ichimoku_b()

    # 3. MACD (12, 26, 9)
    macd = ta.trend.MACD(close=df['close'], window_slow=26, window_fast=12, window_sign=9)
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_hist'] = macd.macd_diff()

    # 4. RSI (14) + SMA 14 of RSI
    df['rsi'] = ta.momentum.rsi(close=df['close'], window=14)
    df['rsi_sma14'] = df['rsi'].rolling(window=14).mean()

    # 5. Stochastic RSI (14, 14, 3, 3)
    # The StochRSI implementation in 'ta' calculates the base stochrsi. 
    # To get %K and %D (smoothed), we apply rolling mean (SMA).
    # Default formula: StochRSI is (RSI - min(RSI)) / (max(RSI) - min(RSI))
    df['stoch_rsi'] = ta.momentum.stochrsi(close=df['close'], window=14) * 100
    df['stoch_rsi_k'] = df['stoch_rsi'].rolling(window=3).mean()
    df['stoch_rsi_d'] = df['stoch_rsi_k'].rolling(window=3).mean()

    # 6. Volume + SMA Volume 20 (for Strategy 1)
    df['vol_sma9'] = df['volume'].rolling(window=9).mean()
    df['vol_sma20'] = df['volume'].rolling(window=20).mean()
    
    return df

def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applies Strategy 1 using a 0-100 Power Score System.
    """
    df = df.copy()
    
    # Initialize columns
    df['signal'] = 'Hold'
    df['reason'] = ''
    df['score'] = 0
    df['trend_status'] = 'Trung lập'

    # Ensure we have enough data
    if len(df) < 2:
        return df

    # --- SCORE CALCULATION (0 - 100) ---
    cond_price_above_bb = (df['close'] > df['bb_mid']).astype(int)
    cond_macd_hist_pos = (df['macd_hist'] > 0).astype(int)
    cond_rsi_above_50 = (df['rsi'] > 50).astype(int)
    cond_vol_above_sma20 = (df['volume'] > df['vol_sma20']).astype(int)

    df['score'] = (cond_price_above_bb * 25) + (cond_macd_hist_pos * 25) + (cond_rsi_above_50 * 25) + (cond_vol_above_sma20 * 25)
    
    # --- TREND STATUS ---
    df.loc[df['score'] >= 75, 'trend_status'] = 'Tích cực (Uptrend)'
    df.loc[df['score'] <= 25, 'trend_status'] = 'Tiêu cực (Downtrend)'
    df.loc[(df['score'] == 50) & (df['close'] > df['bb_mid']), 'trend_status'] = 'Trung lập (Nghiêng Tăng)'
    df.loc[(df['score'] == 50) & (df['close'] <= df['bb_mid']), 'trend_status'] = 'Trung lập (Nghiêng Giảm)'

    # --- BUY / SELL TRIGGERS ---
    prev_score = df['score'].shift(1)
    prev_close = df['close'].shift(1)
    prev_bb_mid = df['bb_mid'].shift(1)
    
    # Điểm MUA mới: Điểm sức mạnh đạt 75 trở lên (hôm trước chưa đạt) 
    # HOẶC giá cắt lên SMA20 đi kèm khối lượng lớn (Score nhảy lên >= 50 từ mức thấp)
    buy_mask = (df['score'] >= 75) & (prev_score < 75)
    
    # Điểm BÁN mới: Điểm sức mạnh rớt xuống <= 25 
    # HOẶC Giá thủng SMA20 (rất quan trọng để phòng thủ)
    sell_mask = ((df['score'] <= 25) & (prev_score > 25)) | ((df['close'] < df['bb_mid']) & (prev_close >= prev_bb_mid))

    df.loc[buy_mask, 'signal'] = 'Buy'
    df.loc[buy_mask, 'reason'] = 'Bùng nổ! Điểm MUA xuất hiện'
    
    df.loc[sell_mask, 'signal'] = 'Sell'
    df.loc[sell_mask, 'reason'] = 'Cảnh báo! Thủng hỗ trợ hoặc Suy yếu'
    
    # Dành cho những ngày không có trigger (Hold)
    hold_mask = (~buy_mask) & (~sell_mask)
    df.loc[hold_mask, 'reason'] = df['trend_status']

    return df
