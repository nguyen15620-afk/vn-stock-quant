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

    # 6. Volume + SMA Volume 9
    df['vol_sma9'] = df['volume'].rolling(window=9).mean()
    
    return df

def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applies the custom Buy/Sell/Hold rule engine.
    """
    df = df.copy()
    
    # Initialize columns
    df['signal'] = 'Hold'
    df['reason'] = ''

    # Ensure we have enough data (shift requires previous rows)
    if len(df) < 2:
        return df

    # Helper conditions
    # Price > middle BB
    cond_price_above_bb = df['close'] > df['bb_mid']
    cond_price_below_bb = df['close'] < df['bb_mid']
    
    # RSI > 50 đang tăng (RSI current > 50 AND RSI current > RSI previous)
    cond_rsi_above_50 = df['rsi'] > 50
    cond_rsi_rising = df['rsi'] > df['rsi'].shift(1)
    cond_rsi_buy = cond_rsi_above_50 & cond_rsi_rising
    
    # RSI < 50
    cond_rsi_below_50 = df['rsi'] < 50
    
    # MACD hist > 0 / < 0
    cond_macd_hist_pos = df['macd_hist'] > 0
    cond_macd_hist_neg = df['macd_hist'] < 0
    
    # StochRSI cắt lên từ dưới 20 
    # Current K > D (or current K > 20 and previous K < 20) -> typically crossover means K crosses D.
    # The prompt says: "StochRSI cắt lên từ dưới 20" -> Previous K < 20 and Current K > Previous K, or K crosses D below 20.
    # Let's interpret as K crosses D below 20, or K crosses above 20. 
    # I'll implement: Previous K < 20 AND Current K crosses above Current D
    prev_k = df['stoch_rsi_k'].shift(1)
    prev_d = df['stoch_rsi_d'].shift(1)
    curr_k = df['stoch_rsi_k']
    curr_d = df['stoch_rsi_d']
    
    # K crosses above D, while happening below 20
    cond_stoch_cross_up = (prev_k <= prev_d) & (curr_k > curr_d) & (curr_k < 20)
    
    # StochRSI cắt xuống từ trên 80
    cond_stoch_cross_down = (prev_k >= prev_d) & (curr_k < curr_d) & (curr_k > 80)
    
    # Volume > SMA9
    cond_vol_above_sma = df['volume'] > df['vol_sma9']

    # BUY Logic
    buy_mask = (
        cond_price_above_bb & 
        cond_rsi_buy & 
        cond_macd_hist_pos & 
        cond_stoch_cross_up & 
        cond_vol_above_sma
    )
    
    # SELL Logic
    sell_mask = (
        cond_price_below_bb & 
        cond_rsi_below_50 & 
        cond_macd_hist_neg & 
        cond_stoch_cross_down
    )

    df.loc[buy_mask, 'signal'] = 'Buy'
    df.loc[buy_mask, 'reason'] = 'Giá > BB_mid, RSI > 50 & Tăng, MACD_hist > 0, StochRSI cắt lên < 20, Vol > SMA9'
    
    df.loc[sell_mask, 'signal'] = 'Sell'
    df.loc[sell_mask, 'reason'] = 'Giá < BB_mid, RSI < 50, MACD_hist < 0, StochRSI cắt xuống > 80'

    return df
