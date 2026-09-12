from pydantic import BaseModel, Field

class MasterAgentResponse(BaseModel):
    recommendation: str = Field(description="Khuyến nghị cuối cùng: MUA, BÁN, hoặc NẮM GIỮ (HOLD)")
    allocation_pct: int = Field(description="Tỷ trọng giải ngân đề xuất (từ 0 đến 100)")
    stop_loss: float = Field(description="Giá cắt lỗ dự kiến (VND)")
    take_profit: float = Field(description="Giá chốt lời mục tiêu (VND)")
    reasoning: str = Field(description="Lý do chi tiết và khách quan đằng sau khuyến nghị này, dựa trên phân tích của các Agent con")
    market_sentiment: str = Field(description="Đánh giá ngắn gọn về tâm lý thị trường (Bullish, Bearish, Neutral)")
