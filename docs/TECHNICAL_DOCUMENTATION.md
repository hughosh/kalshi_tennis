# Tennis Kalshi Trading System - Complete Technical Documentation

## Overview

This system implements a hierarchical Markov chain model for tennis match prediction and automated trading on Kalshi prediction markets. The core strategy focuses on identifying profitable opportunities during service games where the market underprices the server's advantage.

## Core Components

### 1. Tennis Game Markov Chain (`tennis_markov_chain.py`)

**Purpose**: Models individual tennis games as absorbing Markov chains to calculate exact win probabilities.

**Key Features**:
- **State Space**: All possible point combinations (0-0, 15-0, 30-0, 40-0, deuce, advantage)
- **Absorbing States**: "server_wins" and "receiver_wins" 
- **Transition Probabilities**: Based on server's point-winning probability
- **Exact Calculations**: Uses linear algebra to solve for win probabilities without simulation

**Mathematical Foundation**:
```python
# Transition matrix for absorbing Markov chain
# States: (0,0), (15,0), (30,0), (40,0), deuce, advantage_server, advantage_receiver, server_wins, receiver_wins
# Absorbing states: server_wins, receiver_wins
# Non-absorbing states form submatrix Q
# Win probabilities = (I - Q)^(-1) * R
```

**What It Does**:
- Calculates exact probability that server wins the game from any score
- Handles deuce situations correctly (advantage must be won by 2 points)
- Provides dynamic probability adjustment capabilities
- Caches calculations for performance

### 2. Match State Representation (`tennis_match_markov.py`)

**Purpose**: Represents complete tennis match state including sets, games, points, service, and tiebreaks.

**State Components**:
```python
@dataclass
class MatchState:
    sets: tuple          # (player1_sets, player2_sets)
    games: tuple         # (player1_games, player2_games) in current set
    points: tuple        # (player1_points, player2_points) in current game
    server_serving: bool # True if player1 serves, False if player2 serves
    is_tiebreak: bool    # True if in tiebreak
    tiebreak_points: Optional[tuple]  # Tiebreak score if applicable
```

**Key Methods**:
- `is_service_game_start()`: Detects 0-0 situations for trading opportunities
- `copy_with_point_won()`: Advances state when a point is won
- `copy_with_game_complete()`: Handles game completion and service alternation
- `to_key()`: Creates unique string identifier for caching

**What It Does**:
- Tracks complete match progression
- Handles all tennis rules (service alternation, tiebreaks, set completion)
- Provides state transitions for probability calculations
- Enables caching of expensive calculations

### 3. Hierarchical Markov Chain (`tennis_match_markov.py`)

**Purpose**: Combines game-level Markov chains into match-level predictions using hierarchical decomposition.

**Hierarchy**:
```
Match Win Probability
    ↓
Set Win Probabilities (Points → Games → Sets)
    ↓
Game Win Probabilities (Points → Games)
    ↓
Point Win Probabilities (Base probabilities)
```

**Key Components**:
- **Player Parameters**: Base serve/return probabilities, pressure adjustments, fatigue factors
- **Contextual Adjustments**: Modifies probabilities based on match situation
- **Caching System**: Memoizes expensive calculations
- **Dynamic Programming**: Recursive probability calculations

**Mathematical Approach**:
```python
# Match win probability = P(winning current set) * P(winning remaining sets)
# Set win probability = P(winning current game) * P(winning remaining games)
# Game win probability = Calculated from TennisGameMarkovChain
```

**What It Does**:
- Calculates exact match win probabilities from any state
- Handles pressure situations (break points, set points)
- Models momentum and fatigue effects
- Provides probability deltas for trading decisions

### 4. Contextual Probability Adjuster (`tennis_match_markov.py`)

**Purpose**: Modifies base probabilities based on match context, pressure, and momentum.

**Adjustment Factors**:

**Score-Based Pressure**:
- **Break Points**: Server probability decreases by 2-5%
- **Game Points**: Server probability increases by 1-3%
- **Set Points**: Adjustments of ±3-8% based on situation

**Momentum**:
- **Recent Performance**: Weighted average of last 5 games
- **Streak Effects**: Bonus/penalty for winning/losing streaks

**Fatigue**:
- **Match Duration**: Gradual probability decrease over time
- **Set Progression**: Additional fatigue in later sets

**What It Does**:
- Enhances model accuracy by incorporating psychological factors
- Provides more realistic probability estimates
- Captures market inefficiencies in pressure situations

### 5. Trading Strategy (`kalshi_trading_strategy.py`)

**Purpose**: Implements the core trading logic for identifying and executing profitable trades.

**Strategy Overview**:
1. **Entry**: Buy server when market underprices their advantage at service game start
2. **Exit**: Sell when target profit reached, stop loss hit, or game completes
3. **Risk Management**: Position sizing, maximum exposure limits

**Key Methods**:

