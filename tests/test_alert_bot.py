import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from alert_bot import run_quant_scan

@patch("alert_bot.send_telegram_message")
@patch("alert_bot.load_fundamentals")
@patch("alert_bot.load_historical_data")
def test_run_quant_scan_no_signals(mock_load_hist, mock_load_fa, mock_send):
    """Kiểm tra kịch bản quét không tìm thấy mã nào đạt điều kiện MUA"""
    mock_load_hist.return_value = pd.DataFrame()
    mock_load_fa.return_value = {"PE": 30.0, "ROE": 0.05} # FA không đạt chuẩn
    
    run_quant_scan()
    
    mock_send.assert_called_once()
    sent_text = mock_send.call_args[0][0]
    assert "BÁO CÁO QUANT TRƯỚC PHIÊN ATC" in sent_text
    assert "Không có mã VN30 nào đạt tiêu chuẩn MUA" in sent_text

@patch("alert_bot.send_telegram_message")
@patch("alert_bot.load_fundamentals")
@patch("alert_bot.load_historical_data")
@patch("alert_bot.VN30", ["FPT"])
def test_run_quant_scan_with_buy_signal(mock_load_hist, mock_load_fa, mock_send):
    """Kiểm tra kịch bản quét tìm thấy mã đạt chuẩn cơ bản và sinh tín hiệu MUA"""
    mock_load_fa.return_value = {"PE": 15.0, "ROE": 0.25} # FA đạt chuẩn
    
    # Giả lập nến lịch sử cho VNINDEX và FPT
    dates = pd.date_range("2026-01-01", periods=60, freq="D")
    df_ohlcv = pd.DataFrame({
        "time": dates,
        "open": [100.0 + i for i in range(60)],
        "high": [102.0 + i for i in range(60)],
        "low": [99.0 + i for i in range(60)],
        "close": [101.0 + i for i in range(60)],
        "volume": [1_000_000 for _ in range(60)]
    })
    mock_load_hist.return_value = df_ohlcv
    
    with patch("alert_bot.generate_signals") as mock_gen_sig:
        df_sig = df_ohlcv.copy()
        df_sig["signal"] = "Buy"
        df_sig["score"] = 85
        df_sig["reason"] = "Xu hướng tăng mạnh, RSI ổn định"
        mock_gen_sig.return_value = df_sig
        
        run_quant_scan()
        
        mock_send.assert_called_once()
        sent_text = mock_send.call_args[0][0]
        assert "Phát hiện <b>1</b> mã đạt tiêu chuẩn MUA" in sent_text
        assert "FPT" in sent_text
        assert "Điểm s/mạnh: 85/100" in sent_text
