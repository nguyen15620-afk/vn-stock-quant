import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from strategy import compute_indicators, generate_signals
from backtester import run_backtest

def test_backtest_execution_no_lookahead():
    """
    Kiểm tra mô phỏng giao dịch đảm bảo:
    1. Tín hiệu ở nến T chỉ khớp tại giá Open của nến T+1
    2. Chi phí giao dịch và thuế được khấu trừ chính xác
    3. Không khớp lệnh khi nến tín hiệu vừa xuất hiện
    """
    dates = pd.date_range(end=datetime.now(), periods=10, freq='D')
    # Giả lập chuỗi giá có 1 chu kỳ Buy -> Sell rõ rệt
    df = pd.DataFrame({
        'time': dates,
        'open': [10.0, 10.5, 11.0, 11.5, 12.0, 12.5, 12.0, 11.5, 11.0, 10.5],
        'high': [10.5, 11.0, 11.5, 12.0, 12.5, 13.0, 12.5, 12.0, 11.5, 11.0],
        'low': [9.5, 10.0, 10.5, 11.0, 11.5, 12.0, 11.5, 11.0, 10.5, 10.0],
        'close': [10.2, 10.8, 11.2, 11.8, 12.2, 12.8, 12.1, 11.4, 10.8, 10.4],
        'volume': [100_000] * 10,
        # Tín hiệu: Buy ở nến index 1 -> Khớp tại Open nến index 2 (11.0)
        # Sell ở nến index 5 -> Khớp tại Open nến index 6 (12.0)
        'signal': ['Hold', 'Buy', 'Hold', 'Hold', 'Hold', 'Sell', 'Hold', 'Hold', 'Hold', 'Hold']
    })

    initial_capital = 100_000_000.0
    res = run_backtest(df, initial_capital=initial_capital, buy_fee=0.0015, sell_fee_tax=0.0025)

    assert res['total_trades'] >= 1
    trade = res['trades'][0]
    # Khớp tại Open nến index 2
    assert trade['entry_price'] == 11.0
    # Khớp bán tại Open nến index 6
    assert trade['exit_price'] == 12.0
    # Net PnL phải tính chi phí: giá tăng từ 11 lên 12 (gross ~9%), sau thuế phí vẫn dương
    assert trade['net_pnl'] > 0
    assert res['win_rate_pct'] == 100.0

def test_backtest_empty_data():
    """Kiểm tra phản hồi an toàn khi truyền DataFrame rỗng"""
    res = run_backtest(pd.DataFrame())
    assert res['total_trades'] == 0
    assert res['final_equity'] == 100_000_000.0

def test_backtest_losing_trade():
    """Kiểm tra mô phỏng lệnh lỗ, tính toán Drawdown và tỷ lệ Thua"""
    dates = pd.date_range(end=datetime.now(), periods=10, freq='D')
    df = pd.DataFrame({
        'time': dates,
        'open': [20.0, 20.0, 20.0, 19.0, 18.0, 16.0, 15.0, 15.0, 15.0, 15.0],
        'high': [20.5, 20.5, 20.0, 19.5, 18.5, 16.5, 15.5, 15.5, 15.5, 15.5],
        'low': [19.5, 19.5, 19.0, 18.0, 17.0, 15.5, 14.5, 14.5, 14.5, 14.5],
        'close': [20.0, 20.0, 19.5, 18.5, 17.5, 16.0, 15.0, 15.0, 15.0, 15.0],
        'volume': [100_000] * 10,
        # Buy tại nến 1 -> Khớp Open nến 2 (20.0), Sell tại nến 4 -> Khớp Open nến 5 (18.0)
        'signal': ['Hold', 'Buy', 'Hold', 'Hold', 'Sell', 'Hold', 'Hold', 'Hold', 'Hold', 'Hold']
    })
    res = run_backtest(df, initial_capital=100_000_000.0)
    assert res['total_trades'] == 1
    assert res['losing_trades'] == 1
    assert res['winning_trades'] == 0
    assert res['win_rate_pct'] == 0.0
    assert res['trades'][0]['net_pnl'] < 0
    assert res['max_drawdown_pct'] > 0

def test_backtest_consecutive_buy_signals():
    """Kiểm tra không mua trùng lặp khi đã full vị thế và có chuỗi tín hiệu Buy liên tiếp"""
    dates = pd.date_range(end=datetime.now(), periods=6, freq='D')
    df = pd.DataFrame({
        'time': dates,
        'open': [10.0, 10.0, 10.0, 11.0, 12.0, 12.0],
        'high': [10.5, 10.5, 10.5, 11.5, 12.5, 12.5],
        'low': [9.5, 9.5, 9.5, 10.5, 11.5, 11.5],
        'close': [10.0, 10.0, 10.5, 11.5, 12.0, 12.0],
        'volume': [100_000] * 6,
        'signal': ['Buy', 'Buy', 'Buy', 'Hold', 'Sell', 'Hold']
    })
    res = run_backtest(df, initial_capital=100_000_000.0)
    # Chỉ mở 1 vị thế duy nhất và đóng khi có Sell
    assert res['total_trades'] == 1

