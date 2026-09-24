import os
import asyncio
import json
import logging
import google.generativeai as genai
from typing import Dict, Any, Tuple, Optional
from schema import MasterAgentResponse
import llm_manager

logger = logging.getLogger("ai_agents")

class CascadeExecutionError(Exception):
    """Lỗi khi toàn bộ model trong cascade đều thất bại."""
    pass

class QuotaExceededError(CascadeExecutionError):
    """Lỗi khi toàn bộ model trong cascade đều đã vượt quá giới hạn truy cập (429/Quota)."""
    pass

def configure_gemini(api_key: str):
    """Cấu hình API Key toàn cục cho GenAI."""
    llm_manager.configure_llm(api_key)

async def execute_with_cascade(
    tier: str, 
    prompt: str, 
    generation_config: Optional[Any] = None, 
    timeout_sec: int = 25
) -> Tuple[str, str]:
    """
    Thực thi prompt với cơ chế Cascade và Auto-Failover:
    - Thử lần lượt các model theo độ ưu tiên của tier ('subagent' hoặc 'master').
    - Áp dụng đúng Rate Limiter cho từng model.
    - Tự động chuyển sang model tiếp theo nếu gặp lỗi 429 / 503 / Quota / Timeout.
    - Trả về tuple: (kết quả text, tên model đã phục vụ thành công).
    """
    cascade_models = llm_manager.get_cascade_models(tier)
    last_error = None

    for model_name in cascade_models:
        limiter = llm_manager.get_limiter_for_model(model_name)
        
        try:
            async with limiter:
                logger.info(f"[{tier.upper()}] Thử gọi model '{model_name}'...")
                model = genai.GenerativeModel(model_name)
                
                if generation_config:
                    coro = model.generate_content_async(prompt, generation_config=generation_config)
                else:
                    coro = model.generate_content_async(prompt)
                    
                response = await asyncio.wait_for(coro, timeout=timeout_sec)
                
                if response and response.text:
                    logger.info(f"✅ [{tier.upper()}] Model '{model_name}' phản hồi thành công.")
                    return response.text, model_name
                    
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ [{tier.upper()}] Model '{model_name}' bị Timeout ({timeout_sec}s). Đang chuyển sang model tiếp theo...")
            llm_manager.mark_model_cooldown(model_name, duration_sec=120)
            last_error = "Timeout"
            continue
            
        except Exception as e:
            error_str = str(e).lower()
            # Bắt lỗi Quota / Rate limit 429 / 503 Quá tải máy chủ / Service Unavailable
            if any(k in error_str for k in ["quota exceeded", "limit: 0", "429", "resourceexhausted", "503", "high demand", "unavailable", "serviceunavailable", "overloaded", "deadline"]):
                logger.warning(f"⚠️ [{tier.upper()}] Model '{model_name}' bị Quota hoặc 503 Quá tải máy chủ: {e}. Tự động failover...")
                llm_manager.mark_model_cooldown(model_name, duration_sec=120)
                last_error = e
                continue
            elif "404" in error_str or "not found" in error_str:
                logger.warning(f"⚠️ [{tier.upper()}] Model '{model_name}' không tồn tại hoặc không cấp phép: {e}. Cooldown 24h...")
                llm_manager.mark_model_cooldown(model_name, duration_sec=86400)
                last_error = e
                continue
            elif "schema" in error_str or "unknown field" in error_str:
                logger.error(f"❌ Lỗi định dạng Schema: {e}")
                raise ValueError(f"Lỗi định dạng Schema gọi LLM: {e}")
            else:
                logger.error(f"Lỗi khi gọi model '{model_name}': {e}")
                last_error = e
                continue

    # Nếu duyệt hết toàn bộ model trong cascade mà vẫn không thành công
    last_err_str = str(last_error).lower()
    if any(k in last_err_str for k in ["quota", "rate limit", "429", "resourceexhausted", "limit: 0"]):
        raise QuotaExceededError(f"Tất cả các model trong nhóm {tier} ({cascade_models}) đều thất bại do vượt hạn ngạch Quota/Rate Limit. Lỗi: {last_error}")
    else:
        raise CascadeExecutionError(f"Tất cả các model trong nhóm {tier} ({cascade_models}) đều thất bại. Lỗi cuối cùng: {last_error}")

