# Tennis Match Markov Chain for Kalshi Trading

A comprehensive Python system for identifying profitable trading opportunities on Kalshi tennis prediction markets using hierarchical Markov chain modeling. The strategy focuses on buying players on their service games, expecting 5-10% price movements as games progress favorably.

## 🎯 Trading Strategy Overview

### Core Insight
Service games in tennis have asymmetric pricing dynamics:
- Markets often underprice server advantage at game start
- As server wins points (0-0 → 15-0 → 30-0), their match-win probability increases
- This creates profitable exit opportunities without holding to game completion

### Target Markets
- Kalshi tennis match winner markets
- Focus on live in-play trading during service games
- Entry: Start of service game (0-0)
- Exit: After favorable point progression (target 5-10% price movement)

## 🏗️ System Architecture

### Hierarchical Markov Chain Structure

**Level 1: Point-in-Game States**
- Standard tennis scoring: `(server_points, receiver_points)`
- Deuce, advantage states, terminal game states

**Level 2: Game-in-Set States**
- Format: `(server_games, receiver_games, current_game_state, server_serving)`
- Includes tiebreak states

**Level 3: Set-in-Match States**
- Format: `(server_sets, receiver_sets, current_set_state)`
- Complete match state representation

### Core Components

1. **MatchState**: Complete hierarchical state representation
2. **HierarchicalTennisMarkov**: Multi-level Markov chain with exact probability calculations
3. **ContextualProbabilityAdjuster**: Pressure/momentum/fatigue adjustments
4. **KalshiTradingStrategy**: Entry/exit logic and position management
5. **LiveMatchTracker**: Real-time state updates from data feeds
6. **KalshiConnector**: API integration for market data and orders
7. **TennisKalshiBot**: Main trading bot orchestrating all components
8. **Backtester**: Strategy validation on historical data

## 🚀 Quick Start

### Installation

1. Clone the repository
2. Set up virtual environment:
```bash
python -m venv tennis_env
source tennis_env/bin/activate  # On Windows: tennis_env\Scripts\activate
pip install -r requirements.txt
```

### Basic Usage

```python
from tennis_match_markov import MatchState, HierarchicalTennisMarkov, PlayerParams, MatchFormat
from kalshi_trading_strategy import KalshiTradingStrategy, MarketData

# Create hierarchical Markov model
model = HierarchicalTennisMarkov(MatchFormat.BEST_OF_3)

# Set player parameters
djokovic_params = PlayerParams(
    name="Djokovic",
    base_serve_prob=0.68,
    base_return_prob=0.38
)
model.set_player_parameters("Djokovic", djokovic_params)

# Create trading strategy
strategy = KalshiTradingStrategy(
    markov_model=model,
    entry_threshold=0.02,  # 2% edge to enter
    exit_threshold=0.07,   # 7% target profit
    stop_loss_threshold=0.03  # 3% stop loss
)

# Evaluate trading opportunity
state = MatchState(sets=(0, 0), games=(0, 0), points=(0, 0), server_serving=True)
market_data = MarketData(
    match_id="djokovic_sinner",
    player1="Djokovic",
    player2="Sinner",
    player1_yes_price=0.62,  # Market underprices Djokovic
    player2_yes_price=0.38,
    # ... other fields
)

signal = strategy.evaluate_service_game_opportunity(state, market_data)
if signal:
    print(f"Trade signal: {signal.player} at {signal.entry_price}")
```

## 📊 Key Features

### Dynamic Probability Adjustment
The system adjusts point-win probabilities based on:

**Score-Based Pressure:**
- Break points: -2 to -5% server win probability
- Game points: +1 to +3% server win probability  
- Set points: ±3 to ±8% depending on who's serving
- Match points: ±5 to ±15%

**Momentum:**
- Track recent point/game/set outcomes
- Adjust probabilities up to ±3% for sustained runs

**Fatigue:**
- Long matches (>3 hours): -2% serve effectiveness
- Fifth set: Additional -1 to -3% for both players

### Trading Strategy Implementation