**Signal Generation**:
```python
def evaluate_service_game_opportunity(state, market_data):
    # Only trade at service game starts (0-0)
    if not state.is_service_game_start():
        return None
    
    # Calculate edge: model_probability - market_price
    edge = model_price - market_price
    
    # Enter if edge exceeds threshold
    if edge > entry_threshold:
        return TradeSignal(...)
```

**Expected Value Calculation**:
- Simulates likely game progressions
- Calculates probability-weighted profit/loss
- Only enters trades with positive expected value

**Risk Management**:
- **Position Sizing**: Based on account size and risk tolerance
- **Stop Losses**: Automatic exit at predetermined loss levels
- **Target Profits**: Take profit at favorable price levels

**What It Does**:
- Identifies profitable trading opportunities
- Manages risk through position sizing and stop losses
- Calculates expected value for trade decisions
- Provides clear entry/exit signals

### 6. Live Match Tracking (`live_tracking.py`)

**Purpose**: Provides real-time match state updates and data feed integration.

**Components**:

**Data Feed Interface**:
```python
class DataFeed(ABC):
    @abstractmethod
    def get_active_matches(self) -> List[str]
    @abstractmethod
    def get_match_data(self, match_id: str) -> Optional[Dict]
```

**Live Match Tracker**:
- Monitors match state changes
- Detects transitions (point, game, set, match)
- Updates trading system with new states
- Handles data feed errors gracefully

**Kalshi API Integration**:
- Fetches market prices
- Places orders
- Manages positions
- Handles authentication (RSA keys)

**What It Does**:
- Provides real-time match data
- Integrates with Kalshi API
- Handles data feed failures
- Enables automated trading

### 7. Score Feed Implementation (`tennis_score_feed.py`, `mock_tennis_feed.py`)

**Purpose**: Provides tennis score data from various sources.

**Mock Feed** (`mock_tennis_feed.py`):
- Simulates realistic tennis matches
- Perfect for testing and development
- No external dependencies
- Generates trading opportunities

**Web Scraping Feed** (`tennis_score_feed.py`):
- Scrapes live scores from FlashScore/ESPN
- Free alternative to paid APIs
- May have rate limits
- Requires internet connection

**What It Does**:
- Provides live tennis score data
- Enables real-time trading
- Falls back to mock data when needed
- Supports multiple data sources

### 8. Main Trading Bot (`tennis_kalshi_bot.py`)

**Purpose**: Orchestrates the complete trading system and manages the main trading loop.

**Components**:

**Trading Loop**:
```python
while True:
    # Get active matches
    matches = score_feed.get_active_matches()
    
    for match_id in matches:
        # Get current state
        state = score_feed.get_match_state(match_id)
        
        # Check for trading opportunities
        signal = strategy.evaluate_service_game_opportunity(state, market_data)
        
        if signal:
            # Execute trade
            position = strategy.execute_trade(signal)
        
        # Check existing positions
        should_exit = strategy.should_exit_trade(position, state, market_data)
        if should_exit:
            # Close position
            strategy.close_position(position)
```

**Performance Tracking**:
- Win rate, average P&L
- Sharpe ratio, maximum drawdown
- Trade statistics and analysis

**Risk Management**:
- Maximum total exposure
- Position limits per match
- Account protection

**What It Does**:
- Runs the complete trading system
- Manages positions and risk
- Tracks performance metrics
- Handles errors and exceptions

### 9. Backtesting System (`tennis_kalshi_bot.py`)

**Purpose**: Validates trading strategies using historical match data.

**Components**:

**Historical Match Simulation**:
- Replays past matches point by point
- Simulates market price movements
- Tests strategy performance
- Calculates risk metrics

**Performance Metrics**:
- **Win Rate**: Percentage of profitable trades
- **Average P&L**: Mean profit per trade
- **Sharpe Ratio**: Risk-adjusted returns
- **Maximum Drawdown**: Largest peak-to-trough loss

**What It Does**:
- Tests strategies on historical data
- Provides performance statistics
- Identifies strategy weaknesses
- Validates before live trading

## Trading Strategy Details

### Core Strategy: Service Game Momentum

**Concept**: Tennis servers have a significant advantage, but markets often underprice this advantage, especially at the start of service games.

**Entry Conditions**:
1. **Service Game Start**: Score is 0-0 (any game)
2. **Market Edge**: Model probability > Market price + threshold
3. **Positive Expected Value**: Trade must be profitable on average

**Exit Conditions**:
1. **Target Profit**: Price moves favorably by target amount
2. **Stop Loss**: Price moves unfavorably by stop amount
3. **Game Completion**: Game ends (natural exit)
4. **Time Limit**: Maximum holding period reached

### Mathematical Foundation

**Edge Calculation**:
```
Edge = Model_Probability - Market_Price
Expected_Value = Edge × Probability_of_Favorable_Outcome
```

**Risk Management**:
```
Position_Size = Account_Balance × Risk_Percentage / Stop_Loss_Amount
Max_Exposure = Account_Balance × Max_Exposure_Percentage
```

