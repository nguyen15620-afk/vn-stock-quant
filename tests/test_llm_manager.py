import os
import time
import asyncio
import pytest
from llm_manager import (
    DEFAULT_SUBAGENT_CASCADE,
    DEFAULT_MASTER_CASCADE,
    get_limiter_for_model,
    mark_model_cooldown,
    is_model_available,
    get_cascade_models,
    configure_llm,
    _model_cooldowns
)

def test_default_cascades_structure():
    """Kiểm tra cấu trúc cascade mặc định phân tách giữa Sub-Agents và Master Agent"""
    # Sub-agents dùng các bản Flash-Lite (500 RPD)
    assert len(DEFAULT_SUBAGENT_CASCADE) >= 2
    assert "gemini-3.5-flash-lite" in DEFAULT_SUBAGENT_CASCADE

    # Master Agent ưu tiên flagship 3.6-flash và có chốt chặn cuối là lite
    assert DEFAULT_MASTER_CASCADE[0] == "gemini-3.6-flash"
    assert DEFAULT_MASTER_CASCADE[-1] == "gemini-3.5-flash-lite"

def test_get_limiter_for_model():
    """Kiểm tra Rate Limiter: 15 RPM cho Lite models và 5 RPM cho Flash models"""
    async def _check():
        lite_limiter = get_limiter_for_model("gemini-3.5-flash-lite")
        flash_limiter = get_limiter_for_model("gemini-3.6-flash")
        
        assert lite_limiter.max_rate == 15
        assert lite_limiter.time_period == 60
        
        assert flash_limiter.max_rate == 5
        assert flash_limiter.time_period == 60

    asyncio.run(_check())

def test_mark_model_cooldown_and_availability():
    """Kiểm tra cơ chế Circuit Breaker: đánh dấu Cooldown khi gặp lỗi Quota"""
    test_model = "test-model-cooldown"
    
    # Ban đầu khả dụng
    _model_cooldowns.pop(test_model, None)
    assert is_model_available(test_model) is True
    
    # Đánh dấu cooldown 60s
    mark_model_cooldown(test_model, duration_sec=60)
    assert is_model_available(test_model) is False
    
    # Đánh dấu cooldown hết hạn ngay
    mark_model_cooldown(test_model, duration_sec=-1)
    assert is_model_available(test_model) is True

def test_get_cascade_models_filtering(monkeypatch):
    """Kiểm tra lọc bỏ model đang trong trạng thái Cooldown khỏi danh sách ưu tiên"""
    monkeypatch.delenv("GEMINI_MASTER_MODELS", raising=False)
    _model_cooldowns.clear()
    
    # Đưa model top 1 (gemini-3.6-flash) vào Cooldown
    mark_model_cooldown("gemini-3.6-flash", duration_sec=120)
    
    available_master = get_cascade_models(tier="master")
    # Model 3.6 không còn ở đầu danh sách
    assert "gemini-3.6-flash" not in available_master
    # Model 3.5 nhảy lên ưu tiên hàng đầu
    assert available_master[0] == "gemini-3.5-flash"

def test_get_cascade_models_all_cooldown_fallback(monkeypatch):
    """Khi tất cả model trong tier đều bị cooldown, hệ thống tự động reset về danh sách gốc để chống chết đói"""
    monkeypatch.delenv("GEMINI_SUBAGENT_MODELS", raising=False)
    _model_cooldowns.clear()
    
    for m in DEFAULT_SUBAGENT_CASCADE:
        mark_model_cooldown(m, duration_sec=300)
        
    available = get_cascade_models(tier="subagent")
    # Vẫn trả về danh sách để tiếp tục thử lại
    assert available == DEFAULT_SUBAGENT_CASCADE

def test_get_cascade_models_env_override(monkeypatch):
    """Kiểm tra khả năng tùy biến cascade qua biến môi trường"""
    monkeypatch.setenv("GEMINI_SUBAGENT_MODELS", "custom-sub-1, custom-sub-2")
    monkeypatch.setenv("GEMINI_MASTER_MODELS", "custom-master-1, custom-master-2")
    _model_cooldowns.clear()
    
    assert get_cascade_models("subagent") == ["custom-sub-1", "custom-sub-2"]
    assert get_cascade_models("master") == ["custom-master-1", "custom-master-2"]

def test_configure_llm():
    """Kiểm tra thiết lập API Key toàn cục"""
    with pytest.raises(ValueError, match="API Key không hợp lệ"):
        configure_llm("")
    
    # Với key hợp lệ không ném lỗi
    configure_llm("dummy_api_key_test")
