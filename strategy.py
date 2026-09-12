import pandas as pd
import ta

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates core technical indicators using the 'ta' library.
    Required inputs: 'open', 'high', 'low', 'close', 'volume'
    """
    if df.empty:
        return df

    df = df.copy()

    # 1. MACD (12, 26, 9)
    macd = ta.trend.MACD(close=df['close'], window_slow=26, window_fast=12, window_sign=9)
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_hist'] = macd.macd_diff()

    # 2. RSI (14)
    df['rsi'] = ta.momentum.rsi(close=df['close'], window=14)

    # 3. Volume
    df['vol_sma9'] = df['volume'].rolling(window=9).mean()
    df['vol_sma20'] = df['volume'].rolling(window=20).mean()
    
    return df
