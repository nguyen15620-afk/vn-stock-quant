from pydantic import BaseModel, Field

class MasterAgentResponse(BaseModel):
    recommendation: str = Field(description="Khuyến nghị cuối cùng: MUA, BÁN, hoặc NẮM GIỮ (HOLD)")
    order_action: str = Field(description="Hành động đặt lệnh thực thi (MUA/BÁN/GIỮ)")
    target_price: float = Field(description="Giá đặt lệnh mục tiêu (VND)")
    allocation_pct: int = Field(default=0, description="Tỷ trọng phân bổ vốn đề xuất trong danh mục (từ 0 đến 100%)")
    volume_percent: int = Field(default=0, description="Tỷ trọng giải ngân cụ thể cho đợt lệnh này (%)")
    stop_loss: float = Field(default=0.0, description="Giá cắt lỗ dự kiến (VND)")
    take_profit: float = Field(default=0.0, description="Giá chốt lời mục tiêu (VND)")
    reasoning: str = Field(description="Lý do chi tiết và khách quan đằng sau khuyến nghị này, dựa trên phân tích của các Agent con")
    market_sentiment: str = Field(default="Neutral", description="Đánh giá ngắn gọn về tâm lý thị trường (Bullish, Bearish, Neutral)")

