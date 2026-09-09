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
    Applies the Strategy 1: Trend Following logic.
    """
    df = df.copy()
    
    # Initialize columns
    df['signal'] = 'Hold'
    df['reason'] = ''

    # Ensure we have enough data
    if len(df) < 2:
        return df

    # --- BUY CONDITIONS ---
    # 1. Giá > SMA20 (BB Mid)
    cond_price_above_bb = df['close'] > df['bb_mid']
    # 2. MACD Hist > 0
    cond_macd_hist_pos = df['macd_hist'] > 0
    # 3. Volume > SMA20
    cond_vol_above_sma20 = df['volume'] > df['vol_sma20']
    # 4. RSI > 50
    cond_rsi_above_50 = df['rsi'] > 50

    buy_mask = (
        cond_price_above_bb & 
        cond_macd_hist_pos & 
        cond_vol_above_sma20 & 
        cond_rsi_above_50
    )
    
    # --- SELL CONDITIONS ---
    # 1. Giá < SMA20 (BB Mid)
    cond_price_below_bb = df['close'] < df['bb_mid']
    # 2. MACD Hist < 0
    cond_macd_hist_neg = df['macd_hist'] < 0

    sell_mask = (
        cond_price_below_bb | 
        cond_macd_hist_neg
    )

    df.loc[buy_mask, 'signal'] = 'Buy'
    df.loc[buy_mask, 'reason'] = 'Giá > SMA20, MACD_hist > 0, RSI > 50, Vol > SMA20'
    
    df.loc[sell_mask, 'signal'] = 'Sell'
    df.loc[sell_mask, 'reason'] = 'Giá thủng SMA20 HOẶC MACD_hist < 0'

    return df
