import pandas as pd
import numpy as np

def run_backtest(df: pd.DataFrame, initial_capital: float = 100000000.0) -> dict:
    """
    Runs a simple vectorized backtest for the Vietnam market (no short selling).
    Strategy:
        - Enter LONG at the OPEN of the NEXT DAY if Signal == 'Buy'
        - Exit to CASH at the OPEN of the NEXT DAY if Signal == 'Sell'
        - 'Hold' maintains the current state.
    """
    if df.empty or 'signal' not in df.columns:
        return {}
        
    df = df.copy()
    
    # 1. Forward fill position state (1 = Long, 0 = Flat)
    # Map Buy -> 1, Sell -> 0, Hold -> NaN
    df['position_target'] = np.nan
    df.loc[df['signal'] == 'Buy', 'position_target'] = 1
    df.loc[df['signal'] == 'Sell', 'position_target'] = 0
    
    # Fill forward the state. Assuming we start flat (0)
    df['position_target'] = df['position_target'].ffill().fillna(0)
    
    # We enter the trade at the NEXT day's open. So the actual position we hold on day T is the target from day T-1.
    df['position'] = df['position_target'].shift(1).fillna(0)
    
    # Calculate daily returns of the asset using close prices (for holding) 
    # But for a precise open-to-open return or close-to-close return:
    # Asset daily return = (Close_t - Close_{t-1}) / Close_{t-1}
    df['asset_return'] = df['close'].pct_change()
    
    # Strategy daily return = position_{t} * asset_return_{t}
    # Note: Because position changes at the OPEN of day T, the return on day T 
    # is roughly the return from Open_T to Close_T plus gap if we held it overnight. 
    # For simplicity in vectorized backtest, using close-to-close pct_change is standard.
    df['strategy_return'] = df['position'] * df['asset_return']
    
    # Calculate equity curves
    df['cum_market_return'] = (1 + df['asset_return'].fillna(0)).cumprod()
    df['cum_strategy_return'] = (1 + df['strategy_return'].fillna(0)).cumprod()
    
    # Portfolio value
    df['portfolio_value'] = initial_capital * df['cum_strategy_return']
    df['market_portfolio_value'] = initial_capital * df['cum_market_return']
    
    # Metrics
    total_return = df['cum_strategy_return'].iloc[-1] - 1
    market_return = df['cum_market_return'].iloc[-1] - 1
    
    # Count trades: A trade happens when position changes from 0 to 1
    trade_entries = (df['position'] == 1) & (df['position'].shift(1) == 0)
    total_trades = trade_entries.sum()
    
    # Win rate approximation (count positive return days while holding vs total holding days)
    # For a more accurate trade-by-trade win rate, we'd need an event-driven loop.
    # We will do a simple trade-by-trade approximation here:
    trade_signals = df[trade_entries | ((df['position'] == 0) & (df['position'].shift(1) == 1))]
    
    win_rate = 0.0
    wins = 0
    completed_trades = 0
    
    entry_price = 0
    for idx, row in trade_signals.iterrows():
        if row['position'] == 1:
            entry_price = row['close']
        elif row['position'] == 0 and entry_price > 0:
            exit_price = row['close']
            if exit_price > entry_price:
                wins += 1
            completed_trades += 1
            entry_price = 0
            
    if completed_trades > 0:
        win_rate = (wins / completed_trades) * 100
        
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
