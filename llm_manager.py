import os
import time
import asyncio
import logging
from typing import List, Dict
import google.generativeai as genai
from aiolimiter import AsyncLimiter
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("llm_manager")

# --- DANH MỤC CASCADE DỰA TRÊN QUOTA THỰC TẾ CỦA GOOGLE AI STUDIO ---

# 1. Sub-Agents (Tech, FA, Macro): Cần tần suất cao (3 agent con * N mã).
#    Ưu tiên các bản Lite có 15 RPM và 500 RPD mỗi model (tổng >1000 RPD/ngày).
DEFAULT_SUBAGENT_CASCADE = [
    "gemini-3.5-flash-lite",  # 15 RPM, 500 RPD (Model Lite thông minh & mới nhất)
    "gemini-3.1-flash-lite",  # 15 RPM, 500 RPD (Dự phòng số 1: thêm 500 lượt/ngày)
    "gemini-3.6-flash",       # 5 RPM, 20 RPD (Dự phòng số 2)
]

# 2. Master Agent (CIO): Cần tư duy logic cao nhất, xuất JSON schema nghiêm ngặt.
#    Ưu tiên model ổn định và nhanh nhất: gemini-3.6-flash (Google khuyến nghị thay thế 2.5-flash)
#    Fallback cuối cùng: gemini-3.5-flash-lite (15 RPM, 500 RPD) để hệ thống KHÔNG BAO GIỜ bị gián đoạn.
DEFAULT_MASTER_CASCADE = [
    "gemini-3.6-flash",         # 5 RPM, 20 RPD (Flagship Flash tối ưu tốc độ & chuẩn JSON)
    "gemini-3.5-flash",         # 5 RPM, 20 RPD (Dự phòng 1: Hoạt động ổn định)
    "gemini-3.8-flash",         # 5 RPM, 20 RPD (Dự phòng 2)
    "gemini-3.7-flash",         # 5 RPM, 20 RPD (Dự phòng 3)
    "gemini-3.5-flash-lite",    # 15 RPM, 500 RPD (Cứu cánh an toàn: 500 RPD bảo vệ hệ thống)
]

# Định mức RPM thực tế cho từng model theo bảng quota Google AI Studio
MODEL_RPM_LIMITS: Dict[str, int] = {
    "gemini-3.5-flash-lite": 15,
    "gemini-3.1-flash-lite": 15,
    "gemini-2.5-flash-lite": 10,
    "gemini-3.6-flash": 5,
    "gemini-3.5-flash": 5,
    "gemini-3.8-flash": 5,
    "gemini-3.7-flash": 5,
    "gemini-3-flash-preview": 5,
    "gemini-2.5-flash": 5,
}

# Quản lý Circuit Breaker & Cooldown cho từng model
_model_cooldowns: Dict[str, float] = {}

# Quản lý Rate Limiters riêng biệt cho từng model theo event loop
_limiters: Dict[asyncio.AbstractEventLoop, Dict[str, AsyncLimiter]] = {}

def get_limiter_for_model(model_name: str) -> AsyncLimiter:
    """
    Trả về AsyncLimiter riêng biệt cho từng model.
    Vì Google tính RPM độc lập cho từng model, việc tách riêng limiter cho phép
    hệ thống tận dụng 100% dung lượng song song của tài khoản mà không gây nghẽn chéo.
    """
    loop = asyncio.get_running_loop()
    if loop not in _limiters:
        _limiters[loop] = {}
        
    if model_name not in _limiters[loop]:
        rpm = MODEL_RPM_LIMITS.get(model_name)
        if rpm is None:
            if "2.5-flash-lite" in model_name:
                rpm = 10
            elif "lite" in model_name:
                rpm = 15
            else:
                rpm = 5
        _limiters[loop][model_name] = AsyncLimiter(rpm, 60)
        
    return _limiters[loop][model_name]

def mark_model_cooldown(model_name: str, duration_sec: int = 60):
    """Đánh dấu model đang bị Rate Limit/Quota Exceeded, tạm dừng sử dụng trong duration_sec giây."""
    cooldown_until = time.time() + duration_sec
    _model_cooldowns[model_name] = cooldown_until
    logger.warning(f"⚠️ Model '{model_name}' đã chạm hạn ngạch (429/Quota). Tự động Cooldown {duration_sec}s.")

def is_model_available(model_name: str) -> bool:
    """Kiểm tra xem model có đang trong thời gian cooldown không."""
    cooldown_until = _model_cooldowns.get(model_name, 0)
    return time.time() >= cooldown_until

def get_cascade_models(tier: str = "subagent") -> List[str]:
    """
    Trả về danh sách model ưu tiên theo thứ tự cascade.
    Lọc các model đang trong trạng thái cooldown (nếu tất cả đều cooldown, trả về danh sách gốc).
    """
    if tier == "subagent":
        env_val = os.getenv("GEMINI_SUBAGENT_MODELS")
        base_models = [m.strip() for m in env_val.split(",") if m.strip()] if env_val else DEFAULT_SUBAGENT_CASCADE
    else:
        env_val = os.getenv("GEMINI_MASTER_MODELS")
        base_models = [m.strip() for m in env_val.split(",") if m.strip()] if env_val else DEFAULT_MASTER_CASCADE
        
    available = [m for m in base_models if is_model_available(m)]
    
    # Nếu tất cả model trong cascade đều bị đánh dấu cooldown, cho phép thử lại toàn bộ
    if not available:
        logger.warning(f"Tất cả model cho tier '{tier}' đều đang cooldown. Thử lại danh sách cơ sở.")
        return base_models
        
    return available

def configure_llm(api_key: str):
    """Cấu hình API Key cho Google GenAI."""
    if not api_key:
        raise ValueError("API Key không hợp lệ hoặc bị thiếu!")
    genai.configure(api_key=api_key)
