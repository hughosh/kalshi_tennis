"""
Catan AI Strategy Module
Different strategies for placing settlements and making decisions.
"""
from typing import List, Optional, Dict, Tuple
from .board import CatanBoard, Resource, Vertex, BuildingType
from .player import Player


class Strategy:
    """Base strategy class."""

    def choose_initial_settlement(self, board: CatanBoard, player: Player,
                                   taken: List[int]) -> int:
        raise NotImplementedError

    def choose_initial_road(self, board: CatanBoard, player: Player,
                             settlement_vid: int) -> int:
        raise NotImplementedError

    def take_turn(self, board: CatanBoard, player: Player,
                  all_players: List[Player]) -> List[str]:
        raise NotImplementedError


class HighestProbabilityStrategy(Strategy):
    """
    Greedily picks the highest-probability vertices.
    Focuses on ore+wheat for city upgrades (fastest VP path).
    """

    def choose_initial_settlement(self, board: CatanBoard, player: Player,
                                   taken: List[int]) -> int:
        valid = [v for v in board.vertices
                 if v not in taken and _is_valid_placement(board, v, taken)]
        if not valid:
            return list(board.vertices.keys())[0]

        return max(valid, key=lambda v: self._score_vertex(board, v, player.settlements))

    def _score_vertex(self, board: CatanBoard, vid: int,
                       existing_settlements: List[int]) -> float:
        v = board.vertices[vid]
        score = board.get_vertex_score(vid)

        # Check what resources we already have
        existing_resources = set()
        for s_vid in existing_settlements:
            for hex_id in board.vertices[s_vid].adjacent_hexes:
                h = board.hexes[hex_id]
                if h.resource != Resource.DESERT:
                    existing_resources.add(h.resource)

        # Bonus for new resource types
        new_resources = set()
        for hex_id in v.adjacent_hexes:
            h = board.hexes[hex_id]
            if h.resource != Resource.DESERT:
                new_resources.add(h.resource)

        novel = new_resources - existing_resources
        score += len(novel) * 2.0

        # Bonus for ore and wheat (city building)
        for hex_id in v.adjacent_hexes:
            h = board.hexes[hex_id]
            if h.resource in (Resource.ORE, Resource.WHEAT) and h.number:
                score += h.probability * 10

        return score

    def choose_initial_road(self, board: CatanBoard, player: Player,
                             settlement_vid: int) -> int:
        v = board.vertices[settlement_vid]
        if not v.adjacent_edges:
            return list(board.edges.keys())[0]

        # Road toward best unexplored vertex
        best_edge = None
        best_score = -1
        for eid in v.adjacent_edges:
            edge = board.edges[eid]
            if edge.has_road:
                continue
            other_vid = edge.vertices[0] if edge.vertices[1] == settlement_vid else edge.vertices[1]
            s = board.get_vertex_score(other_vid)
            if s > best_score:
                best_score = s
                best_edge = eid
        return best_edge if best_edge is not None else v.adjacent_edges[0]

    def take_turn(self, board: CatanBoard, player: Player,
                  all_players: List[Player]) -> List[str]:
        actions = []

        # Priority: city > settlement > dev card > road > trade
        if player.can_build_city():
            # Upgrade the settlement on the highest-scoring vertex
            best_vid = max(player.settlements, key=lambda v: board.get_vertex_score(v))
            player.spend_city()
            player.settlements.remove(best_vid)
            player.cities.append(best_vid)
            board.vertices[best_vid].building = BuildingType.CITY
            player.victory_points = player.calculate_vp()
            actions.append(f"built city at {best_vid}")

        elif player.can_build_settlement():
            valid = board.get_valid_settlement_spots(player.settlements + player.cities)
            # Prefer connected spots (reachable by roads)
            reachable = _reachable_vertices(board, player)
            valid_reachable = [v for v in valid if v in reachable]
            if valid_reachable:
                best_vid = max(valid_reachable,
                               key=lambda v: self._score_vertex(board, v, player.settlements))
                player.spend_settlement()
                player.settlements.append(best_vid)
                board.vertices[best_vid].building = BuildingType.SETTLEMENT
                board.vertices[best_vid].player_id = player.player_id
                player.victory_points = player.calculate_vp()
                actions.append(f"built settlement at {best_vid}")

        elif player.can_buy_dev_card():
            player.spend_dev_card()
            card = _draw_dev_card(board)
            player.dev_cards.append(card)
            if card == "knight":
                player.knights_played += 1
            actions.append(f"bought dev card: {card}")

        elif player.can_build_road():
            # Extend road toward a good vertex
            frontier = _road_frontier(board, player)
            if frontier:
                eid = frontier[0]
                player.spend_road()
                player.roads.append(eid)
                board.edges[eid].road_owner = player.player_id
                actions.append(f"built road {eid}")

        else:
            # Try to trade
            _try_trade(board, player, actions)

        return actions


