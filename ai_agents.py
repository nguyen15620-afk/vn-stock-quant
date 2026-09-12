import os
import asyncio
import google.generativeai as genai
from dotenv import load_dotenv
import json
from tenacity import retry, wait_exponential, stop_after_attempt
import llm_manager

from schema import MasterAgentResponse

# Global model variables
tech_model = None
fa_model = None
macro_model = None
master_model = None
flash_model_name = None

def configure_gemini(api_key: str):
    global tech_model, fa_model, macro_model, master_model
    
    if not api_key:
        raise ValueError("Thiếu API Key! Vui lòng nhập API Key trên giao diện.")
        
    genai.configure(api_key=api_key)
    
    # Khởi tạo mô hình sau khi configure
    try:
        global flash_model_name
        flash_model_name = llm_manager.get_best_available_model(api_key, tier="flash")
        pro_model_name = llm_manager.get_best_available_model(api_key, tier="pro")
        
        tech_model = genai.GenerativeModel(flash_model_name)
        fa_model = genai.GenerativeModel(flash_model_name)
        macro_model = genai.GenerativeModel(flash_model_name)
        master_model = genai.GenerativeModel(pro_model_name)
    except Exception as e:
        print(f"Error initializing models: {e}")

# Giảm thời gian chờ retry để báo lỗi nhanh hơn nếu cấu hình sai
@retry(wait=wait_exponential(multiplier=1, min=1, max=3), stop=stop_after_attempt(2), reraise=True)
async def fetch_gemini_response(model, prompt, is_pro=False, generation_config=None):
    limiter = llm_manager.pro_limiter if is_pro else llm_manager.flash_limiter
    async with limiter:
        if generation_config:
            response = await model.generate_content_async(prompt, generation_config=generation_config)
        else:
            response = await model.generate_content_async(prompt)
        return response.text

async def run_technical_agent(ticker: str, tech_data: str) -> str:
    """Agent Phân tích Kỹ thuật"""
    prompt = f"""
    Bạn là một Chuyên gia Phân tích Kỹ thuật (Technical Analyst) xuất sắc cho thị trường chứng khoán Việt Nam.
    Nhiệm vụ của bạn là phân tích hành vi giá, khối lượng, hỗ trợ/kháng cự, và các chỉ báo động lượng (RSI, MACD) của mã cổ phiếu: {ticker}.
    
    Dữ liệu kỹ thuật gần đây:
    {tech_data}
    
    Hãy đưa ra phân tích ngắn gọn, súc tích (dưới 150 từ) về xu hướng hiện tại và các tín hiệu kỹ thuật đáng chú ý. Kết luận bằng một trạng thái: TÍCH CỰC, TIÊU CỰC, hoặc TRUNG LẬP.
    """
    try:
        return await fetch_gemini_response(tech_model, prompt)
    except Exception as e:
        print(f"Technical Agent failed after retries: {e}")
        return "⚠️ Dữ liệu Phân tích Kỹ thuật tạm thời không khả dụng do lỗi API/Mạng. Master Agent hãy bỏ qua phần này."

async def run_fundamental_agent(ticker: str, fa_data: str) -> str:
    """Agent Phân tích Cơ bản"""
    prompt = f"""
    Bạn là một Chuyên gia Phân tích Cơ bản (Fundamental Analyst) am hiểu sâu sắc về định giá doanh nghiệp tại Việt Nam.
    Nhiệm vụ của bạn là đánh giá tình hình kinh doanh, định giá (P/E, P/B, EPS, ROE) và tiềm năng của: {ticker}.
    
    Dữ liệu cơ bản (Real Data):
    {fa_data}
    
    Hãy đưa ra phân tích ngắn gọn (dưới 150 từ) về rủi ro, định giá hiện tại (rẻ/đắt/hợp lý). Kết luận bằng một trạng thái: TỐT, XẤU, hoặc BÌNH THƯỜNG.
    """
    try:
        return await fetch_gemini_response(fa_model, prompt)
    except Exception as e:
        print(f"Fundamental Agent failed after retries: {e}")
        return "⚠️ Dữ liệu Phân tích Cơ bản tạm thời không khả dụng do lỗi API/Mạng. Master Agent hãy bỏ qua phần này."

