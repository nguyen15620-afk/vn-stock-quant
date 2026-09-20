import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock, AsyncMock
from ai_agents import (
    configure_gemini,
    execute_with_cascade,
    run_technical_agent,
    run_fundamental_agent,
    run_macro_agent,
    run_master_agent,
    analyze_stock_async,
    QuotaExceededError
)
import llm_manager

@pytest.fixture(autouse=True)
def reset_cooldowns():
    """Tự động dọn sạch trạng thái cooldown giữa các test"""
    llm_manager._model_cooldowns.clear()

def test_configure_gemini():
    """Kiểm tra gọi hàm cấu hình GenAI API key"""
    with patch("llm_manager.configure_llm") as mock_conf:
        configure_gemini("test_key_123")
        mock_conf.assert_called_once_with("test_key_123")

@pytest.mark.asyncio
async def test_execute_with_cascade_first_success():
    """Kiểm tra model ưu tiên số 1 phản hồi thành công ngay lượt đầu"""
    mock_resp = MagicMock()
    mock_resp.text = "Phân tích kỹ thuật: Xu hướng tăng rõ nét."
    
    mock_model_inst = MagicMock()
    mock_model_inst.generate_content_async = AsyncMock(return_value=mock_resp)
    
    with patch("google.generativeai.GenerativeModel", return_value=mock_model_inst):
        res, model_used = await execute_with_cascade("subagent", "prompt test")
        assert res == "Phân tích kỹ thuật: Xu hướng tăng rõ nét."
        assert model_used == llm_manager.DEFAULT_SUBAGENT_CASCADE[0]

@pytest.mark.asyncio
async def test_execute_with_cascade_failover_on_quota():
    """Kiểm tra tự động chuyển sang model tiếp theo khi model đầu tiên gặp lỗi 429 / Quota Exceeded"""
    mock_model_1 = MagicMock()
    mock_model_1.generate_content_async = AsyncMock(side_effect=Exception("429 Quota exceeded for model gemini-3.5-flash-lite"))
    
    mock_resp_2 = MagicMock()
    mock_resp_2.text = "Phản hồi từ model dự phòng số 2."
    mock_model_2 = MagicMock()
    mock_model_2.generate_content_async = AsyncMock(return_value=mock_resp_2)
    
    def model_factory(name):
        if name == llm_manager.DEFAULT_SUBAGENT_CASCADE[0]:
            return mock_model_1
        return mock_model_2

    with patch("google.generativeai.GenerativeModel", side_effect=model_factory):
        res, model_used = await execute_with_cascade("subagent", "prompt test")
        assert res == "Phản hồi từ model dự phòng số 2."
        assert model_used == llm_manager.DEFAULT_SUBAGENT_CASCADE[1]
        # Model 1 phải bị đưa vào cooldown
        assert llm_manager.is_model_available(llm_manager.DEFAULT_SUBAGENT_CASCADE[0]) is False

@pytest.mark.asyncio
async def test_execute_with_cascade_timeout_failover():
    """Kiểm tra tự động chuyển model khi model đầu tiên bị Timeout"""
    mock_model_1 = MagicMock()
    # Giả lập timeout quá 1s
    async def _hang(*args, **kwargs):
        await asyncio.sleep(5)
    mock_model_1.generate_content_async = _hang
    
    mock_resp_2 = MagicMock()
    mock_resp_2.text = "Phản hồi thành công sau timeout."
    mock_model_2 = MagicMock()
    mock_model_2.generate_content_async = AsyncMock(return_value=mock_resp_2)
    
    def model_factory(name):
        if name == llm_manager.DEFAULT_SUBAGENT_CASCADE[0]:
            return mock_model_1
        return mock_model_2

    with patch("google.generativeai.GenerativeModel", side_effect=model_factory):
        res, model_used = await execute_with_cascade("subagent", "prompt test", timeout_sec=1)
        assert res == "Phản hồi thành công sau timeout."
        assert model_used == llm_manager.DEFAULT_SUBAGENT_CASCADE[1]

@pytest.mark.asyncio
async def test_execute_with_cascade_all_failed_raises_quota_error():
    """Kiểm tra ném QuotaExceededError khi toàn bộ model trong cascade đều thất bại"""
    mock_fail_model = MagicMock()
    mock_fail_model.generate_content_async = AsyncMock(side_effect=Exception("429 ResourceExhausted"))
    
    with patch("google.generativeai.GenerativeModel", return_value=mock_fail_model):
        with pytest.raises(QuotaExceededError, match="đều thất bại"):
            await execute_with_cascade("subagent", "prompt test")