**Entry Conditions (Service Game Start):**
```python
def find_service_game_entry(self, state: MatchState, market: MarketData) -> Optional[Trade]:
    # 1. Calculate server's true match-win probability
    model_prob = self.markov_model.get_match_win_probability(state)
    
    # 2. Compare to market price
    edge = model_prob[server] - market.get_yes_price(server)
    
    # 3. If market underprices by > entry_threshold, enter
    if edge > self.entry_threshold:
        return Trade(...)
```

**Exit Conditions:**
- Target profit reached (5-10% price movement)
- Game completed (avoid hold risk)
- Stop-loss hit (position moved against us)
- Market conditions changed unfavorably

### Expected Price Movement Calculation

```python
def calculate_expected_game_movement(self, state: MatchState, server: str) -> float:
    # Simulate likely point progressions
    progressions = [
        ((1, 0), p_win_point),      # 15-0
        ((2, 0), p_win_point**2),   # 30-0
        ((3, 0), p_win_point**3),   # 40-0
        # ... etc
    ]
    
    expected_movement = 0
    for game_score, probability in progressions:
        new_state = state.copy_with_game_score(game_score)
        new_prob = self.markov_model.get_match_win_probability(new_state)[server]
        delta = new_prob - initial_prob
        expected_movement += probability * delta
    
    return expected_movement
```

## 🧪 Testing and Validation

### Run Tests
```bash
# Run all tests
python test_tennis_trading_system.py

# Run specific test classes
python -m unittest TestMatchState
python -m unittest TestHierarchicalTennisMarkov
python -m unittest TestKalshiTradingStrategy
```

### Example Usage and Testing
```bash
# Run comprehensive examples
python tennis_trading_example.py
```

### Backtesting
```python
from tennis_kalshi_bot import Backtester, HistoricalMatch

# Create historical match data
historical_match = HistoricalMatch(
    match_id="test_match",
    player1="Djokovic",
    player2="Sinner",
    state_sequence=[...],  # List of MatchState objects
    final_result="Djokovic",
    duration=7200.0
)

# Run backtest
backtester = Backtester(strategy)
results = backtester.simulate_strategy([historical_match])

print(f"Win rate: {results.win_rate:.3f}")
print(f"Total P&L: {results.total_pnl:.4f}")
print(f"Sharpe ratio: {results.sharpe_ratio:.3f}")
```

## 🔧 Configuration

### Strategy Parameters
```python
strategy = KalshiTradingStrategy(
    markov_model=model,
    entry_threshold=0.02,      # Minimum edge to enter (2%)
    exit_threshold=0.07,      # Target profit to exit (7%)
    stop_loss_threshold=0.03, # Stop loss threshold (3%)
    max_position_size=1000.0  # Maximum position size ($)
)
```

### Risk Management
```python
bot = TennisKalshiBot(
    strategy=strategy,
    kalshi_api_key="your_api_key",
    data_feed=your_data_feed
)

# Risk limits
bot.max_total_exposure = 5000.0
bot.max_positions_per_match = 1
bot.max_concurrent_positions = 3
```

## 📈 Performance Metrics

The system tracks comprehensive performance metrics:

- **Win rate**: Percentage of profitable trades
- **Average P&L**: Mean profit/loss per trade
- **Sharpe ratio**: Risk-adjusted returns
- **Maximum drawdown**: Largest peak-to-trough decline
- **Average holding time**: Mean trade duration
- **Fill rate**: Order execution success rate
- **Edge decay**: Model accuracy over time

## 🔌 Data Integration

### Real-Time Data Feeds
```python
from live_tracking import LiveMatchTracker, MockTennisFeed

# Initialize with data feed
feed = MockTennisFeed()  # Use mock for testing
tracker = LiveMatchTracker(feed)

# Start tracking
tracker.start_tracking()

# Get active matches
matches = tracker.get_active_matches()
```

### Kalshi API Integration
```python
from live_tracking import KalshiConnector

# Initialize connector
kalshi = KalshiConnector(api_key="your_kalshi_api_key")

# Get market prices
market_data = kalshi.get_market_prices("match_id")

# Place order
order_id = kalshi.place_order(trade)
```

## 🎮 Live Trading Bot