async def run_technical_agent(ticker: str, tech_data: str) -> Tuple[str, str]:
    """Agent Phân tích Kỹ thuật (Sử dụng Sub-Agent Cascade)"""
    prompt = f"""
    Bạn là một Chuyên gia Phân tích Kỹ thuật (Technical Analyst) xuất sắc cho thị trường chứng khoán Việt Nam.
    Nhiệm vụ của bạn là phân tích hành vi giá, khối lượng, hỗ trợ/kháng cự, và các chỉ báo động lượng (RSI, MACD) của mã cổ phiếu: {ticker}.
    
    Dữ liệu kỹ thuật gần đây:
    {tech_data}
    
    Hãy đưa ra phân tích ngắn gọn, súc tích (dưới 150 từ) về xu hướng hiện tại và các tín hiệu kỹ thuật đáng chú ý. Kết luận bằng một trạng thái: TÍCH CỰC, TIÊU CỰC, hoặc TRUNG LẬP.
    """
    try:
        return await execute_with_cascade("subagent", prompt)
    except (QuotaExceededError, CascadeExecutionError) as ce:
        raise ce
    except Exception as e:
        logger.error(f"Technical Agent failed: {e}")
        return "⚠️ Dữ liệu Phân tích Kỹ thuật tạm thời không khả dụng do lỗi API/Mạng. Master Agent hãy bỏ qua phần này.", "Fallback"

async def run_fundamental_agent(ticker: str, fa_data: str) -> Tuple[str, str]:
    """Agent Phân tích Cơ bản (Sử dụng Sub-Agent Cascade)"""
    prompt = f"""
    Bạn là một Chuyên gia Phân tích Cơ bản (Fundamental Analyst) am hiểu sâu sắc về định giá doanh nghiệp tại Việt Nam.
    Nhiệm vụ của bạn là đánh giá tình hình kinh doanh, định giá (P/E, P/B, EPS, ROE) và tiềm năng của: {ticker}.
    
    Dữ liệu cơ bản (Real Data):
    {fa_data}
    
    Hãy đưa ra phân tích ngắn gọn (dưới 150 từ) về rủi ro, định giá hiện tại (rẻ/đắt/hợp lý). Kết luận bằng một trạng thái: TỐT, XẤU, hoặc BÌNH THƯỜNG.
    """
    try:
        return await execute_with_cascade("subagent", prompt)
    except (QuotaExceededError, CascadeExecutionError) as ce:
        raise ce
    except Exception as e:
        logger.error(f"Fundamental Agent failed: {e}")
        return "⚠️ Dữ liệu Phân tích Cơ bản tạm thời không khả dụng do lỗi API/Mạng. Master Agent hãy bỏ qua phần này.", "Fallback"

async def run_macro_agent(ticker: str, market_data: str, news_data: str) -> Tuple[str, str]:
    """Agent Phân tích Vĩ mô & Dòng tiền (Sử dụng Sub-Agent Cascade)"""
    prompt = f"""
    Bạn là một Chuyên gia Chiến lược Thị trường (Macro & Flow Analyst).
    Nhiệm vụ của bạn là đánh giá bối cảnh thị trường chung (VN-INDEX), xu hướng dòng tiền và TÂM LÝ TIN TỨC để xem môi trường hiện tại có thuận lợi cho việc đầu tư mã {ticker} hay không.
    
    Dữ liệu thị trường chung (Real Data):
    {market_data}
    
    Tin tức mới nhất (Real-time News):
    {news_data}
    
    Hãy đưa ra nhận định ngắn gọn (dưới 150 từ) về sức mạnh của VN-INDEX và đánh giá rõ Tâm lý tin tức (Sentiment) hiện tại là Tích cực hay Tiêu cực. Kết luận bằng một trạng thái: THUẬN LỢI, RỦI RO, hoặc THẬN TRỌNG.
    """
    try:
        return await execute_with_cascade("subagent", prompt)
    except (QuotaExceededError, CascadeExecutionError) as ce:
        raise ce
    except Exception as e:
        logger.error(f"Macro Agent failed: {e}")
        return "⚠️ Dữ liệu Phân tích Vĩ mô tạm thời không khả dụng do lỗi API/Mạng. Master Agent hãy bỏ qua phần này.", "Fallback"

