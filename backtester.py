import pandas as pd
import numpy as np
from typing import Dict, Any, List

def run_backtest(
    df: pd.DataFrame,
    initial_capital: float = 100_000_000.0,
    buy_fee: float = 0.0015,
    sell_fee_tax: float = 0.0025,
    risk_free_rate: float = 0.05
) -> Dict[str, Any]:
    """
    Mô phỏng giao dịch lịch sử (Backtest) cho chiến lược định lượng trên TTCK Việt Nam.
    
    NGUYÊN TẮC QUAN TRỌNG:
    - Loại bỏ hoàn toàn Lookahead Bias:
      + Tín hiệu sinh tại giá đóng cửa (Close) của ngày T.
      + Khớp lệnh mua/bán tại giá mở cửa (Open) của ngày T+1.
    - Áp dụng đầy đủ chi phí giao dịch & thuế:
      + Phí mua: 0.15% (mặc định)
      + Phí bán + Thuế bán: 0.25% (0.15% phí môi giới + 0.10% thuế TNCN)
      + Tổng chi phí 1 vòng T+: ~0.40%
    - Chỉ số đo lường nâng cao cho dữ liệu 3-5 năm:
      + Sharpe Ratio (chuẩn hóa 252 phiên, lãi suất phi rủi ro 5%/năm)
      + Thống kê hiệu suất chi tiết theo từng năm (Yearly Breakdown)
    """
    if df.empty or len(df) < 5 or 'signal' not in df.columns:
        return {
            "total_return_pct": 0.0,
            "benchmark_return_pct": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "final_equity": initial_capital,
            "trades": [],
            "equity_curve": pd.DataFrame(),
            "yearly_breakdown": []
        }

    df = df.copy().reset_index(drop=True)
    n = len(df)

    cash = initial_capital
    shares = 0
    trades: List[Dict[str, Any]] = []
    equity_series = []
    
    current_entry_price = 0.0
    current_entry_date = None
    current_entry_index = 0

    # Duyệt từng ngày
    for i in range(n):
        row = df.iloc[i]
        date_val = row.get('time', i)
        open_price = row.get('open', row['close'])
        close_price = row['close']

        # 1. Thực hiện lệnh đã được báo trước từ phiên hôm qua (i - 1)
        if i > 0:
            prev_signal = df.iloc[i - 1]['signal']

            # Khớp lệnh MUA tại Open nến T
            if prev_signal == 'Buy' and shares == 0 and cash > 0:
                # Tính số cổ phiếu mua được theo lô chẵn 100 cổ phiếu (chuẩn HOSE/HNX)
                cost_per_share = open_price * (1.0 + buy_fee)
                max_shares = int((cash / cost_per_share) // 100) * 100
                if max_shares > 0:
                    trade_cost = max_shares * open_price * (1.0 + buy_fee)
                    cash -= trade_cost
                    shares = max_shares
                    current_entry_price = open_price
                    current_entry_date = date_val
                    current_entry_index = i

            # Khớp lệnh BÁN tại Open nến T (tối thiểu T+2 theo quy định T+ Việt Nam)
            elif prev_signal == 'Sell' and shares > 0 and (i - current_entry_index >= 2):
                revenue = shares * open_price * (1.0 - sell_fee_tax)
                gross_pnl = (open_price - current_entry_price) * shares
                cost_basis = shares * current_entry_price * (1.0 + buy_fee)
                net_pnl = revenue - cost_basis
                ret_pct = (revenue / cost_basis - 1.0) * 100.0 if cost_basis > 0 else 0.0

                trades.append({
                    'entry_date': current_entry_date,
                    'entry_price': current_entry_price,
                    'exit_date': date_val,
                    'exit_price': open_price,
                    'shares': shares,
                    'net_pnl': net_pnl,
                    'return_pct': round(ret_pct, 2),
                    'holding_bars': i - current_entry_index
                })

                cash += revenue
                shares = 0
                current_entry_price = 0.0
                current_entry_date = None

        # Tính tổng tài sản (Equity) tại cuối ngày theo giá Close
        current_equity = cash + (shares * close_price * (1.0 - sell_fee_tax) if shares > 0 else 0.0)
        equity_series.append({
            'time': date_val,
            'equity': current_equity,
            'close': close_price
        })

    # Nếu còn giữ hàng ở nến cuối cùng, đóng vị thế mô phỏng theo giá close cuối
    if shares > 0:
        final_row = df.iloc[-1]
        final_open = final_row['close']
        revenue = shares * final_open * (1.0 - sell_fee_tax)
        cost_basis = shares * current_entry_price * (1.0 + buy_fee)
        net_pnl = revenue - cost_basis
        ret_pct = (revenue / cost_basis - 1.0) * 100.0 if cost_basis > 0 else 0.0

        trades.append({
            'entry_date': current_entry_date,
            'entry_price': current_entry_price,
            'exit_date': final_row.get('time', n-1),
            'exit_price': final_open,
            'shares': shares,
            'net_pnl': net_pnl,
            'return_pct': round(ret_pct, 2),
            'holding_bars': n - 1 - current_entry_index
        })
        cash += revenue
        shares = 0

    equity_df = pd.DataFrame(equity_series)
    final_equity = equity_df['equity'].iloc[-1] if not equity_df.empty else initial_capital

    # Tính toán các chỉ số cơ bản
    total_return_pct = round(((final_equity - initial_capital) / initial_capital) * 100.0, 2)

    # Benchmark: Mua và giữ từ nến đầu đến nến cuối
    first_close = df.iloc[0]['close']
    last_close = df.iloc[-1]['close']
    benchmark_return_pct = round(((last_close - first_close) / first_close) * 100.0, 2) if first_close > 0 else 0.0

    # Max Drawdown
    equity_df['peak'] = equity_df['equity'].cummax()
    equity_df['drawdown'] = (equity_df['equity'] - equity_df['peak']) / equity_df['peak']
    max_drawdown_pct = round(abs(float(equity_df['drawdown'].min())) * 100.0, 2)

    # Thống kê giao dịch
    total_trades = len(trades)
    winning_trades = [t for t in trades if t['net_pnl'] > 0]
    losing_trades = [t for t in trades if t['net_pnl'] <= 0]
    win_rate_pct = round((len(winning_trades) / total_trades * 100.0), 2) if total_trades > 0 else 0.0

    gross_profit = sum(t['net_pnl'] for t in winning_trades)
    gross_loss = abs(sum(t['net_pnl'] for t in losing_trades))
    if gross_loss > 0:
        profit_factor = round(gross_profit / gross_loss, 2)
    elif gross_profit > 0:
        profit_factor = 99.9  # Rất tốt
    else:
        profit_factor = 0.0

    # Sharpe Ratio (annualized, 252 trading days)
    daily_returns = equity_df['equity'].pct_change().dropna()
    rf_daily = risk_free_rate / 252.0
    excess_returns = daily_returns - rf_daily
    if len(excess_returns) > 1 and excess_returns.std() > 1e-8:
        sharpe_ratio = round(float(np.sqrt(252) * excess_returns.mean() / excess_returns.std()), 2)
    else:
        sharpe_ratio = 0.0

    # Thống kê hiệu suất theo từng năm (Yearly Breakdown)
    yearly_dict = {}
    for t in trades:
        d_val = t.get('exit_date') or t.get('entry_date')
        try:
            year_str = str(pd.to_datetime(d_val).year)
        except Exception:
            year_str = "Khác"

        if year_str not in yearly_dict:
            yearly_dict[year_str] = {
                "year": year_str,
                "trades_count": 0,
                "winning_trades": 0,
                "net_pnl": 0.0
            }
        yearly_dict[year_str]["trades_count"] += 1
        if t['net_pnl'] > 0:
            yearly_dict[year_str]["winning_trades"] += 1
        yearly_dict[year_str]["net_pnl"] += t['net_pnl']

    yearly_breakdown = []
    for y in sorted(yearly_dict.keys()):
        item = yearly_dict[y]
        cnt = item["trades_count"]
        w_cnt = item["winning_trades"]
        win_rate = round((w_cnt / cnt * 100.0), 1) if cnt > 0 else 0.0
        ret_contrib_pct = round((item["net_pnl"] / initial_capital) * 100.0, 2)
        yearly_breakdown.append({
            "Năm": item["year"],
            "Số lệnh": cnt,
            "Lệnh thắng": w_cnt,
            "Tỷ lệ thắng (%)": win_rate,
            "Lợi nhuận ròng (VNĐ)": round(item["net_pnl"], 0),
            "Tỷ suất sinh lời (%)": ret_contrib_pct
        })

    return {
        "total_return_pct": total_return_pct,
        "benchmark_return_pct": benchmark_return_pct,
        "win_rate_pct": win_rate_pct,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_drawdown_pct,
        "sharpe_ratio": sharpe_ratio,
        "total_trades": total_trades,
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "final_equity": round(final_equity, 0),
        "trades": trades,
        "equity_curve": equity_df[['time', 'equity']],
        "yearly_breakdown": yearly_breakdown
    }