### Complete Trading Loop
```python
from tennis_kalshi_bot import TennisKalshiBot

# Initialize bot
bot = TennisKalshiBot(
    strategy=strategy,
    kalshi_api_key="your_api_key",
    data_feed=your_data_feed
)

# Start trading
bot.start()

# Monitor performance
performance = bot.get_performance_summary()
print(f"Total trades: {performance['total_trades']}")
print(f"Win rate: {performance['win_rate']:.3f}")
```

### Bot Features
- **Real-time monitoring**: Continuous state tracking and opportunity detection
- **Position management**: Automatic entry/exit based on strategy rules
- **Risk management**: Exposure limits and stop-losses
- **Performance tracking**: Comprehensive metrics and trade logging
- **Error handling**: Robust error recovery and logging

## 📚 Mathematical Foundation

### Absorbing Markov Chain Theory
The system uses absorbing Markov chain mathematics:

- **Transient states**: All in-progress game/set/match states
- **Absorbing states**: Match completion states
- **Fundamental matrix**: `N = (I - Q)^(-1)` where Q is transient-to-transient submatrix
- **Absorption probabilities**: `B = N * R` where R is transient-to-absorbing submatrix

This allows exact calculation of win probabilities and expected game length without simulation.

### Hierarchical Decomposition
```
Match Win Probability = Σ P(Set i) × P(Match Win | Set i)
Set Win Probability = Σ P(Game j) × P(Set Win | Game j)  
Game Win Probability = Σ P(Point k) × P(Game Win | Point k)
```

## 🔍 Advanced Features

### Player Model Calibration
```python
from live_tracking import PlayerModelCalibrator

calibrator = PlayerModelCalibrator()

# Fit from historical data
player_params = calibrator.fit_from_matches("Djokovic", match_history)

# Surface adjustments
adjusted_params = calibrator.adjust_for_surface(player_params, "hard")

# Opponent adjustments
h2h_params = calibrator.adjust_for_opponent(adjusted_params, "Sinner")
```

### Contextual Adjustments
The system automatically adjusts probabilities based on:

- **Pressure situations**: Break points, game points, set points
- **Momentum**: Recent performance streaks
- **Fatigue**: Match duration and set progression
- **Surface**: Hard court, clay, grass adjustments
- **Head-to-head**: Historical matchup data

## 🚨 Risk Management

### Position Limits
- Maximum total exposure across all positions
- Maximum concurrent positions
- Maximum positions per match
- Position sizing based on edge magnitude

### Stop-Losses
- Automatic stop-loss on adverse price movements
- Game completion exits to avoid hold risk
- Market condition monitoring

### Performance Monitoring
- Real-time P&L tracking
- Drawdown monitoring
- Strategy performance metrics
- Alert system for unusual conditions

## 📖 Examples

### Complete Trading Scenario
```python
# Scenario: Djokovic vs Sinner, Djokovic serving at 0-0
state = MatchState(sets=(0, 0), games=(0, 0), points=(0, 0), server_serving=True)

# Market underprices Djokovic
market_data = MarketData(
    player1_yes_price=0.62,  # Market: 62%
    player2_yes_price=0.38
)

# Model says Djokovic has 68% chance
model_probs = model.get_match_win_probability(state, "Djokovic", "Sinner")
# Edge: 68% - 62% = 6% (exceeds 2% threshold)

signal = strategy.evaluate_service_game_opportunity(state, market_data)
# Signal generated: BUY Djokovic at 0.62

# Simulate favorable progression
state_30_0 = MatchState(sets=(0, 0), games=(0, 0), points=(2, 0), server_serving=True)
new_probs = model.get_match_win_probability(state_30_0, "Djokovic", "Sinner")
# New probability: 72% (10% price movement)

# Exit signal: Target profit reached
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ⚠️ Disclaimer

This software is for educational and research purposes only. Trading involves substantial risk of loss and is not suitable for all investors. Past performance does not guarantee future results. Always do your own research and consider your risk tolerance before trading.

## 📞 Support

For questions, issues, or contributions:
- Create an issue on GitHub
- Review the test suite for usage examples
- Check the comprehensive example scripts

---

**Happy Trading! 🎾📈**
