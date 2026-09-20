import os
import pytest
from unittest.mock import patch, MagicMock
import requests
from notifier import send_telegram_message, send_telegram_alert

def test_send_telegram_message_missing_credentials(monkeypatch):
    """Kiểm tra xử lý an toàn khi thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID"""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    
    res = send_telegram_message("Test message")
    assert res is False

def test_send_telegram_message_placeholder_credentials(monkeypatch):
    """Kiểm tra xử lý khi biến môi trường vẫn là placeholder mặc định"""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456789")
    
    res = send_telegram_message("Test message")
    assert res is False

@patch("notifier.requests.post")
def test_send_telegram_message_success(mock_post, monkeypatch):
    """Kiểm tra gửi tin nhắn thành công qua HTTP POST"""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake_bot_token_123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response
    
    res = send_telegram_message("<b>Hello World</b>")
    assert res is True
    
    # Kiểm tra payload
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert "https://api.telegram.org/botfake_bot_token_123/sendMessage" in args[0]
    assert kwargs["json"]["chat_id"] == "987654321"
    assert kwargs["json"]["text"] == "<b>Hello World</b>"
    assert kwargs["json"]["parse_mode"] == "HTML"

@patch("notifier.requests.post")
def test_send_telegram_message_network_error(mock_post, monkeypatch):
    """Kiểm tra xử lý lỗi khi mạng hoặc API Telegram gặp sự cố"""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake_bot_token_123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")
    
    mock_post.side_effect = requests.RequestException("Connection timeout")
    
    res = send_telegram_message("Test message")
    assert res is False

@patch("notifier.send_telegram_message")
def test_send_telegram_alert(mock_send):
    """Kiểm tra định dạng tin nhắn cảnh báo tín hiệu giao dịch"""
    mock_send.return_value = True
    
    res = send_telegram_alert("FPT", "MUA", "Vượt đỉnh 52 tuần với thanh khoản lớn")
    assert res is True
    
    mock_send.assert_called_once()
    sent_text = mock_send.call_args[0][0]
    assert "TÍN HIỆU MUA - FPT" in sent_text
    assert "Vượt đỉnh 52 tuần với thanh khoản lớn" in sent_text
