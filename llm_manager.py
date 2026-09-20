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

# --- DANH MỤC CASCADE DỰA TRÊN QUOTA THỰC TẾ ---
# 1. Sub-Agents: Cần tần suất cao (3 agent con * N mã).
#    Dùng Flash-Lite có 15 RPM và 500 RPD mỗi model (tổng 1000 RPD).
DEFAULT_SUBAGENT_CASCADE = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]

# 2. Master Agent (CIO): Cần tư duy cao nhất, xuất JSON schema.
#    Ưu tiên flagship 3.8-flash -> 3.7 -> 3.6 -> 3.5 -> 3-flash (mỗi model 5 RPM, 20 RPD).
#    Fallback cuối cùng: gemini-3.5-flash-lite (500 RPD) để không bao giờ bị gián đoạn.
DEFAULT_MASTER_CASCADE = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.5-flash-lite",
]

# Quản lý Circuit Breaker & Cooldown cho từng model
_model_cooldowns: Dict[str, float] = {}

# Quản lý Rate Limiters theo event loop
_limiters: Dict[asyncio.AbstractEventLoop, Dict[str, AsyncLimiter]] = {}

def get_limiter_for_model(model_name: str) -> AsyncLimiter:
    """Trả về AsyncLimiter tương ứng với quota RPM của model (15 RPM cho Lite, 5 RPM cho Flash)."""
    loop = asyncio.get_running_loop()
    if loop not in _limiters:
        _limiters[loop] = {
            'lite': AsyncLimiter(15, 60),
            'flash': AsyncLimiter(5, 60)
        }
        
    if "lite" in model_name:
        return _limiters[loop]['lite']
    return _limiters[loop]['flash']

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