class CityRushStrategy(Strategy):
    """
    Focuses on ore+wheat production for fast city upgrades.
    Highest VP-per-turn for mid-late game.
    """

    def choose_initial_settlement(self, board: CatanBoard, player: Player,
                                   taken: List[int]) -> int:
        valid = [v for v in board.vertices
                 if v not in taken and _is_valid_placement(board, v, taken)]
        if not valid:
            return list(board.vertices.keys())[0]

        return max(valid, key=lambda v: self._city_score(board, v, player.settlements))

    def _city_score(self, board: CatanBoard, vid: int,
                    existing: List[int]) -> float:
        v = board.vertices[vid]
        score = 0.0
        resources = {}

        for hex_id in v.adjacent_hexes:
            h = board.hexes[hex_id]
            if h.resource != Resource.DESERT and h.number:
                prob = h.probability * 36  # pips
                resources[h.resource] = resources.get(h.resource, 0) + prob
                if h.resource in (Resource.ORE, Resource.WHEAT):
                    score += prob * 2.5  # strong bonus
                else:
                    score += prob * 0.5

        # Port bonus
        if v.port:
            score += 3.0

        # Diversity penalty if we have 2 settlements and they're duplicating
        if existing:
            existing_res = set()
            for s_vid in existing:
                for hex_id in board.vertices[s_vid].adjacent_hexes:
                    h = board.hexes[hex_id]
                    existing_res.add(h.resource)
            new_res = set(h_res for hid in v.adjacent_hexes
                          for h_res in [board.hexes[hid].resource]
                          if h_res != Resource.DESERT)
            novel = new_res - existing_res
            score += len(novel) * 1.5

        return score

    def choose_initial_road(self, board: CatanBoard, player: Player,
                             settlement_vid: int) -> int:
        v = board.vertices[settlement_vid]
        if not v.adjacent_edges:
            return list(board.edges.keys())[0]

        best_edge = None
        best_score = -1
        for eid in v.adjacent_edges:
            edge = board.edges[eid]
            if edge.has_road:
                continue
            other_vid = edge.vertices[0] if edge.vertices[1] == settlement_vid else edge.vertices[1]
            s = self._city_score(board, other_vid, player.settlements)
            if s > best_score:
                best_score = s
                best_edge = eid
        return best_edge if best_edge is not None else v.adjacent_edges[0]

    def take_turn(self, board: CatanBoard, player: Player,
                  all_players: List[Player]) -> List[str]:
        actions = []

        # City > dev card > settlement > road > trade
        if player.can_build_city():
            best_vid = max(player.settlements, key=lambda v: board.get_vertex_score(v))
            player.spend_city()
            player.settlements.remove(best_vid)
            player.cities.append(best_vid)
            board.vertices[best_vid].building = BuildingType.CITY
            player.victory_points = player.calculate_vp()
            actions.append(f"built city at {best_vid}")

        elif player.can_buy_dev_card():
            player.spend_dev_card()
            card = _draw_dev_card(board)
            player.dev_cards.append(card)
            if card == "knight":
                player.knights_played += 1
            actions.append(f"bought dev card: {card}")

        elif player.can_build_settlement():
            valid = board.get_valid_settlement_spots(player.settlements + player.cities)
            reachable = _reachable_vertices(board, player)
            valid_reachable = [v for v in valid if v in reachable]
            if valid_reachable:
                best_vid = max(valid_reachable,
                               key=lambda v: self._city_score(board, v, player.settlements))
                player.spend_settlement()
                player.settlements.append(best_vid)
                board.vertices[best_vid].building = BuildingType.SETTLEMENT
                board.vertices[best_vid].player_id = player.player_id
                player.victory_points = player.calculate_vp()
                actions.append(f"built settlement at {best_vid}")

        elif player.can_build_road():
            frontier = _road_frontier(board, player)
            if frontier:
                eid = frontier[0]
                player.spend_road()
                player.roads.append(eid)
                board.edges[eid].road_owner = player.player_id
                actions.append(f"built road {eid}")
        else:
            _try_trade(board, player, actions)

        return actions


