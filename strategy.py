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

    # 4. RSI (14)
    df['rsi'] = ta.momentum.rsi(close=df['close'], window=14)
    df['rsi_sma14'] = df['rsi'].rolling(window=14).mean()

    # 5. Stochastic RSI (14, 14, 3, 3)
    df['stoch_rsi'] = ta.momentum.stochrsi(close=df['close'], window=14) * 100
    df['stoch_rsi_k'] = df['stoch_rsi'].rolling(window=3).mean()
    df['stoch_rsi_d'] = df['stoch_rsi_k'].rolling(window=3).mean()

    # 6. Volume
    df['vol_sma9'] = df['volume'].rolling(window=9).mean()
    df['vol_sma20'] = df['volume'].rolling(window=20).mean()
    
    # 7. EMAs for Momentum Strategy
    df['ema5'] = ta.trend.ema_indicator(close=df['close'], window=5)
    df['ema20'] = ta.trend.ema_indicator(close=df['close'], window=20)
    
    # 8. ADX
    adx = ta.trend.ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14)
    df['adx'] = adx.adx()
    
    # 9. Donchian Channels (For Turtle Trading)
    df['roll_high_20'] = df['high'].rolling(window=20).max()
    df['roll_low_10'] = df['low'].rolling(window=10).min()
    
    return df

