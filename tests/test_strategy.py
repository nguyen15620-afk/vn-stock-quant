import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from strategy import compute_indicators, generate_signals

@pytest.fixture
def sample_ohlcv():
    """Tạo DataFrame OHLCV giả lập gồm 60 phiên tăng trưởng có sóng"""
    dates = pd.date_range(end=datetime.now(), periods=60, freq='D')
    np.random.seed(42)
    base = 100.0
    returns = np.random.normal(0.002, 0.015, size=60)
    close = base * np.cumprod(1 + returns)
    high = close * (1 + np.abs(np.random.normal(0.005, 0.005, size=60)))
    low = close * (1 - np.abs(np.random.normal(0.005, 0.005, size=60)))
    open_p = (close + low) / 2
    volume = np.random.randint(100_000, 1_000_000, size=60)

    df = pd.DataFrame({
        'time': dates,
        'open': open_p,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    return df

def test_compute_indicators_columns(sample_ohlcv):
    """Kiểm tra tính toán đầy đủ các chỉ báo kỹ thuật"""
    df = compute_indicators(sample_ohlcv)
    expected_cols = [
        'macd', 'macd_signal', 'macd_hist', 'rsi',
        'vol_sma9', 'vol_sma20', 'ema20', 'ema50',
        'bb_mid', 'bb_high', 'bb_low',
        'ichimoku_tenkan', 'ichimoku_kijun', 'adx'
    ]
    for col in expected_cols:
        assert col in df.columns, f"Thiếu chỉ báo kỹ thuật: {col}"
    
    # Kiểm tra giá trị hợp lệ
    assert (df['rsi'].dropna() >= 0).all() and (df['rsi'].dropna() <= 100).all()
    assert (df['bb_high'].dropna() >= df['bb_low'].dropna()).all()

def test_generate_signals_trend(sample_ohlcv):
    """Kiểm tra sinh tín hiệu theo chiến lược Trend Following"""
    df_sig = generate_signals(sample_ohlcv, strategy_type='trend')
    assert 'signal' in df_sig.columns
    assert 'score' in df_sig.columns
    assert 'reason' in df_sig.columns
    assert set(df_sig['signal'].unique()).issubset({'Buy', 'Sell', 'Hold'})
    assert (df_sig['score'] >= 0).all() and (df_sig['score'] <= 100).all()

def test_generate_signals_momentum(sample_ohlcv):
    """Kiểm tra sinh tín hiệu theo chiến lược Momentum Breakout"""
    df_sig = generate_signals(sample_ohlcv, strategy_type='momentum')
    assert 'signal' in df_sig.columns
    assert set(df_sig['signal'].unique()).issubset({'Buy', 'Sell', 'Hold'})

def test_generate_signals_mean_reversion(sample_ohlcv):
    """Kiểm tra sinh tín hiệu theo chiến lược Mean Reversion"""
    df_sig = generate_signals(sample_ohlcv, strategy_type='mean_reversion')
    assert 'signal' in df_sig.columns
    assert set(df_sig['signal'].unique()).issubset({'Buy', 'Sell', 'Hold'})

def test_compute_indicators_short_data():
    """Kiểm tra tính toán chỉ báo an toàn với dữ liệu ngắn (< 5 nến và < 26 nến)"""
    dates = pd.date_range(end=datetime.now(), periods=3, freq='D')
    df_short = pd.DataFrame({
        'time': dates,
        'open': [10.0, 10.5, 11.0],
        'high': [10.5, 11.0, 11.5],
        'low': [9.5, 10.0, 10.5],
        'close': [10.2, 10.8, 11.2],
        'volume': [1000, 2000, 3000]
    })
    # < 5 nến trả về nguyên vẹn
    res = compute_indicators(df_short)
    assert len(res) == 3

def test_generate_signals_with_market_regime_and_mtf(sample_ohlcv):
    """Kiểm tra sinh tín hiệu khi tích hợp Market Regime và Đa khung thời gian (MTF)"""
    sample_ohlcv['date_str'] = sample_ohlcv['time'].dt.strftime('%Y-%m-%d')
    sample_ohlcv.set_index('date_str', inplace=True, drop=False)
    
    # Giả lập VNINDEX Uptrend
    regime = pd.Series(True, index=sample_ohlcv.index)
    df_sig = generate_signals(sample_ohlcv, strategy_type='trend', market_regime=regime, use_mtf=True)
    assert 'signal' in df_sig.columns
    assert 'score' in df_sig.columns