class PortTraderStrategy(Strategy):
    """
    Focuses on getting port access and trading efficiently.
    Good for converting surplus resources.
    """

    def choose_initial_settlement(self, board: CatanBoard, player: Player,
                                   taken: List[int]) -> int:
        valid = [v for v in board.vertices
                 if v not in taken and _is_valid_placement(board, v, taken)]
        if not valid:
            return list(board.vertices.keys())[0]

        return max(valid, key=lambda v: self._port_score(board, v))

    def _port_score(self, board: CatanBoard, vid: int) -> float:
        v = board.vertices[vid]
        score = board.get_vertex_score(vid)
        if v.port:
            score += 5.0  # Strong port bonus
        return score

    def choose_initial_road(self, board: CatanBoard, player: Player,
                             settlement_vid: int) -> int:
        v = board.vertices[settlement_vid]
        if not v.adjacent_edges:
            return list(board.edges.keys())[0]

        # Road toward a port
        best_edge = None
        best_score = -1
        for eid in v.adjacent_edges:
            edge = board.edges[eid]
            if edge.has_road:
                continue
            other_vid = edge.vertices[0] if edge.vertices[1] == settlement_vid else edge.vertices[1]
            s = self._port_score(board, other_vid)
            if s > best_score:
                best_score = s
                best_edge = eid
        return best_edge if best_edge is not None else v.adjacent_edges[0]

    def take_turn(self, board: CatanBoard, player: Player,
                  all_players: List[Player]) -> List[str]:
        actions = []

        # Trade first to get what we need
        _try_trade(board, player, actions)

        if player.can_build_city():
            best_vid = max(player.settlements, key=lambda v: board.get_vertex_score(v))
            player.spend_city()
            player.settlements.remove(best_vid)
            player.cities.append(best_vid)
            board.vertices[best_vid].building = BuildingType.CITY
            player.victory_points = player.calculate_vp()
            actions.append(f"built city at {best_vid}")

        elif player.can_build_settlement():
            valid = board.get_valid_settlement_spots(player.settlements + player.cities)
            reachable = _reachable_vertices(board, player)
            valid_reachable = [v for v in valid if v in reachable]
            if valid_reachable:
                # Prefer port vertices
                best_vid = max(valid_reachable, key=lambda v: self._port_score(board, v))
                player.spend_settlement()
                player.settlements.append(best_vid)
                board.vertices[best_vid].building = BuildingType.SETTLEMENT
                board.vertices[best_vid].player_id = player.player_id
                player.victory_points = player.calculate_vp()
                actions.append(f"built settlement at {best_vid}")

        elif player.can_build_road():
            frontier = _road_frontier(board, player)
            if frontier:
                eid = frontier[0]
                player.spend_road()
                player.roads.append(eid)
                board.edges[eid].road_owner = player.player_id
                actions.append(f"built road {eid}")

        return actions