async def run_master_agent(
    ticker: str, 
    current_price: float, 
    tech_analysis: str, 
    fa_analysis: str, 
    macro_analysis: str, 
    risk_profile: str = "Cân bằng"
) -> Tuple[str, str]:
    """Master Agent: Tổng hợp và ra Quyết định (Sử dụng Master Cascade + Pydantic Schema)"""
    prompt = f"""
    Bạn là Master Agent (Giám đốc Đầu tư - CIO) của một quỹ đầu tư tại Việt Nam.
    Bạn đang xem xét mã cổ phiếu {ticker} với mức giá hiện tại là {current_price:,.0f} VND.
    
    Khẩu vị rủi ro (Risk Profile) của nhà đầu tư: {risk_profile}.
    
    Báo cáo từ 3 chuyên viên:
    
    1. Kỹ thuật:
    {tech_analysis}
    
    2. Cơ bản:
    {fa_analysis}
    
    3. Vĩ mô:
    {macro_analysis}
    
    LƯU Ý QUAN TRỌNG: Nếu bất kỳ báo cáo nào có chứa "⚠️", nghĩa là dữ liệu đó không khả dụng. Bạn hãy ra quyết định dựa trên các dữ liệu còn lại một cách linh hoạt (Graceful Degradation) mà không được báo lỗi sập hệ thống. Nếu thiếu cả 3, hãy đề xuất "NẮM GIỮ" hoặc "QUAN SÁT" với tỷ trọng 0%.
    
    Nhiệm vụ:
    - Đưa ra Khuyến nghị cuối cùng (MUA, BÁN, hoặc NẮM GIỮ).
    - HÃY TỰ ĐỘNG ĐIỀU CHỈNH Tỷ trọng giải ngân phù hợp với Khẩu vị rủi ro: {risk_profile} (Thận trọng: Tỷ trọng thấp 10-20%, Cân bằng: 20-40%, Mạo hiểm: 40-70%).
    - HÃY TỰ ĐỘNG ĐIỀU CHỈNH mức giá Cắt lỗ (Stop-loss) và Chốt lời (Take-profit) linh hoạt theo Khẩu vị rủi ro: {risk_profile}.
    - Cung cấp Lý do rõ ràng, khách quan.
    
    Yêu cầu định dạng đầu ra:
    Trả về dữ liệu dưới định dạng JSON tuân thủ strict schema.
    """
    
    gen_config = genai.types.GenerationConfig(
        response_mime_type="application/json",
        response_schema=MasterAgentResponse
    )
    
    try:
        return await execute_with_cascade("master", prompt, generation_config=gen_config, timeout_sec=30)
    except (QuotaExceededError, CascadeExecutionError) as ce:
        raise ce
    except Exception as e:
        logger.error(f"Master Agent failed: {e}")
        fallback = {
            "recommendation": "LỖI HỆ THỐNG",
            "order_action": "GIỮ",
            "target_price": 0.0,
            "volume_percent": 0,
            "allocation_pct": 0,
            "stop_loss": 0.0,
            "take_profit": 0.0,
            "reasoning": f"Tất cả các nỗ lực kết nối Master Agent đều thất bại: {e}",
            "market_sentiment": "Unknown"
        }
        return json.dumps(fallback), "Fallback"

async def analyze_stock_async(
    ticker: str, 
    current_price: float, 
    tech_data: str, 
    fa_data: str, 
    market_data: str, 
    news_data: str, 
    risk_profile: str = "Cân bằng"
) -> dict:
    """Hàm điều phối: Chạy song song 3 Agent con qua subagent cascade, sau đó gọi Master Agent."""
    
    # 1. Chạy song song 3 Agent con
    tech_task = asyncio.create_task(run_technical_agent(ticker, tech_data))
    fa_task = asyncio.create_task(run_fundamental_agent(ticker, fa_data))
    macro_task = asyncio.create_task(run_macro_agent(ticker, market_data, news_data))
    
    (tech_result, tech_model), (fa_result, fa_model), (macro_result, macro_model) = await asyncio.gather(
        tech_task, fa_task, macro_task
    )
    
    # 2. Gọi Master Agent với kết quả từ các Agent con
    master_result_json, master_model = await run_master_agent(
        ticker, current_price, tech_result, fa_result, macro_result, risk_profile
    )
    
    try:
        master_data = json.loads(master_result_json)
    except json.JSONDecodeError:
        master_data = {
            "recommendation": "LỖI PARSE JSON",
            "order_action": "GIỮ",
            "target_price": 0.0,
            "volume_percent": 0,
            "allocation_pct": 0,
            "stop_loss": 0.0,
            "take_profit": 0.0,
            "reasoning": master_result_json,
            "market_sentiment": "Unknown"
        }
    
    return {
        "tech_analysis": tech_result,
        "fa_analysis": fa_result,
        "macro_analysis": macro_result,
        "master_decision": master_data,
        "models_used": {
            "tech": tech_model,
            "fa": fa_model,
            "macro": macro_model,
            "master": master_model
        }
    }
