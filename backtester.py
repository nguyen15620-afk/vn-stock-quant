import pandas as pd
import numpy as np

def run_backtest(df: pd.DataFrame, initial_capital: float = 100000000.0, take_profit_pct: float = 0.0, stop_loss_pct: float = 0.0) -> dict:
    """
    Runs a backtest supporting Stop Loss and Take Profit.
    """
    if df.empty or 'signal' not in df.columns:
        return {}
        
    df = df.copy()
    n = len(df)
    
    positions = np.zeros(n)
    actual_signals = ['Hold'] * n
    
    current_pos = 0
    entry_price = 0.0
    wins = 0
    completed_trades = 0
    
    for i in range(n):
        sig = df['signal'].iloc[i]
        close = df['close'].iloc[i]
        
        if current_pos == 1:
            pnl = (close - entry_price) / entry_price
            
            # Check Stop Loss / Take Profit
            if take_profit_pct > 0 and pnl >= take_profit_pct:
                current_pos = 0
                actual_signals[i] = 'Sell' # TP triggered
                df.at[df.index[i], 'reason'] = f'Chốt lời tự động (+{pnl*100:.1f}%)'
                wins += 1
                completed_trades += 1
                entry_price = 0.0
            elif stop_loss_pct > 0 and pnl <= -stop_loss_pct:
                current_pos = 0
                actual_signals[i] = 'Sell' # SL triggered
                df.at[df.index[i], 'reason'] = f'Cắt lỗ tự động ({pnl*100:.1f}%)'
                completed_trades += 1
                entry_price = 0.0
            elif sig == 'Sell':
                current_pos = 0
                actual_signals[i] = 'Sell'
                if pnl > 0:
                    wins += 1
                completed_trades += 1
                entry_price = 0.0
            else:
                actual_signals[i] = 'Hold'
                
        else:
            if sig == 'Buy':
                current_pos = 1
                entry_price = close
                actual_signals[i] = 'Buy'
            else:
                actual_signals[i] = 'Hold'
                
        positions[i] = current_pos
        
    df['position_target'] = positions
    df['signal'] = actual_signals # Overwrite with actual executed signals
    
    # Position applies to the next day's return
    df['position'] = df['position_target'].shift(1).fillna(0)
    df['asset_return'] = df['close'].pct_change()
    df['strategy_return'] = df['position'] * df['asset_return']
    
    df['cum_market_return'] = (1 + df['asset_return'].fillna(0)).cumprod()
    df['cum_strategy_return'] = (1 + df['strategy_return'].fillna(0)).cumprod()
    
    df['portfolio_value'] = initial_capital * df['cum_strategy_return']
    df['market_portfolio_value'] = initial_capital * df['cum_market_return']
    
    total_return = df['cum_strategy_return'].iloc[-1] - 1
    market_return = df['cum_market_return'].iloc[-1] - 1
    
    win_rate = (wins / completed_trades * 100) if completed_trades > 0 else 0.0
    
    # Calculate Max Drawdown
    df['rolling_max'] = df['portfolio_value'].cummax()
    df['drawdown'] = (df['portfolio_value'] - df['rolling_max']) / df['rolling_max']
    max_drawdown = df['drawdown'].min() * 100
        
    return {
        'total_return_pct': total_return * 100,
        'market_return_pct': market_return * 100,
        'max_drawdown_pct': max_drawdown,
        'total_trades': completed_trades,
        'win_rate_pct': win_rate,
        'df_backtest': df
    }
# Force reload