def generate_signals(df: pd.DataFrame, strategy_type: str = 'trend', market_regime: pd.Series = None) -> pd.DataFrame:
    """
    Generates Buy/Sell/Hold signals based on the selected strategy.
    Strategies: 'trend' (Breakout/Trend Following), 'momentum' (Fast EMA), 'mean_reversion' (Bottom Fishing), 'turtle' (Turtle Trading), 'ichimoku' (Cloud Breakout).
    """
    df = df.copy()
    
    df['signal'] = 'Hold'
    df['reason'] = ''
    df['score'] = 0
    df['trend_status'] = 'Trung lập'

    if len(df) < 2:
        return df

    prev_close = df['close'].shift(1)
    prev_bb_mid = df['bb_mid'].shift(1)
    
    # --- Strategy: Trend Following (Default) ---
    if strategy_type == 'trend':
        cond_price_above_bb = (df['close'] > df['bb_mid']).astype(int)
        cond_macd_hist_pos = (df['macd_hist'] > 0).astype(int)
        cond_rsi_above_50 = (df['rsi'] > 50).astype(int)
        cond_vol_above_sma20 = (df['volume'] > df['vol_sma20']).astype(int)

        df['score'] = (cond_price_above_bb * 25) + (cond_macd_hist_pos * 25) + (cond_rsi_above_50 * 25) + (cond_vol_above_sma20 * 25)
        
        df.loc[df['score'] >= 75, 'trend_status'] = 'Tích cực (Uptrend)'
        df.loc[df['score'] <= 25, 'trend_status'] = 'Tiêu cực (Downtrend)'
        df.loc[(df['score'] == 50) & (df['close'] > df['bb_mid']), 'trend_status'] = 'Trung lập (Nghiêng Tăng)'
        df.loc[(df['score'] == 50) & (df['close'] <= df['bb_mid']), 'trend_status'] = 'Trung lập (Nghiêng Giảm)'

        prev_score = df['score'].shift(1)
        
        buy_mask = (df['score'] >= 75) & (prev_score < 75)
        sell_mask = ((df['score'] <= 25) & (prev_score > 25)) | ((df['close'] < df['bb_mid']) & (prev_close >= prev_bb_mid))
        
        df.loc[buy_mask, 'signal'] = 'Buy'
        df.loc[buy_mask, 'reason'] = 'Bùng nổ! Xu hướng Tăng xác nhận.'
        df.loc[sell_mask, 'signal'] = 'Sell'
        df.loc[sell_mask, 'reason'] = 'Cảnh báo! Thủng hỗ trợ hoặc Suy yếu.'

    # --- Strategy: Momentum (Fast EMA) ---
    elif strategy_type == 'momentum':
        df['score'] = np.where(df['ema5'] > df['ema20'], 100, 0)
        df['trend_status'] = np.where(df['score'] == 100, 'Tích cực (Uptrend nhanh)', 'Tiêu cực (Downtrend)')
        
        buy_mask = (df['ema5'] > df['ema20']) & (df['ema5'].shift(1) <= df['ema20'].shift(1))
        sell_mask = (df['ema5'] < df['ema20']) & (df['ema5'].shift(1) >= df['ema20'].shift(1))
        
        df.loc[buy_mask, 'signal'] = 'Buy'
        df.loc[buy_mask, 'reason'] = 'Giao cắt EMA (Mua)'
        df.loc[sell_mask, 'signal'] = 'Sell'
        df.loc[sell_mask, 'reason'] = 'Giao cắt EMA (Bán)'

    # --- Strategy: Mean Reversion (Bottom Fishing) ---
    elif strategy_type == 'mean_reversion':
        df['score'] = np.where(df['rsi'] < 30, 100, np.where(df['rsi'] > 70, 0, 50))
        df['trend_status'] = np.where(df['rsi'] < 30, 'Quá bán (Hấp dẫn)', np.where(df['rsi'] > 70, 'Quá mua (Rủi ro)', 'Trung lập'))
        
        buy_mask = ((df['rsi'] < 30) & (df['rsi'].shift(1) >= 30)) | ((df['close'] < df['bb_low']) & (prev_close >= df['bb_low'].shift(1)))
        sell_mask = ((df['rsi'] > 70) & (df['rsi'].shift(1) <= 70)) | ((df['close'] > df['bb_mid']) & (prev_close <= prev_bb_mid))
        
        df.loc[buy_mask, 'signal'] = 'Buy'
        df.loc[buy_mask, 'reason'] = 'Bắt đáy! Cổ phiếu rơi vào vùng Quá bán.'
        df.loc[sell_mask, 'signal'] = 'Sell'
        df.loc[sell_mask, 'reason'] = 'Chốt lời/Cắt lỗ! Chạm ngưỡng cản hoặc Quá mua.'

    # --- Strategy: Turtle Trading (Đột phá đỉnh 20 ngày) ---
    elif strategy_type == 'turtle':
        df['score'] = np.where(df['close'] >= df['roll_high_20'].shift(1), 100, np.where(df['close'] <= df['roll_low_10'].shift(1), 0, 50))
        df['trend_status'] = np.where(df['score'] == 100, 'Tích cực (Vượt đỉnh)', np.where(df['score'] == 0, 'Tiêu cực (Thủng đáy)', 'Trung lập'))
        
        buy_mask = (df['close'] > df['roll_high_20'].shift(1)) & (prev_close <= df['roll_high_20'].shift(2))
        sell_mask = (df['close'] < df['roll_low_10'].shift(1)) & (prev_close >= df['roll_low_10'].shift(2))
        
        df.loc[buy_mask, 'signal'] = 'Buy'
        df.loc[buy_mask, 'reason'] = 'Turtle: Phá đỉnh 20 ngày'
        df.loc[sell_mask, 'signal'] = 'Sell'
        df.loc[sell_mask, 'reason'] = 'Turtle: Thủng đáy 10 ngày'

    # --- Strategy: Ichimoku Kumo Breakout ---
    elif strategy_type == 'ichimoku':
        # Xác định mây
        cloud_top = np.maximum(df['ichi_senkou_a'], df['ichi_senkou_b'])
        cloud_bottom = np.minimum(df['ichi_senkou_a'], df['ichi_senkou_b'])
        
        df['score'] = np.where(df['close'] > cloud_top, 100, np.where(df['close'] < cloud_bottom, 0, 50))
        df['trend_status'] = np.where(df['score'] == 100, 'Tích cực (Trên Mây)', np.where(df['score'] == 0, 'Tiêu cực (Dưới Mây)', 'Trung lập (Trong Mây)'))
        
        prev_cloud_top = cloud_top.shift(1)
        prev_cloud_bottom = cloud_bottom.shift(1)
        
        buy_mask = (df['close'] > cloud_top) & (prev_close <= prev_cloud_top)
        sell_mask = (df['close'] < cloud_bottom) & (prev_close >= prev_cloud_bottom)
        
        df.loc[buy_mask, 'signal'] = 'Buy'
        df.loc[buy_mask, 'reason'] = 'Ichimoku: Giá đâm xuyên Mây đi lên'
        df.loc[sell_mask, 'signal'] = 'Sell'
        df.loc[sell_mask, 'reason'] = 'Ichimoku: Giá rớt khỏi Mây Kumo'

    # --- Tùy chọn Phòng thủ Thị trường Chung ---
    if market_regime is not None:
        # Hủy các lệnh Buy nếu market_regime == False (Thị trường chung xấu)
        # Giữ nguyên các lệnh Sell vì vẫn cần cắt lỗ/chốt lời
        blocked_buys = df['signal'] == 'Buy'
        # market_regime có thể là một Series bool có cùng index, map theo thời gian. 
        # Cần reindex để khớp với df và đưa về dạng bool
        market_regime_aligned = market_regime.reindex(df.index).fillna(False).astype(bool)
        
        # Chỉ giữ Buy khi market_regime_aligned == True
        df.loc[blocked_buys & (~market_regime_aligned), 'signal'] = 'Hold'
        df.loc[blocked_buys & (~market_regime_aligned), 'reason'] = 'Tín hiệu MUA bị HỦY do VNINDEX xấu'

    # Fallback for 'Hold' reason
    hold_mask = (df['signal'] == 'Hold') & (df['reason'] == '')
    df.loc[hold_mask, 'reason'] = df['trend_status']

    return df