async def run_macro_agent(ticker: str, market_data: str) -> str:
    """Agent Phân tích Vĩ mô & Dòng tiền"""
    prompt = f"""
    Bạn là một Chuyên gia Chiến lược Thị trường (Macro & Flow Analyst).
    Nhiệm vụ của bạn là đánh giá bối cảnh thị trường chung (VN-INDEX), xu hướng dòng tiền để xem môi trường hiện tại có thuận lợi cho việc đầu tư mã {ticker} hay không.
    
    Dữ liệu thị trường chung (Real Data):
    {market_data}
    
    Hãy đưa ra nhận định ngắn gọn (dưới 150 từ) về sức mạnh của VN-INDEX. Kết luận bằng một trạng thái: THUẬN LỢI, RỦI RO, hoặc THẬN TRỌNG.
    """
    try:
        return await fetch_gemini_response(macro_model, prompt)
    except Exception as e:
        print(f"Macro Agent failed after retries: {e}")
        return "⚠️ Dữ liệu Phân tích Vĩ mô tạm thời không khả dụng do lỗi API/Mạng. Master Agent hãy bỏ qua phần này."

async def run_master_agent(ticker: str, current_price: float, tech_analysis: str, fa_analysis: str, macro_analysis: str) -> str:
    """Master Agent: Tổng hợp và ra Quyết định (Hỗ trợ Graceful Degradation)"""
    prompt = f"""
    Bạn là Master Agent (Giám đốc Đầu tư - CIO) của một quỹ đầu tư tại Việt Nam.
    Bạn đang xem xét mã cổ phiếu {ticker} với mức giá hiện tại là {current_price} VND.
    
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
    - Xác định tỷ trọng giải ngân phù hợp (0-100%).
    - Đề xuất mức giá cắt lỗ (Stop-loss) và chốt lời (Take-profit) logic so với giá hiện tại.
    - Cung cấp Lý do rõ ràng.
    
    Yêu cầu định dạng đầu ra:
    Trả về dữ liệu dưới định dạng JSON tuân thủ strict schema của bạn. KHÔNG BAO GỒM markdown format (như ```json) trong câu trả lời, chỉ xuất JSON thuần.
    """
    try:
        gen_config = genai.types.GenerationConfig(
            response_mime_type="application/json",
            response_schema=MasterAgentResponse
        )
        return await fetch_gemini_response(master_model, prompt, is_pro=True, generation_config=gen_config)
    except Exception as e:
        print(f"Master Agent failed with PRO model: {e}")
        print("⚠️ Bắt đầu Auto-Fallback sang model Flash...")
        try:
            # Fallback sang Flash model (is_pro=False)
            fallback_model = genai.GenerativeModel(flash_model_name)
            return await fetch_gemini_response(fallback_model, prompt, is_pro=False, generation_config=gen_config)
        except Exception as e2:
            print(f"Master Agent completely failed after fallback: {e2}")
            fallback = {
                "recommendation": "LỖI HỆ THỐNG",
                "allocation_pct": 0,
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "reasoning": f"Tất cả các nỗ lực kết nối Master Agent đều thất bại: {e2}",
                "market_sentiment": "Unknown"
            }
            return json.dumps(fallback)

async def analyze_stock_async(ticker: str, current_price: float, tech_data: str, fa_data: str, market_data: str) -> dict:
    """Hàm main để chạy song song 3 Agent con, sau đó gọi Master Agent"""
    
    # 1. Chạy song song 3 Agent con (Rate Limit đã được aiolimiter quản lý tự động)
    tech_task = asyncio.create_task(run_technical_agent(ticker, tech_data))
    fa_task = asyncio.create_task(run_fundamental_agent(ticker, fa_data))
    macro_task = asyncio.create_task(run_macro_agent(ticker, market_data))
    
    tech_result, fa_result, macro_result = await asyncio.gather(tech_task, fa_task, macro_task)
    
    # 2. Gọi Master Agent với kết quả từ các Agent con
    master_result_json = await run_master_agent(ticker, current_price, tech_result, fa_result, macro_result)
    
    try:
        master_data = json.loads(master_result_json)
    except json.JSONDecodeError:
        master_data = {
             "recommendation": "LỖI PARSE JSON",
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
        "master_decision": master_data
    }