class LongestRoadStrategy(Strategy):
    """
    Aims for the Longest Road special card (2 VP).
    """

    def choose_initial_settlement(self, board: CatanBoard, player: Player,
                                   taken: List[int]) -> int:
        valid = [v for v in board.vertices
                 if v not in taken and _is_valid_placement(board, v, taken)]
        if not valid:
            return list(board.vertices.keys())[0]

        # Find central, high-connectivity vertices
        return max(valid, key=lambda v: (
            board.get_vertex_score(v) +
            len(board.vertices[v].adjacent_vertices) * 0.5
        ))

    def choose_initial_road(self, board: CatanBoard, player: Player,
                             settlement_vid: int) -> int:
        v = board.vertices[settlement_vid]
        if not v.adjacent_edges:
            return list(board.edges.keys())[0]
        for eid in v.adjacent_edges:
            if not board.edges[eid].has_road:
                return eid
        return v.adjacent_edges[0]

    def take_turn(self, board: CatanBoard, player: Player,
                  all_players: List[Player]) -> List[str]:
        actions = []

        # Road > settlement > city > dev card
        if player.can_build_road():
            frontier = _road_frontier(board, player)
            if frontier:
                eid = frontier[0]
                player.spend_road()
                player.roads.append(eid)
                board.edges[eid].road_owner = player.player_id
                # Check longest road
                road_len = _calculate_road_length(board, player)
                actions.append(f"built road {eid} (road length: {road_len})")

        elif player.can_build_settlement():
            valid = board.get_valid_settlement_spots(player.settlements + player.cities)
            reachable = _reachable_vertices(board, player)
            valid_reachable = [v for v in valid if v in reachable]
            if valid_reachable:
                best_vid = max(valid_reachable, key=lambda v: board.get_vertex_score(v))
                player.spend_settlement()
                player.settlements.append(best_vid)
                board.vertices[best_vid].building = BuildingType.SETTLEMENT
                board.vertices[best_vid].player_id = player.player_id
                player.victory_points = player.calculate_vp()
                actions.append(f"built settlement at {best_vid}")

        elif player.can_build_city():
            best_vid = max(player.settlements, key=lambda v: board.get_vertex_score(v))
            player.spend_city()
            player.settlements.remove(best_vid)
            player.cities.append(best_vid)
            board.vertices[best_vid].building = BuildingType.CITY
            player.victory_points = player.calculate_vp()
            actions.append(f"built city at {best_vid}")

        else:
            _try_trade(board, player, actions)

        return actions


# ============================================================
# Helper Functions
# ============================================================

def _is_valid_placement(board: CatanBoard, vid: int, taken: List[int]) -> bool:
    """Check distance rule: no adjacent occupied vertices."""
    v = board.vertices[vid]
    if v.is_occupied:
        return False
    for adj in v.adjacent_vertices:
        if adj in taken or board.vertices[adj].is_occupied:
            return False
    return True


def _reachable_vertices(board: CatanBoard, player: Player) -> set:
    """Get all vertices reachable from player's road network."""
    reachable = set(player.settlements + player.cities)
    # BFS from settlements/cities along roads
    queue = list(player.settlements + player.cities)
    while queue:
        vid = queue.pop()
        v = board.vertices[vid]
        for eid in v.adjacent_edges:
            edge = board.edges[eid]
            if edge.road_owner == player.player_id:
                other = edge.vertices[0] if edge.vertices[1] == vid else edge.vertices[1]
                if other not in reachable:
                    reachable.add(other)
                    queue.append(other)
    return reachable


