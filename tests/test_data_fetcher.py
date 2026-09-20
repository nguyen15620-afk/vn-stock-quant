import pytest
import pandas as pd
import re
from unittest.mock import patch, MagicMock
from data_fetcher import get_fundamental_data, get_macro_flow, get_latest_news, is_ticker_in_news

def test_ticker_regex_boundary():
    """Kiểm tra is_ticker_in_news lọc đúng ticker, tránh false positive (như 'tỷ VND', 'giá bid')"""
    # Test case với VND
    assert not is_ticker_in_news("VND", "Lợi nhuận đạt 500 tỷ VND trong quý 2")
    assert not is_ticker_in_news("VND", "Doanh thu 1,200 VND mỗi cổ phiếu")
    assert not is_ticker_in_news("VND", "Tỷ giá USD/VND hạ nhiệt phiên cuối tuần")
    assert is_ticker_in_news("VND", "Cổ phiếu VND ghi nhận dòng tiền khối ngoại mua ròng")
    assert is_ticker_in_news("VND", "VND: Khuyến nghị MUA với giá mục tiêu 25,000")
    
    # Test case với BID
    assert not is_ticker_in_news("BID", "Chênh lệch giá bid và ask nới rộng trên thị trường phái sinh")
    assert is_ticker_in_news("BID", "Cổ phiếu BID của BIDV dẫn dắt nhóm ngân hàng")


@patch("data_fetcher.load_fundamentals")
def test_get_fundamental_data_yahoo_success(mock_load_fa):
    """Kiểm tra chuẩn hóa dữ liệu tài chính từ Yahoo Finance"""
    mock_load_fa.return_value = {
        "PE": 14.5,
        "PB": 2.1,
        "ROE": 0.22,
        "EPS": 6500,
        "RevenueGrowth": 0.18,
        "GrossMargins": 0.35,
        "MarketCap": 150000000000000
    }
    
    data = get_fundamental_data("FPT")
    assert data["Mã CP"] == "FPT"
    assert data["P/E"] == 14.5
    assert data["P/B"] == 2.1
    assert "22.0%" in data["ROE"]
    assert "6,500 VND" in data["EPS"]
    assert "Yahoo Finance" in data["Nguồn dữ liệu"]

@patch("data_fetcher.load_fundamentals")
def test_get_fundamental_data_fallback(mock_load_fa, monkeypatch):
    """Kiểm tra fallback tầng 3 khi không có dữ liệu tài chính từ API"""
    mock_load_fa.return_value = None
    monkeypatch.setattr("data_fetcher.VNSTOCK_AVAILABLE", False)
    
    data = get_fundamental_data("UNKNOWN_TICKER")
    assert data["Mã CP"] == "UNKNOWN_TICKER"
    assert "Lưu ý phân tích" in data
    assert "Định giá P/E & P/B" in data

@patch("data_fetcher.load_historical_data")
def test_get_macro_flow_with_data(mock_load_data):
    """Kiểm tra tổng hợp xu hướng vĩ mô khi có dữ liệu VNINDEX"""
    dates = pd.date_range("2026-01-01", periods=10, freq="D")
    df_fake = pd.DataFrame({
        "time": dates,
        "open": [1200 + i for i in range(10)],
        "high": [1205 + i for i in range(10)],
        "low": [1195 + i for i in range(10)],
        "close": [1200 + i * 2 for i in range(10)],
        "volume": [500_000_000 for _ in range(10)]
    })
    mock_load_data.return_value = df_fake
    
    summary = get_macro_flow()
    assert "VN-INDEX" in summary
    assert "Xu hướng" in summary
    assert "Thanh khoản" in summary

@patch("data_fetcher.load_historical_data")
def test_get_macro_flow_empty_fallback(mock_load_data):
    """Kiểm tra fallback vĩ mô an toàn khi mất kết nối dữ liệu chỉ số"""
    mock_load_data.return_value = pd.DataFrame()
    
    summary = get_macro_flow()
    assert "VN-INDEX" in summary
    assert "tích lũy" in summary

@patch("data_fetcher.requests.get")
def test_get_latest_news_google_rss_success(mock_get):
    """Kiểm tra bóc tách tin tức RSS từ Google News"""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <title>Google News</title>
            <item>
                <title>FPT công bố kết quả kinh doanh tăng trưởng 20%</title>
                <pubDate>Fri, 15 Sep 2026 07:00:00 GMT</pubDate>
                <source>Vietstock</source>
            </item>
        </channel>
    </rss>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = xml_content.encode("utf-8")
    mock_get.return_value = mock_resp
    
    news = get_latest_news("FPT")
    assert "FPT công bố kết quả kinh doanh" in news
    assert "Vietstock" in news
