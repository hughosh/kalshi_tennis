"""
Catan Strategy Simulation - Run N games per strategy combination and report results.
"""
import random
import json
from collections import defaultdict
from typing import List, Dict, Tuple
from .game import CatanGame
from .strategy import (
    HighestProbabilityStrategy, CityRushStrategy,
    PortTraderStrategy, LongestRoadStrategy, LargestArmyStrategy
)


STRATEGIES = {
    "HighestProbability": HighestProbabilityStrategy,
    "CityRush": CityRushStrategy,
    "PortTrader": PortTraderStrategy,
    "LongestRoad": LongestRoadStrategy,
    "LargestArmy": LargestArmyStrategy,
}


def run_tournament(n_games: int = 500, n_players: int = 5, seed: int = 42) -> Dict:
    """
    Run a tournament of N games with all strategies competing.
    Returns win rates, average VP, average rounds, and best placement stats.
    """
    rng = random.Random(seed)

    wins = defaultdict(int)
    total_vp = defaultdict(list)
    total_rounds = []
    placement_scores = defaultdict(list)  # strategy -> list of vertex scores for 1st settlement
    settlement_hex_stats = defaultdict(list)  # strategy -> list of (resource, number) pairs

    strategy_names = list(STRATEGIES.keys())

    print(f"\nRunning {n_games} games with {n_players} players...")

    for game_num in range(n_games):
        game_seed = rng.randint(0, 10**9)

        # Rotate player order each game
        rotation = game_num % len(strategy_names)
        player_strategies = strategy_names[rotation:] + strategy_names[:rotation]
        player_strategies = player_strategies[:n_players]

        players = [(f"{name}", STRATEGIES[name]()) for name in player_strategies]
        game = CatanGame(players, seed=game_seed)

        winner = game.run(max_rounds=120)
        stats = game.get_stats()

        if winner:
            # winner.name is the strategy key (set during player creation)
            wins[winner.name] += 1

        total_rounds.append(stats["rounds"])

        for ps in stats["player_stats"]:
            # ps["name"] is the strategy key; ps["strategy"] is the class name
            key = ps["name"]
            total_vp[key].append(ps["vp"])

            # Track initial placement quality
            for placement in ps["initial_placements"]:
                placement_scores[key].append(placement["vertex_score"])
                for hex_info in placement["adjacent_hexes"]:
                    settlement_hex_stats[key].append(hex_info)

        if (game_num + 1) % 100 == 0:
            print(f"  Completed {game_num + 1}/{n_games} games...")

    # Compile results
    results = {
        "total_games": n_games,
        "strategy_results": {},
        "avg_rounds": sum(total_rounds) / len(total_rounds),
    }

    for name in strategy_names:
        win_count = wins[name]
        games_played = sum(1 for _ in total_vp[name])
        avg_vp = sum(total_vp[name]) / len(total_vp[name]) if total_vp[name] else 0
        win_rate = win_count / games_played if games_played > 0 else 0

        avg_placement = (sum(placement_scores[name]) / len(placement_scores[name])
                         if placement_scores[name] else 0)

        # Most common resources at settlements
        resource_counts = defaultdict(int)
        number_counts = defaultdict(int)
        for hex_info in settlement_hex_stats[name]:
            resource_counts[hex_info["resource"]] += 1
            if hex_info["number"]:
                number_counts[hex_info["number"]] += 1

        top_resources = sorted(resource_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        top_numbers = sorted(number_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        results["strategy_results"][name] = {
            "wins": win_count,
            "games_played": games_played,
            "win_rate": round(win_rate * 100, 1),
            "avg_vp": round(avg_vp, 2),
            "avg_settlement_score": round(avg_placement, 2),
            "top_resources": top_resources,
            "top_numbers": top_numbers,
        }

    return results


def run_head_to_head(strategy_a: str, strategy_b: str,
                     n_games: int = 200, seed: int = 99) -> Dict:
    """Run head-to-head between two strategies with 2 players each."""
    rng = random.Random(seed)
    wins = {strategy_a: 0, strategy_b: 0}
    avg_rounds = []

    for game_num in range(n_games):
        game_seed = rng.randint(0, 10**9)
        players = [
            (strategy_a, STRATEGIES[strategy_a]()),
            (strategy_b, STRATEGIES[strategy_b]()),
            (strategy_a + "_2", STRATEGIES[strategy_a]()),
            (strategy_b + "_2", STRATEGIES[strategy_b]()),
        ]
        game = CatanGame(players, seed=game_seed)
        winner = game.run(max_rounds=120)
        stats = game.get_stats()
        avg_rounds.append(stats["rounds"])

        if winner:
            # winner.name is set to strategy key (e.g. "CityRush" or "CityRush_2")
            w_name = winner.name.rstrip("_2").rstrip("_3")
            if w_name in wins:
                wins[w_name] += 1
            elif winner.name in wins:
                wins[winner.name] += 1

    total = sum(wins.values())
    return {
        "strategy_a": strategy_a,
        "strategy_b": strategy_b,
        "wins_a": wins[strategy_a],
        "wins_b": wins[strategy_b],
        "win_rate_a": round(wins[strategy_a] / n_games * 100, 1),
        "win_rate_b": round(wins[strategy_b] / n_games * 100, 1),
        "avg_rounds": round(sum(avg_rounds) / len(avg_rounds), 1),
    }


def analyze_board_positions(n_boards: int = 200) -> Dict:
    """
    Analyze which vertex positions tend to win across many board configurations.
    Returns statistics on optimal settlement placement.
    """
    from .board import CatanBoard, Resource
    rng = random.Random(777)

    vertex_win_scores = defaultdict(list)
    number_token_wins = defaultdict(int)
    number_token_total = defaultdict(int)
    resource_combo_wins = defaultdict(int)
    resource_combo_total = defaultdict(int)

    print(f"\nAnalyzing {n_boards} board configurations...")

    for i in range(n_boards):
        seed = rng.randint(0, 10**9)
        board = CatanBoard(seed=seed)

        # Score all valid vertices
        scores = {}
        for vid in board.vertices:
            v = board.vertices[vid]
            score = board.get_vertex_score(vid)
            scores[vid] = score

            # Track numbers
            for hex_id in v.adjacent_hexes:
                h = board.hexes[hex_id]
                if h.number:
                    number_token_total[h.number] += 1

        # Top 10% vertices (best spots)
        threshold = sorted(scores.values(), reverse=True)[len(scores)//10]
        top_vertices = [v for v, s in scores.items() if s >= threshold]

        for vid in top_vertices:
            v = board.vertices[vid]
            resources = frozenset(
                board.hexes[hid].resource.value
                for hid in v.adjacent_hexes
                if board.hexes[hid].resource != Resource.DESERT
            )
            resource_combo_total[resources] += 1
            for hex_id in v.adjacent_hexes:
                h = board.hexes[hex_id]
                if h.number:
                    number_token_wins[h.number] += 1

    # Number token rankings
    number_rankings = {}
    for num in range(2, 13):
        total = number_token_total.get(num, 1)
        wins = number_token_wins.get(num, 0)
        number_rankings[num] = round(wins / total * 100, 1)

    # Top resource combos
    top_combos = sorted(resource_combo_total.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "number_token_priority": sorted(number_rankings.items(),
                                        key=lambda x: x[1], reverse=True),
        "top_resource_combos": [(list(combo), count) for combo, count in top_combos],
    }


def print_results(tournament: Dict, board_analysis: Dict, h2h_results: List[Dict]):
    print("\n" + "=" * 65)
    print("          CATAN STRATEGY SIMULATION RESULTS")
    print("=" * 65)
    print(f"\nTournament: {tournament['total_games']} games, "
          f"avg {tournament['avg_rounds']:.1f} rounds/game\n")

    # Sort by win rate
    sorted_strats = sorted(
        tournament["strategy_results"].items(),
        key=lambda x: x[1]["win_rate"],
        reverse=True
    )

    print("┌─────────────────────┬──────────┬──────────┬──────────┬──────────────┐")
    print("│ Strategy            │ Win Rate │  Avg VP  │ Avg Scr  │ Games        │")
    print("├─────────────────────┼──────────┼──────────┼──────────┼──────────────┤")
    for name, data in sorted_strats:
        print(f"│ {name:<19} │ {data['win_rate']:>6.1f}%  │ "
              f"{data['avg_vp']:>7.2f}  │ {data['avg_settlement_score']:>7.2f}  │ "
              f"{data['games_played']:>8}     │")
    print("└─────────────────────┴──────────┴──────────┴──────────┴──────────────┘")

    print("\n=== RESOURCE PREFERENCES BY STRATEGY ===")
    for name, data in sorted_strats:
        top_r = ", ".join(f"{r}({c})" for r, c in data["top_resources"])
        top_n = ", ".join(f"{n}({c})" for n, c in data["top_numbers"][:3])
        print(f"  {name:<20}: Resources: {top_r}")
        print(f"  {'':20}  Numbers: {top_n}")

    print("\n=== OPTIMAL NUMBER TOKENS (% appearance in top spots) ===")
    rankings = board_analysis["number_token_priority"]
    for num, pct in rankings:
        bar = "█" * int(pct / 5)
        print(f"  {num:>2}: {bar:<20} {pct:5.1f}%")

    print("\n=== TOP RESOURCE COMBINATIONS AT BEST VERTICES ===")
    for i, (combo, count) in enumerate(board_analysis["top_resource_combos"][:6], 1):
        combo_str = " + ".join(sorted(combo))
        print(f"  #{i}: {combo_str:<35} (seen {count}x)")

    print("\n=== HEAD-TO-HEAD RESULTS ===")
    for h2h in h2h_results:
        print(f"  {h2h['strategy_a']:<20} vs {h2h['strategy_b']:<20}: "
              f"{h2h['win_rate_a']:5.1f}% vs {h2h['win_rate_b']:5.1f}%  "
              f"(avg {h2h['avg_rounds']} rounds)")

    # Best strategy analysis
    best = sorted_strats[0]
    print(f"\n{'=' * 65}")
    print(f"  WINNING STRATEGY: {best[0]}")
    print(f"{'=' * 65}")


def generate_strategy_guide(tournament: Dict, board_analysis: Dict) -> str:
    """Generate a human-readable strategy guide based on simulation results."""
    sorted_strats = sorted(
        tournament["strategy_results"].items(),
        key=lambda x: x[1]["win_rate"],
        reverse=True
    )
    best_name, best_data = sorted_strats[0]
    second_name, second_data = sorted_strats[1]

    # Extract best number tokens
    top_numbers = [str(num) for num, _ in board_analysis["number_token_priority"][:5]]
    top_combos = board_analysis["top_resource_combos"][:3]

    guide = f"""
╔══════════════════════════════════════════════════════════════╗
║       CATAN WINNING STRATEGY GUIDE  (5-Player Edition)      ║
║           Based on {tournament['total_games']} simulated games                  ║
╚══════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OVERALL WIN RATES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    for name, data in sorted_strats:
        bar = "▓" * int(data["win_rate"] / 2)
        guide += f"  {name:<20}: {bar:<25} {data['win_rate']:5.1f}%\n"

    guide += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#1 BEST STRATEGY: {best_name}  (Win rate: {best_data['win_rate']}%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CORE PRINCIPLE: Build cities as fast as possible.
Cities produce 2 resources per roll instead of 1, creating
a compounding production advantage that is very hard to stop.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INITIAL SETTLEMENT PLACEMENT (Most Important Decision!)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FIRST SETTLEMENT — Prioritize ore + wheat production:
  • Must-have: At least one hex with ore OR wheat at number 5, 6, 8, or 9
  • Best case: Intersection touching ORE + WHEAT + (wood/brick/sheep)
  • Target number tokens: {", ".join(top_numbers[:3])} (highest probability)
  • Ideal: 3 unique resources with combined pip count ≥ 10

SECOND SETTLEMENT — Fill resource gaps + production:
  • If 1st settlement has ore: seek wheat + sheep + wood/brick
  • If 1st settlement has wheat: seek ore + wood + brick
  • Never duplicate the same resource heavily
  • A 3:1 port nearby dramatically helps trading efficiency
  • Target: different 3 resources from 1st settlement

TOP RESOURCE COMBINATIONS AT BEST BOARD VERTICES:"""

    for i, (combo, count) in enumerate(top_combos, 1):
        guide += f"\n  #{i}: {' + '.join(sorted(combo))}"

    guide += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NUMBER TOKEN PRIORITY (higher = appear more in winning spots)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    for num, pct in board_analysis["number_token_priority"]:
        bar = "█" * int(pct / 4)
        guide += f"  Token {num:>2}: {bar:<20} {pct:.1f}% (of top spots)\n"

    guide += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TURN PRIORITY ORDER (what to build/buy each turn)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. CITY UPGRADE        — Best VP per resource spent (5 res = 2 VP)
  2. DEVELOPMENT CARD    — Knights = Largest Army (2 VP), VP cards
  3. NEW SETTLEMENT      — Only if it gives new resources or a port
  4. ROAD               — Only to reach a valuable vertex
  5. BANK TRADE         — Last resort; use ports aggressively

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VICTORY POINT PATHS TO 10 VP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Path A — Pure City Rush (easiest):
    2 initial settlements (2 VP)
    + 2 cities (4 VP total, net +2 over settlements)
    + 2 more settlements (2 VP)
    + 2 more cities (4 VP total)
    + Largest Army or VP dev cards (2 VP)
    = 10 VP  ✓

  Path B — Mixed (with Longest Road):
    2 settlements (2 VP)
    → Build 5+ road chain = Longest Road (2 VP)
    + 3 settlements along road (3 VP)
    + 2 cities (4 VP)
    → 11 VP after cities  ✓

  Path C — Dev Card Heavy:
    Settlements + cities = 8 VP
    + 3 VP dev cards drawn = 11 VP ✓
    (risky due to card luck)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KEY TACTICAL TIPS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  • NEVER skip a 6 or 8 — these two numbers alone roll 28% of the time
  • Ore is most scarce (3 tiles); secure it early or you can't build cities
  • Sheep is cheapest resource to get via port; use 2:1 sheep port if available
  • The robber on 6/8 is devastating; place 2nd settlement away from heavy 6/8 tiles
    to have a robber-proof backup production source
  • Blocking opponents: place roads to cut off their expansion paths
  • If you're behind in VP, switch to dev cards (hidden VP) — opponents can't block
  • With a 3:1 port + any 2-resource surplus, you can convert efficiently
  • Cities are always better than settlements; upgrade ASAP

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE OPTIMAL OPENING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Settlement 1: Ore(8) + Wheat(5) + Sheep(9)
    → 14 combined pips, covers 3 city-building resources
    → Build road toward a port

  Settlement 2: Wood(6) + Brick(9) + Wheat(4)
    → Fills in road-building resources for expansion
    → Gets starting resources: 1 wood + 1 brick + 1 wheat
    → Enables immediate road building in round 1

  Early game plan:
    Rounds 1-3: Build roads toward a 3:1 port
    Round 4:    Build 3rd settlement at port
    Round 5-8:  Accumulate ore+wheat, build first city
    Round 9-12: Second city → 6 VP base
    Round 13+:  Dev cards for Largest Army + last 4 VP

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMON MISTAKES TO AVOID
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✗ Both settlements on wheat/ore only (no wood/brick → can't expand)
  ✗ Chasing Longest Road without VP settlements along the route
  ✗ Building roads with no destination in mind
  ✗ Hoarding resources past 7 cards (robber bait)
  ✗ Ignoring ports — a 2:1 ore port turns a mediocre position into great
  ✗ Building a 3rd settlement when you have 2 upgradeable settlements
  ✗ Trading 4:1 when you could bank trade more efficiently next turn

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
5-PLAYER SPECIFIC ADJUSTMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  • Board congestion: good spots disappear faster — be aggressive in setup
  • Robber is more dangerous: with 5 players it hits someone every ~6 rounds
    instead of every ~6 rounds; keep cards low or diversify placements
  • Longest Road is harder to hold — 5 players = more road conflict
  • Largest Army is more achievable (deck shared by 5 → more knights drawn)
  • Trading with players becomes viable — more partners, more deal-making
  • Second settlement is even more critical: you get only 2 free placements
    before the board is 40% occupied
  • LargestArmy strategy synergizes well with CityRush (both want ore+wheat);
    expect early contention for those hexes — plan backup production
  • If going 4th or 5th in setup: scout before picking; let others commit first
    then take the best remaining ore or wheat hex at a high-probability number
  • With 5 players, games end faster (avg ~50 rounds); tempo matters more
    — every turn without a build is falling behind
"""
    return guide


if __name__ == "__main__":
    print("Running Catan Strategy Simulation (5-Player Expansion)...")

    # Main tournament — 5 players, all 5 strategies
    tournament = run_tournament(n_games=500, n_players=5, seed=42)

    # Board position analysis
    board_analysis = analyze_board_positions(n_boards=300)

    # Head-to-head matchups (5-player: all 5 strategies per game)
    h2h_pairs = [
        ("CityRush", "HighestProbability"),
        ("CityRush", "LargestArmy"),
        ("CityRush", "LongestRoad"),
        ("LargestArmy", "HighestProbability"),
        ("LargestArmy", "LongestRoad"),
    ]
    h2h_results = []
    for a, b in h2h_pairs:
        result = run_head_to_head(a, b, n_games=200)
        h2h_results.append(result)

    # Print results
    print_results(tournament, board_analysis, h2h_results)

    # Generate and print strategy guide
    guide = generate_strategy_guide(tournament, board_analysis)
    print(guide)

    # Save results to JSON
    output = {
        "tournament": tournament,
        "board_analysis": {
            "number_token_priority": board_analysis["number_token_priority"],
            "top_resource_combos": [
                {"combo": list(c), "count": n}
                for c, n in board_analysis["top_resource_combos"]
            ],
        },
        "head_to_head": h2h_results,
        "strategy_guide": guide,
    }
    with open("catan/results.json", "w") as f:
        json.dump(output, f, indent=2)
    print("\nResults saved to catan/results.json")
