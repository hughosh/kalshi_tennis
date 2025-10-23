# Tennis Game State Markov Chain

A Python implementation of a tennis game scoring model using Markov Chain theory with dynamically priceable edge costs (transition probabilities). This model allows for fine-grained control over transition probabilities to model pressure situations and context-dependent scenarios in tennis games.

## Features

- **Complete State Space**: Models all possible tennis game states including standard scoring, deuce, advantage, and terminal states
- **Dynamic Probability Adjustment**: Fine-grained control over transition probabilities for modeling pressure situations
- **Mathematical Foundation**: Uses absorbing Markov chain theory for exact win probability calculations
- **Simulation Capabilities**: Monte Carlo simulation of game trajectories
- **Player Statistics Integration**: Construct chains from real player serve statistics
- **Visualization**: Generate directed graph visualizations of the Markov chain
- **Comprehensive Testing**: Full test suite with unit tests and integration tests

## Installation

1. Clone or download the repository
2. Install required dependencies:

```bash
pip install -r requirements.txt
```

## Quick Start

```python
from tennis_markov_chain import TennisGameMarkovChain

# Create a Markov chain with 65% server point-win probability
chain = TennisGameMarkovChain(p_server_wins_point=0.65)

# Calculate win probability from start of game
probs = chain.get_win_probability("(0,0)")
print(f"Server wins game: {probs['server']:.2%}")

# Simulate a single game
terminal_state, state_sequence = chain.simulate_game("(0,0)")
print(f"Game result: {terminal_state}")

# Visualize the chain
chain.visualize_chain("tennis_chain.png")
```

## Core Components

### State Representation

Each game state is represented as a tuple `(server_points, receiver_points)` where points follow tennis scoring:
- `0` → Love (0 points)
- `1` → 15 (1 point)  
- `2` → 30 (2 points)
- `3` → 40 (3 points)
- Special states: `deuce`, `advantage_server`, `advantage_receiver`

### State Space

The complete state space includes:
- Standard states: `(0,0)`, `(0,1)`, `(0,2)`, `(0,3)`, `(1,0)`, ..., `(3,3)`
- Deuce state: When both players reach 40 (3,3)
- Advantage states: One point ahead after deuce
- Terminal states: `server_wins`, `receiver_wins`

## Key Methods

### Basic Operations

- `get_win_probability(current_state)`: Calculate win probabilities from any state
- `simulate_game(starting_state)`: Simulate a single game trajectory
- `get_expected_points(starting_state)`: Calculate expected number of points until completion

### Dynamic Probability Control

- `set_point_probability(p)`: Update base server point-win probability
- `set_state_specific_probability(from_state, to_state, probability)`: Fine-grained control over specific transitions

### Advanced Features

- `from_player_stats(serve_stats)`: Construct chain from player statistics
- `compare_scenarios(scenarios)`: Compare win probabilities across different configurations
- `estimate_parameters_from_data(game_data)`: Maximum likelihood estimation from observed data

## Example Usage

### Basic Usage

```python
# Create chain and calculate win probabilities
chain = TennisGameMarkovChain(p_server_wins_point=0.65)
probs = chain.get_win_probability("(0,0)")
print(f"Server: {probs['server']:.2%}, Receiver: {probs['receiver']:.2%}")
```

### Pressure Situations

```python
# Model server struggling under pressure
chain = TennisGameMarkovChain(p_server_wins_point=0.65)

# Reduce server effectiveness on break point
chain.set_state_specific_probability("advantage_receiver", "receiver_wins", 0.8)

# Model clutch serving on game point  
chain.set_state_specific_probability("advantage_server", "server_wins", 0.9)
```

### Player Statistics

```python
# Create chain from player statistics
serve_stats = {
    'first_serve_pct': 0.62,
    'first_serve_win_pct': 0.77,
    'second_serve_win_pct': 0.57
}

chain = TennisGameMarkovChain.from_player_stats(serve_stats)
```

### Simulation Analysis

```python
# Simulate 1000 games
outcomes = []
for _ in range(1000):
    terminal_state, _ = chain.simulate_game()
    outcomes.append(terminal_state)

server_wins = sum(1 for outcome in outcomes if outcome == "server_wins")
print(f"Simulated server win rate: {server_wins/1000:.2%}")
```

## Mathematical Foundation

The model leverages absorbing Markov chain theory:

- **Transient states**: All in-progress game states
- **Absorbing states**: `server_wins` and `receiver_wins`
- **Fundamental matrix**: `N = (I - Q)^(-1)` where Q is transient-to-transient submatrix
- **Absorption probabilities**: `B = N * R` where R is transient-to-absorbing submatrix

This allows exact calculation of win probabilities and expected game length without simulation.

## State Transition Logic

From any non-terminal state:
- If server wins the point → advance server's score
- If receiver wins the point → advance receiver's score

**Standard Scoring Rules:**
- If either player reaches 4 points while opponent has ≤2 points → that player wins
- If both reach 3 points (40-40) → enter deuce
- From deuce: winner of point gets advantage
- From advantage: 
  - If same player wins → game over
  - If opponent wins → return to deuce

## Dynamic Pricing (Edge Costs)

The "price" or "cost" of an edge is its transition probability, which can be dynamically adjusted to model:

**Context-Dependent Probabilities:**
- **Break points** (receiver one point from winning): Lower server win probability
- **Game points** (server one point from winning): Potentially higher server win probability
- **Deuce situations**: May model pressure differently
- **Score-dependent momentum**: Adjust probabilities based on current score

## Testing

Run the comprehensive test suite:

```bash
python test_tennis_markov_chain.py
```

The test suite includes:
- Unit tests for state transition logic
- Transition matrix validation
- Win probability calculations
- Edge cases (deuce sequences, immediate wins)
- Probability bounds validation
- Integration tests

## Examples

Run the example script to see various use cases:

```bash
python example_usage.py
```

This demonstrates:
- Basic usage patterns
- Pressure situation modeling
- Simulation analysis
- Player statistics integration
- Scenario comparison
- Visualization capabilities

## Extensions

This base model can be extended to:
- **Set-level Markov chains**: Model entire sets with game scores as states
- **Match-level chains**: Include set scores and match outcomes
- **Player-specific models**: Different chains for different players/matchups
- **Surface adjustments**: Vary probabilities by court surface
- **Fatigue modeling**: Decrease point-win probability as game/set progresses

## Dependencies

- `numpy`: Matrix operations and numerical computations
- `scipy`: Solving linear systems for absorbing Markov chains
- `networkx`: Graph representation and algorithms
- `matplotlib`: Visualization
- `pandas`: Data analysis and scenario comparison

## Performance Considerations

- Transition matrix is cached to avoid recalculation
- Uses sparse matrices for large state spaces (if extending to sets/matches)
- Vectorized operations where possible
- Efficient matrix algebra for exact calculations

## License

This project is open source and available under the MIT License.
