"""
Catan Game Engine
"""
from typing import List, Dict, Optional, Tuple
from .board import CatanBoard, Resource, BuildingType
from .player import Player
from .strategy import (
    Strategy, HighestProbabilityStrategy, CityRushStrategy,
    PortTraderStrategy, LongestRoadStrategy,
    _calculate_road_length, _is_valid_placement
)


class CatanGame:
    """
    Full Catan game simulation.
    Handles setup, turns, resource distribution, special cards, and victory.
    """

    WIN_VP = 10
    LONGEST_ROAD_MIN = 5
    LARGEST_ARMY_MIN = 3

    def __init__(self, players: List[Tuple[str, Strategy]], seed: Optional[int] = None):
        self.board = CatanBoard(seed=seed)
        self.players: List[Player] = []
        for i, (name, strategy) in enumerate(players):
            p = Player(player_id=i, name=name, strategy=strategy.__class__.__name__)
            p._strategy = strategy
            self.players.append(p)

        self.turn = 0
        self.round = 0
        self.game_log: List[str] = []
        self.winner: Optional[Player] = None
        self.longest_road_holder: Optional[int] = None  # player_id
        self.largest_army_holder: Optional[int] = None  # player_id

        # Track initial placement choices for analysis
        self.initial_placements: Dict[int, List[Dict]] = {p.player_id: [] for p in self.players}

    def log(self, msg: str):
        self.game_log.append(f"[R{self.round}T{self.turn}] {msg}")

    def setup_phase(self):
        """
        Standard Catan setup: each player places 2 settlements and 2 roads.
        Order: P0, P1, P2, P3, P3, P2, P1, P0 (snake draft)
        """
        self.log("=== SETUP PHASE ===")
        taken_vertices = []

        order = list(range(len(self.players))) + list(reversed(range(len(self.players))))

        for placement_num, player_idx in enumerate(order):
            player = self.players[player_idx]
            strategy = player._strategy

            # Choose settlement
            vid = strategy.choose_initial_settlement(self.board, player, taken_vertices)
            if vid not in self.board.vertices:
                # Fallback to first valid
                valid = [v for v in self.board.vertices
                         if v not in taken_vertices and
                         _is_valid_placement(self.board, v, taken_vertices)]
                vid = valid[0] if valid else 0

            taken_vertices.append(vid)
            player.settlements.append(vid)
            self.board.vertices[vid].building = BuildingType.SETTLEMENT
            self.board.vertices[vid].player_id = player.player_id

            # Choose road
            eid = strategy.choose_initial_road(self.board, player, vid)
            player.roads.append(eid)
            self.board.edges[eid].road_owner = player.player_id

            # Second settlement gets starting resources
            if placement_num >= len(self.players):
                for hex_id in self.board.vertices[vid].adjacent_hexes:
                    h = self.board.hexes[hex_id]
                    if h.resource != Resource.DESERT:
                        player.receive_resources(h.resource, 1)

            # Record placement for analysis
            hex_info = []
            for hex_id in self.board.vertices[vid].adjacent_hexes:
                h = self.board.hexes[hex_id]
                hex_info.append({
                    "resource": h.resource.value,
                    "number": h.number,
                    "probability": round(h.probability * 100, 1)
                })

            self.initial_placements[player.player_id].append({
                "vertex_id": vid,
                "placement_order": placement_num + 1,
                "vertex_score": round(self.board.get_vertex_score(vid), 2),
                "adjacent_hexes": hex_info
            })

            player.victory_points = player.calculate_vp()
            self.log(f"{player.name} placed settlement at vertex {vid} "
                     f"(score={self.board.get_vertex_score(vid):.1f}) "
                     f"and road {eid}")

    def play_turn(self, player: Player) -> bool:
        """Play one turn. Returns True if player won."""
        self.turn += 1

        # Roll dice
        roll = self.board.roll_dice()
        self.log(f"{player.name} rolled {roll}")

        if roll == 7:
            self._handle_robber(player)
        else:
            self._distribute_resources(roll)

        # Player action
        actions = player._strategy.take_turn(self.board, player, self.players)
        for action in actions:
            self.log(f"  {player.name}: {action}")

        # Check special cards
        self._update_special_cards()

        # Update VP
        player.victory_points = player.calculate_vp()
        if self.longest_road_holder == player.player_id:
            player.victory_points += 2
        if self.largest_army_holder == player.player_id:
            player.victory_points += 2

        # Check win condition
        if player.victory_points >= self.WIN_VP:
            self.winner = player
            self.log(f"*** {player.name} WINS with {player.victory_points} VP! ***")
            return True

        return False

    def _distribute_resources(self, roll: int):
        """Give resources to all players with settlements/cities on producing hexes."""
        producing_hexes = self.board.get_producing_hexes(roll)
        for hex_id in producing_hexes:
            h = self.board.hexes[hex_id]
            for vid, v in self.board.vertices.items():
                if hex_id in v.adjacent_hexes and v.player_id is not None:
                    amount = 2 if v.building == BuildingType.CITY else 1
                    player = self.players[v.player_id]
                    player.receive_resources(h.resource, amount)
                    self.log(f"  {player.name} gets {amount}x{h.resource.value} "
                             f"from hex {hex_id} (roll {roll})")

    def _handle_robber(self, active_player: Player):
        """Move robber to the hex with highest opponent production."""
        # Find opponent's best hex
        best_hex = None
        best_score = -1
        for hex_id, h in self.board.hexes.items():
            if h.resource == Resource.DESERT:
                continue
            # Check if any opponent has a settlement here
            for vid, v in self.board.vertices.items():
                if hex_id in v.adjacent_hexes and v.player_id is not None:
                    if v.player_id != active_player.player_id:
                        score = h.probability * 36
                        if score > best_score:
                            best_score = score
                            best_hex = hex_id
                        break

        if best_hex is not None:
            # Remove robber from current hex
            old = self.board.robber_hex
            self.board.hexes[old].has_robber = False
            self.board.hexes[best_hex].has_robber = True
            self.board.robber_hex = best_hex
            self.log(f"  Robber moved to hex {best_hex}")

            # Steal a card from a player on that hex
            for vid, v in self.board.vertices.items():
                if best_hex in v.adjacent_hexes and v.player_id is not None:
                    if v.player_id != active_player.player_id:
                        victim = self.players[v.player_id]
                        stolen = _steal_resource(victim)
                        if stolen:
                            active_player.receive_resources(stolen, 1)
                            self.log(f"  {active_player.name} stole {stolen.value} "
                                     f"from {victim.name}")
                        break

        # Discard half if over 7 cards
        for p in self.players:
            if p.total_resources > 7:
                discard = p.total_resources // 2
                _discard_resources(p, discard)
                self.log(f"  {p.name} discarded {discard} cards")

    def _update_special_cards(self):
        """Update Longest Road and Largest Army holders."""
        # Longest Road
        road_lengths = {}
        for p in self.players:
            road_lengths[p.player_id] = _calculate_road_length(self.board, p)

        max_road = max(road_lengths.values())
        if max_road >= self.LONGEST_ROAD_MIN:
            for pid, length in road_lengths.items():
                if length == max_road:
                    if self.longest_road_holder != pid:
                        self.longest_road_holder = pid
                        self.log(f"  {self.players[pid].name} takes Longest Road ({length})")
                    break

        # Largest Army
        army_sizes = {p.player_id: p.knights_played for p in self.players}
        max_army = max(army_sizes.values())
        if max_army >= self.LARGEST_ARMY_MIN:
            for pid, size in army_sizes.items():
                if size == max_army:
                    if self.largest_army_holder != pid:
                        self.largest_army_holder = pid
                        self.log(f"  {self.players[pid].name} takes Largest Army ({size} knights)")
                    break

    def run(self, max_rounds: int = 150) -> Optional[Player]:
        """Run the full game."""
        self.setup_phase()

        self.round = 1
        while self.round <= max_rounds:
            for player in self.players:
                if self.play_turn(player):
                    return self.winner
            self.round += 1

        # No winner - return leader by VP
        self.log("Game ended by round limit")
        leader = max(self.players, key=lambda p: p.victory_points)
        self.winner = leader
        return leader

    def get_stats(self) -> Dict:
        """Return game statistics."""
        return {
            "winner": self.winner.name if self.winner else None,
            "winner_strategy": self.winner.strategy if self.winner else None,
            "rounds": self.round,
            "turns": self.turn,
            "player_stats": [
                {
                    "name": p.name,
                    "strategy": p.strategy,
                    "vp": p.victory_points,
                    "settlements": len(p.settlements),
                    "cities": len(p.cities),
                    "roads": len(p.roads),
                    "knights": p.knights_played,
                    "dev_cards": len(p.dev_cards),
                    "initial_placements": self.initial_placements[p.player_id],
                }
                for p in self.players
            ]
        }


def _steal_resource(victim: Player) -> Optional[Resource]:
    """Steal a random resource from victim."""
    available = [r for r, amt in victim.resources.items()
                 if r != Resource.DESERT and amt > 0]
    if not available:
        return None
    import random
    res = random.choice(available)
    victim.resources[res] -= 1
    return res


def _discard_resources(player: Player, amount: int):
    """Discard resources (discard most abundant)."""
    for _ in range(amount):
        surplus = [(r, amt) for r, amt in player.resources.items()
                   if r != Resource.DESERT and amt > 0]
        if not surplus:
            break
        surplus.sort(key=lambda x: x[1], reverse=True)
        player.resources[surplus[0][0]] -= 1