### Market Inefficiencies Targeted

1. **Service Advantage Underpricing**: Markets underestimate server advantage
2. **Pressure Situation Mis pricing**: Break points, set points often mispriced
3. **Momentum Ignorance**: Markets don't account for recent performance
4. **Fatigue Discounting**: Late-match fatigue effects ignored

## Implementation Architecture

### Data Flow

```
Live Tennis Scores → Match State Updates → Probability Calculations → Trading Signals → Order Execution → Position Management
```

### Key Design Principles

1. **Exact Calculations**: No Monte Carlo simulation - uses linear algebra
2. **Hierarchical Decomposition**: Points → Games → Sets → Match
3. **Caching**: Expensive calculations cached for performance
4. **Fault Tolerance**: Graceful handling of data feed failures
5. **Risk Management**: Multiple layers of protection

### Performance Optimizations

1. **Memoization**: Cache probability calculations
2. **Batch Processing**: Process multiple matches efficiently
3. **Lazy Evaluation**: Calculate only when needed
4. **Connection Pooling**: Reuse HTTP connections

## Risk Management

### Position-Level Risk

- **Stop Losses**: Automatic exit at predetermined loss levels
- **Position Sizing**: Based on account size and risk tolerance
- **Maximum Positions**: Limit concurrent positions

### Portfolio-Level Risk

- **Total Exposure**: Maximum percentage of account at risk
- **Correlation Limits**: Avoid overexposure to similar matches
- **Drawdown Protection**: Reduce size after losses

### System-Level Risk

- **Data Feed Failures**: Fallback to mock data
- **API Errors**: Graceful error handling
- **Network Issues**: Retry logic and timeouts

## Configuration and Customization

### Strategy Parameters

```python
strategy = KalshiTradingStrategy(
    entry_threshold=0.02,      # 2% edge required to enter
    exit_threshold=0.05,       # 5% target profit
    stop_loss_threshold=0.03,  # 3% stop loss
    max_position_size=100.0    # Maximum position size
)
```

### Player Parameters

```python
player_params = PlayerParams(
    name="Djokovic",
    base_serve_prob=0.68,      # 68% chance of winning point on serve
    base_return_prob=0.38,     # 38% chance of winning point on return
    pressure_serve_adjustment=0.02,  # +2% under pressure
    fatigue_factor=-0.01       # -1% per hour of play
)
```

### Risk Limits

```python
bot = TennisKalshiBot(
    max_total_exposure=5000.0,     # Maximum $5000 exposure
    max_concurrent_positions=3,     # Maximum 3 positions
    max_positions_per_match=1       # Maximum 1 position per match
)
```

## Usage Instructions

### Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Credentials**:
   ```bash
   echo "your_rsa_key" > kalshi_secret_key.txt
   echo "your_email@example.com" > kalshi_username.txt
   ```

3. **Test System**:
   ```bash
   python tennis_trading_demo.py
   ```

### Running Live Trading

1. **Start Trading Bot**:
   ```bash
   python live_tennis_trading.py
   ```

2. **Monitor Performance**:
   - Check console output for signals
   - Monitor position status
   - Review performance metrics

### Backtesting

1. **Run Backtest**:
   ```bash
   python -c "from tennis_kalshi_bot import Backtester; ..."
   ```

2. **Analyze Results**:
   - Review win rate and P&L
   - Check risk metrics
   - Identify improvement opportunities

## Troubleshooting

### Common Issues

1. **No Trading Signals**: Check if edge threshold is too high
2. **API Errors**: Verify credentials and network connection
3. **Data Feed Failures**: System falls back to mock data
4. **Performance Issues**: Check caching and optimization

### Debugging

1. **Enable Verbose Logging**: Add debug prints
2. **Test Individual Components**: Run unit tests
3. **Check Data Quality**: Verify score feed accuracy
4. **Monitor System Resources**: Check memory and CPU usage

## Future Enhancements

### Planned Improvements

1. **Better Score Feeds**: Professional API integration
2. **Machine Learning**: Player performance prediction
3. **Multi-Market**: Support for other prediction markets
4. **Advanced Analytics**: More sophisticated risk metrics

### Research Areas

1. **Market Microstructure**: Order book analysis
2. **Sentiment Analysis**: Social media impact
3. **Weather Effects**: Environmental factors
4. **Injury Modeling**: Player health considerations

## Conclusion

This system provides a comprehensive framework for automated tennis trading on prediction markets. By combining exact mathematical modeling with real-time data feeds and robust risk management, it aims to identify and exploit market inefficiencies in tennis betting markets.

The hierarchical Markov chain approach provides accurate probability estimates, while the contextual adjustments capture psychological factors that markets often miss. The trading strategy focuses on high-probability opportunities with positive expected value, managing risk through careful position sizing and stop losses.

While the system is designed for production use, it includes extensive testing capabilities and fallback mechanisms to ensure reliability. The modular architecture allows for easy customization and enhancement as new data sources and strategies become available.