@pytest.mark.asyncio
async def test_subagents_graceful_degradation():
    """Kiểm tra các sub-agents trả về thông điệp dự phòng và không làm sập luồng khi gặp lỗi mạng khác"""
    with patch("ai_agents.execute_with_cascade", side_effect=Exception("Unexpected connection drop")):
        tech_res, tech_m = await run_technical_agent("FPT", "SMA data")
        assert "⚠️" in tech_res
        assert tech_m == "Fallback"
        
        fa_res, fa_m = await run_fundamental_agent("FPT", "FA data")
        assert "⚠️" in fa_res
        assert fa_m == "Fallback"
        
        macro_res, macro_m = await run_macro_agent("FPT", "VNINDEX", "News")
        assert "⚠️" in macro_res
        assert macro_m == "Fallback"

@pytest.mark.asyncio
async def test_master_agent_fallback_on_unexpected_error():
    """Kiểm tra Master Agent tạo JSON cứu hộ khi toàn bộ nỗ lực kết nối thất bại"""
    with patch("ai_agents.execute_with_cascade", side_effect=Exception("General network outage")):
        raw_json, model_name = await run_master_agent("VCB", 90000.0, "Tech", "FA", "Macro")
        assert model_name == "Fallback"
        data = json.loads(raw_json)
        assert data["recommendation"] == "LỖI HỆ THỐNG"
        assert data["order_action"] == "GIỮ"
        assert data["volume_percent"] == 0

@pytest.mark.asyncio
async def test_analyze_stock_async_full_pipeline():
    """Kiểm tra luồng phân tích hoàn chỉnh: chạy song song 3 agent con, gọi master và ghi nhận metadata models_used"""
    mock_tech = ("Kỹ thuật: Uptrend mạnh. TÍCH CỰC.", "gemini-3.5-flash-lite")
    mock_fa = ("Cơ bản: P/E 13x, ROE 24%. TỐT.", "gemini-3.5-flash-lite")
    mock_macro = ("Vĩ mô: Dòng tiền lan tỏa. THUẬN LỢI.", "gemini-3.5-flash-lite")
    
    master_dict = {
        "recommendation": "MUA",
        "order_action": "MUA",
        "target_price": 125000.0,
        "volume_percent": 30,
        "allocation_pct": 30,
        "stop_loss": 112000.0,
        "take_profit": 140000.0,
        "reasoning": "Sự đồng thuận cao giữa 3 chuyên viên.",
        "market_sentiment": "Bullish"
    }
    mock_master = (json.dumps(master_dict), "gemini-3.8-flash")
    
    with patch("ai_agents.run_technical_agent", new_callable=AsyncMock, return_value=mock_tech), \
         patch("ai_agents.run_fundamental_agent", new_callable=AsyncMock, return_value=mock_fa), \
         patch("ai_agents.run_macro_agent", new_callable=AsyncMock, return_value=mock_macro), \
         patch("ai_agents.run_master_agent", new_callable=AsyncMock, return_value=mock_master):
        
        result = await analyze_stock_async(
            ticker="FPT",
            current_price=118000.0,
            tech_data="...",
            fa_data="...",
            market_data="...",
            news_data="...",
            risk_profile="Cân bằng"
        )
        
        # Kiểm tra nội dung phân tích
        assert result["tech_analysis"] == mock_tech[0]
        assert result["fa_analysis"] == mock_fa[0]
        assert result["macro_analysis"] == mock_macro[0]
        assert result["master_decision"]["recommendation"] == "MUA"
        assert result["master_decision"]["target_price"] == 125000.0
        
        # Kiểm tra metadata model phục vụ
        assert result["models_used"]["tech"] == "gemini-3.5-flash-lite"
        assert result["models_used"]["fa"] == "gemini-3.5-flash-lite"
        assert result["models_used"]["macro"] == "gemini-3.5-flash-lite"
        assert result["models_used"]["master"] == "gemini-3.8-flash"

@pytest.mark.asyncio
async def test_analyze_stock_async_json_decode_error_fallback():
    """Kiểm tra xử lý an toàn khi phản hồi từ Master Agent không phải là JSON hợp lệ"""
    mock_tech = ("Kỹ thuật OK", "gemini-3.5-flash-lite")
    mock_fa = ("Cơ bản OK", "gemini-3.5-flash-lite")
    mock_macro = ("Vĩ mô OK", "gemini-3.5-flash-lite")
    mock_master = ("Phản hồi dạng văn bản thường không tuân thủ JSON", "gemini-3.8-flash")
    
    with patch("ai_agents.run_technical_agent", new_callable=AsyncMock, return_value=mock_tech), \
         patch("ai_agents.run_fundamental_agent", new_callable=AsyncMock, return_value=mock_fa), \
         patch("ai_agents.run_macro_agent", new_callable=AsyncMock, return_value=mock_macro), \
         patch("ai_agents.run_master_agent", new_callable=AsyncMock, return_value=mock_master):
        
        result = await analyze_stock_async("HPG", 28000.0, "...", "...", "...", "...")
        
        assert result["master_decision"]["recommendation"] == "LỖI PARSE JSON"
        assert result["master_decision"]["order_action"] == "GIỮ"
        assert result["models_used"]["master"] == "gemini-3.8-flash"