def _road_frontier(board: CatanBoard, player: Player) -> List[int]:
    """Get edges where player can build roads (extending existing network)."""
    reachable = _reachable_vertices(board, player)
    candidates = []
    for vid in reachable:
        v = board.vertices[vid]
        for eid in v.adjacent_edges:
            edge = board.edges[eid]
            if not edge.has_road:
                # Score: prefer toward high-value unexplored vertices
                other = edge.vertices[0] if edge.vertices[1] == vid else edge.vertices[1]
                score = board.get_vertex_score(other)
                candidates.append((score, eid))
    candidates.sort(reverse=True)
    return [eid for _, eid in candidates]


def _calculate_road_length(board: CatanBoard, player: Player) -> int:
    """Calculate player's longest road length."""
    player_edges = set(player.roads)
    if not player_edges:
        return 0

    # Build adjacency for player's roads
    road_adj: Dict[int, List[int]] = {}
    for eid in player_edges:
        edge = board.edges[eid]
        v1, v2 = edge.vertices
        if v1 not in road_adj:
            road_adj[v1] = []
        if v2 not in road_adj:
            road_adj[v2] = []
        road_adj[v1].append(v2)
        road_adj[v2].append(v1)

    # DFS to find longest path
    best = [0]

    def dfs(node, visited_edges, length):
        best[0] = max(best[0], length)
        v = board.vertices[node]
        for eid in v.adjacent_edges:
            if eid in player_edges and eid not in visited_edges:
                edge = board.edges[eid]
                other = edge.vertices[0] if edge.vertices[1] == node else edge.vertices[1]
                visited_edges.add(eid)
                dfs(other, visited_edges, length + 1)
                visited_edges.remove(eid)

    for start in road_adj:
        dfs(start, set(), 0)

    return best[0]


DEV_CARD_DECK = (
    ["knight"] * 14 +
    ["road_building"] * 2 +
    ["year_of_plenty"] * 2 +
    ["monopoly"] * 2 +
    ["victory_point"] * 5
)

_deck_copy = DEV_CARD_DECK.copy()
import random
random.shuffle(_deck_copy)
_deck_index = [0]


def _draw_dev_card(board) -> str:
    global _deck_copy, _deck_index
    if _deck_index[0] >= len(_deck_copy):
        _deck_copy = DEV_CARD_DECK.copy()
        random.shuffle(_deck_copy)
        _deck_index[0] = 0
    card = _deck_copy[_deck_index[0]]
    _deck_index[0] += 1
    return card


def _try_trade(board: CatanBoard, player: Player, actions: List[str]):
    """Attempt bank/port trades to get needed resources."""
    # Determine what we need most
    needs = _get_needs(player)
    if not needs:
        return

    for want in needs:
        # Try to trade surplus resources
        surplus = [(r, amt) for r, amt in player.resources.items()
                   if r != Resource.DESERT and r != want]
        surplus.sort(key=lambda x: x[1], reverse=True)

        for give_res, give_amt in surplus:
            rate = player.trade_rate(give_res, board)
            if give_amt >= rate and player.resources[want] < 1:
                player.resources[give_res] -= rate
                player.resources[want] += 1
                actions.append(f"traded {rate}x{give_res.value} -> 1x{want.value}")
                return  # One trade per turn for simplicity


def _get_needs(player: Player) -> List[Resource]:
    """Determine what resources the player needs most."""
    needs = []
    r = player.resources

    # Need for city (ore x3, wheat x2)
    if len(player.settlements) > 0 and len(player.cities) < 4:
        if r[Resource.ORE] < 3:
            needs.append(Resource.ORE)
        if r[Resource.WHEAT] < 2:
            needs.append(Resource.WHEAT)

    # Need for settlement
    if len(player.settlements) < 5:
        for res in [Resource.WOOD, Resource.BRICK, Resource.SHEEP, Resource.WHEAT]:
            if r[res] < 1:
                needs.append(res)

    return list(dict.fromkeys(needs))  # deduplicate
