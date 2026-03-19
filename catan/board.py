"""
Catan Board Module - Hexagonal board representation
"""
import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from enum import Enum


class Resource(Enum):
    WOOD = "wood"
    BRICK = "brick"
    SHEEP = "sheep"
    WHEAT = "wheat"
    ORE = "ore"
    DESERT = "desert"


class BuildingType(Enum):
    SETTLEMENT = "settlement"
    CITY = "city"


class PortType(Enum):
    THREE_TO_ONE = "3:1"
    WOOD = "2:1 wood"
    BRICK = "2:1 brick"
    SHEEP = "2:1 sheep"
    WHEAT = "2:1 wheat"
    ORE = "2:1 ore"


# Standard Catan tile counts
TILE_COUNTS = {
    Resource.WOOD: 4,
    Resource.BRICK: 3,
    Resource.SHEEP: 4,
    Resource.WHEAT: 4,
    Resource.ORE: 3,
    Resource.DESERT: 1,
}

# Standard number tokens and their probabilities
NUMBER_TOKENS = [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]
ROLL_PROBABILITY = {
    2: 1/36, 3: 2/36, 4: 3/36, 5: 4/36, 6: 5/36,
    7: 6/36, 8: 5/36, 9: 4/36, 10: 3/36, 11: 2/36, 12: 1/36
}


@dataclass
class Hex:
    """A hexagonal tile on the board."""
    hex_id: int
    resource: Resource
    number: Optional[int]  # None for desert
    row: int
    col: int
    has_robber: bool = False

    @property
    def probability(self) -> float:
        if self.number is None:
            return 0.0
        return ROLL_PROBABILITY.get(self.number, 0.0)

    @property
    def pip_count(self) -> int:
        """Number of pips on the token (visual indicator of probability)."""
        pip_map = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 0, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}
        return pip_map.get(self.number, 0) if self.number else 0


@dataclass
class Vertex:
    """A corner/intersection where settlements/cities can be placed."""
    vertex_id: int
    adjacent_hexes: List[int] = field(default_factory=list)  # hex_ids
    adjacent_vertices: List[int] = field(default_factory=list)
    adjacent_edges: List[int] = field(default_factory=list)
    building: Optional[BuildingType] = None
    player_id: Optional[int] = None
    port: Optional[PortType] = None

    @property
    def is_occupied(self) -> bool:
        return self.building is not None


@dataclass
class Edge:
    """An edge between two vertices where roads can be placed."""
    edge_id: int
    vertices: Tuple[int, int] = (0, 0)  # vertex_ids
    adjacent_hexes: List[int] = field(default_factory=list)
    road_owner: Optional[int] = None

    @property
    def has_road(self) -> bool:
        return self.road_owner is not None


class CatanBoard:
    """
    Standard Catan board with 19 hexes arranged in a 3-4-5-4-3 pattern.
    """

    def __init__(self, seed: Optional[int] = None):
        self.rng = random.Random(seed)
        self.hexes: Dict[int, Hex] = {}
        self.vertices: Dict[int, Vertex] = {}
        self.edges: Dict[int, Edge] = {}
        self.robber_hex: int = 0  # starts on desert

        self._build_board()

    def _build_board(self):
        """Build the standard Catan board layout."""
        # Hex grid positions (row, col) for 3-4-5-4-3 layout
        hex_positions = [
            # Row 0 (top, 3 hexes)
            (0, 0), (0, 1), (0, 2),
            # Row 1 (4 hexes)
            (1, 0), (1, 1), (1, 2), (1, 3),
            # Row 2 (middle, 5 hexes)
            (2, 0), (2, 1), (2, 2), (2, 3), (2, 4),
            # Row 3 (4 hexes)
            (3, 0), (3, 1), (3, 2), (3, 3),
            # Row 4 (bottom, 3 hexes)
            (4, 0), (4, 1), (4, 2),
        ]

        # Create tile pool
        tiles = []
        for resource, count in TILE_COUNTS.items():
            tiles.extend([resource] * count)
        self.rng.shuffle(tiles)

        # Assign numbers (skip desert)
        numbers = NUMBER_TOKENS.copy()
        self.rng.shuffle(numbers)

        for i, (row, col) in enumerate(hex_positions):
            resource = tiles[i]
            if resource == Resource.DESERT:
                number = None
                self.robber_hex = i
            else:
                number = numbers.pop(0)
            self.hexes[i] = Hex(i, resource, number, row, col)

        # Build vertex and edge topology
        self._build_topology()
        self._assign_ports()

    def _build_topology(self):
        """
        Build the vertex/edge topology for the hex grid.
        Each hex has 6 vertices and 6 edges.
        This uses a coordinate mapping for the offset hex grid.
        """
        # Map from (hex_id, corner_index) -> vertex_id
        # Corners 0-5 going clockwise from top
        vertex_map: Dict[Tuple, int] = {}
        vertex_id_counter = 0

        # Shared corner definitions for offset hex grid
        # For each hex, define which corners are shared with neighbors
        # We use axial coordinates for neighbor lookup

        # Row offsets for the 3-4-5-4-3 layout
        row_offsets = [0, 3, 7, 12, 16]  # starting hex_id for each row
        row_sizes = [3, 4, 5, 4, 3]

        def hex_at(row, col):
            if row < 0 or row >= 5:
                return None
            if col < 0 or col >= row_sizes[row]:
                return None
            return row_offsets[row] + col

        # For each hex, define 6 corners using a canonical system
        # corners: top-left=0, top-right=1, right=2, bottom-right=3, bottom-left=4, left=5
        # Shared corners between adjacent hexes:
        # right neighbor: shares corners 1,2 with neighbor's 4,5 (but layout-dependent)

        # Simpler approach: assign vertices by scanning all unique positions
        # Each hex corner gets a unique ID unless shared with a neighbor

        hex_corners: Dict[int, List[int]] = {}  # hex_id -> list of 6 vertex_ids

        for hex_id, h in self.hexes.items():
            row, col = h.row, h.col
            corners = []
            for c in range(6):
                corners.append(None)
            hex_corners[hex_id] = corners

        # Corner sharing rules for offset grid (row-based):
        # Each hex has 6 corners indexed 0-5 (top, top-right, bottom-right, bottom, bottom-left, top-left)
        # Neighbors and shared corners:
        # Upper-left neighbor: shares corners 0,5 with neighbor's 3,2? depends on row parity
        # This is complex; use a deterministic vertex assignment instead

        # Use a simpler but correct approach: enumerate all vertices explicitly
        # For a 3-4-5-4-3 board, there are 54 vertices

        # Precompute neighbor relationships
        def get_neighbors(row, col):
            """Get (row, col) of all 6 neighbors."""
            if row == 0:
                # top row, neighbors: right, lower-left, lower-right
                return [(row, col-1), (row, col+1),
                        (row+1, col), (row+1, col+1)]
            elif row == 1:
                return [(row, col-1), (row, col+1),
                        (row-1, col-1), (row-1, col),
                        (row+1, col), (row+1, col+1)]
            elif row == 2:
                return [(row, col-1), (row, col+1),
                        (row-1, col-1), (row-1, col),
                        (row+1, col-1), (row+1, col)]
            elif row == 3:
                return [(row, col-1), (row, col+1),
                        (row-1, col), (row-1, col+1),
                        (row+1, col-1), (row+1, col)]
            else:  # row == 4
                return [(row, col-1), (row, col+1),
                        (row-1, col), (row-1, col+1)]

        # Assign vertices using a set of canonical keys
        # Each vertex is at the intersection of up to 3 hexes
        # Key: frozenset of (row,col) tuples of adjacent hexes

        vertex_hex_groups = []  # list of frozensets

        for hex_id, h in self.hexes.items():
            row, col = h.row, h.col
            # Each hex contributes 6 corners
            # Top corner: shared with (row-1, col-1) and (row-1, col) neighbors
            # Top-right: shared with (row-1, col) and (row, col+1)
            # etc.
            # Use the 6-neighbor corner sharing pattern

            corner_keys = self._get_corner_keys(row, col)
            for key in corner_keys:
                if key not in [vhg for vhg in vertex_hex_groups]:
                    vertex_hex_groups.append(key)

        # Deduplicate
        seen = set()
        unique_groups = []
        for g in vertex_hex_groups:
            fg = frozenset(g)
            if fg not in seen:
                seen.add(fg)
                unique_groups.append(fg)

        # Create vertices
        group_to_vid = {}
        for vid, group in enumerate(unique_groups):
            self.vertices[vid] = Vertex(vid)
            group_to_vid[group] = vid

        # Assign vertices to hexes and vice versa
        for hex_id, h in self.hexes.items():
            row, col = h.row, h.col
            corner_keys = self._get_corner_keys(row, col)
            for key in corner_keys:
                fg = frozenset(key)
                if fg in group_to_vid:
                    vid = group_to_vid[fg]
                    if hex_id not in self.vertices[vid].adjacent_hexes:
                        self.vertices[vid].adjacent_hexes.append(hex_id)

        # Build vertex adjacency (two vertices are adjacent if they share an edge)
        # Two vertices are adjacent if they share exactly 2 hexes in their groups
        # OR if one is on the border and they share 1 hex and are geometrically adjacent
        # Simpler: build edges by finding pairs of vertices that are adjacent on the same hex

        edge_id = 0
        edge_set = set()
        hex_vertices: Dict[int, List[int]] = {}  # hex_id -> ordered list of 6 vertex_ids

        for hex_id, h in self.hexes.items():
            row, col = h.row, h.col
            corner_keys = self._get_corner_keys(row, col)
            vids = []
            for key in corner_keys:
                fg = frozenset(key)
                vids.append(group_to_vid[fg])
            hex_vertices[hex_id] = vids

        # For each hex, create edges between consecutive vertices
        for hex_id, vids in hex_vertices.items():
            for i in range(6):
                v1 = vids[i]
                v2 = vids[(i + 1) % 6]
                key = frozenset([v1, v2])
                if key not in edge_set:
                    edge_set.add(key)
                    edge = Edge(edge_id, (v1, v2))
                    if hex_id not in edge.adjacent_hexes:
                        edge.adjacent_hexes.append(hex_id)
                    self.edges[edge_id] = edge

                    if edge_id not in self.vertices[v1].adjacent_edges:
                        self.vertices[v1].adjacent_edges.append(edge_id)
                    if edge_id not in self.vertices[v2].adjacent_edges:
                        self.vertices[v2].adjacent_edges.append(edge_id)
                    if v2 not in self.vertices[v1].adjacent_vertices:
                        self.vertices[v1].adjacent_vertices.append(v2)
                    if v1 not in self.vertices[v2].adjacent_vertices:
                        self.vertices[v2].adjacent_vertices.append(v1)

                    edge_id += 1
                else:
                    # Find existing edge and add this hex
                    for eid, e in self.edges.items():
                        if frozenset(e.vertices) == key:
                            if hex_id not in e.adjacent_hexes:
                                e.adjacent_hexes.append(hex_id)
                            break

    def _get_corner_keys(self, row: int, col: int) -> List[frozenset]:
        """
        Get 6 corner keys for a hex at (row, col).
        Each key is a frozenset of up to 3 (row,col) tuples identifying the hexes that share that corner.
        Corners are ordered: top, top-right, bottom-right, bottom, bottom-left, top-left
        """
        rc = (row, col)

        # Neighbor positions depend on row position
        # For the 3-4-5-4-3 layout with offset rows:
        # Rows 0,1,2,3,4 with sizes 3,4,5,4,3
        # Upper rows (0,1) shift right relative to lower rows
        # The adjacency pattern:
        # Row 0->1: hex (0,c) is above-left of (1,c) and above-right of (1,c+1)... actually
        # Let me define this carefully.
        #
        # The standard Catan board layout:
        # Row 0 (size 3): cols 0,1,2
        # Row 1 (size 4): cols 0,1,2,3
        # Row 2 (size 5): cols 0,1,2,3,4
        # Row 3 (size 4): cols 0,1,2,3
        # Row 4 (size 3): cols 0,1,2
        #
        # Hex (r,c) has neighbors:
        # For r in {0,1} (upper half, expanding):
        #   upper-left: (r-1, c-1), upper-right: (r-1, c)
        #   lower-left: (r+1, c),   lower-right: (r+1, c+1)
        # For r == 2 (middle):
        #   upper-left: (r-1, c-1), upper-right: (r-1, c)
        #   lower-left: (r+1, c-1), lower-right: (r+1, c)
        # For r in {3,4} (lower half, contracting):
        #   upper-left: (r-1, c),   upper-right: (r-1, c+1)
        #   lower-left: (r+1, c-1), lower-right: (r+1, c)

        def ul(r, c):  # upper-left neighbor
            if r <= 2:
                return (r-1, c-1)
            else:
                return (r-1, c)

        def ur(r, c):  # upper-right neighbor
            if r <= 2:
                return (r-1, c)
            else:
                return (r-1, c+1)

        def ll(r, c):  # lower-left neighbor
            if r < 2:
                return (r+1, c)
            elif r == 2:
                return (r+1, c-1)
            else:
                return (r+1, c-1)

        def lr(r, c):  # lower-right neighbor
            if r < 2:
                return (r+1, c+1)
            elif r == 2:
                return (r+1, c)
            else:
                return (r+1, c)

        def left(r, c): return (r, c-1)
        def right(r, c): return (r, c+1)

        def valid(pos):
            row_sizes = [3, 4, 5, 4, 3]
            r, c = pos
            if r < 0 or r >= 5: return False
            if c < 0 or c >= row_sizes[r]: return False
            return True

        def corner(*positions):
            return frozenset(p for p in positions if valid(p))

        # 6 corners of hex (row, col):
        # 0: top        - shared with ul, ur
        # 1: top-right  - shared with ur, right
        # 2: bottom-right - shared with right, lr
        # 3: bottom     - shared with lr, ll
        # 4: bottom-left - shared with ll, left
        # 5: top-left   - shared with left, ul
        r, c = row, col
        corners = [
            corner(rc, ul(r,c), ur(r,c)),       # top
            corner(rc, ur(r,c), right(r,c)),    # top-right
            corner(rc, right(r,c), lr(r,c)),    # bottom-right
            corner(rc, lr(r,c), ll(r,c)),       # bottom
            corner(rc, ll(r,c), left(r,c)),     # bottom-left
            corner(rc, left(r,c), ul(r,c)),     # top-left
        ]
        return corners

    def _assign_ports(self):
        """Assign ports to coastal vertices."""
        # Standard Catan has 9 ports: 4 generic (3:1) and 5 specific (2:1 each resource)
        port_types = [
            PortType.THREE_TO_ONE, PortType.THREE_TO_ONE,
            PortType.THREE_TO_ONE, PortType.THREE_TO_ONE,
            PortType.WOOD, PortType.BRICK, PortType.SHEEP,
            PortType.WHEAT, PortType.ORE,
        ]

        # Find coastal vertices (those adjacent to only 1 or 2 hexes)
        coastal_vertices = [v for v in self.vertices.values()
                           if len(v.adjacent_hexes) <= 2]

        # Assign ports to pairs of coastal vertices
        self.rng.shuffle(port_types)
        self.rng.shuffle(coastal_vertices)

        assigned = 0
        i = 0
        while assigned < len(port_types) and i < len(coastal_vertices) - 1:
            port = port_types[assigned]
            coastal_vertices[i].port = port
            # Find adjacent coastal vertex
            for adj_vid in coastal_vertices[i].adjacent_vertices:
                adj_v = self.vertices[adj_vid]
                if len(adj_v.adjacent_hexes) <= 2 and adj_v.port is None:
                    adj_v.port = port
                    break
            i += 1
            assigned += 1

    def get_vertex_score(self, vertex_id: int) -> float:
        """
        Score a vertex based on its production potential.
        Higher is better.
        """
        v = self.vertices[vertex_id]
        score = 0.0
        resources = set()
        for hex_id in v.adjacent_hexes:
            h = self.hexes[hex_id]
            if h.resource != Resource.DESERT and h.number:
                score += h.probability * 36  # pip count equivalent
                resources.add(h.resource)
        # Bonus for resource diversity
        score += len(resources) * 0.5
        # Bonus for port
        if v.port:
            score += 2.0
        return score

    def get_valid_settlement_spots(self, player_settlements: List[int]) -> List[int]:
        """Get vertices where settlements can be placed (distance rule)."""
        occupied = set()
        for vid in player_settlements:
            occupied.add(vid)
            for adj in self.vertices[vid].adjacent_vertices:
                occupied.add(adj)

        # Also check all buildings on board
        for vid, v in self.vertices.items():
            if v.is_occupied:
                occupied.add(vid)
                for adj in v.adjacent_vertices:
                    occupied.add(adj)

        return [vid for vid in self.vertices if vid not in occupied]

    def roll_dice(self) -> int:
        return self.rng.randint(1, 6) + self.rng.randint(1, 6)

    def get_producing_hexes(self, roll: int) -> List[int]:
        return [h.hex_id for h in self.hexes.values()
                if h.number == roll and not h.has_robber]

    def display_board_stats(self):
        """Print board statistics."""
        print("\n=== CATAN BOARD ===")
        print(f"Total hexes: {len(self.hexes)}")
        print(f"Total vertices: {len(self.vertices)}")
        print(f"Total edges: {len(self.edges)}")
        print("\nHex layout:")
        row_sizes = [3, 4, 5, 4, 3]
        idx = 0
        for row in range(5):
            row_hexes = []
            for col in range(row_sizes[row]):
                h = self.hexes[idx]
                num = h.number if h.number else "D"
                row_hexes.append(f"{h.resource.value[:3].upper()}({num})")
                idx += 1
            print("  " * (5 - row_sizes[row]) + "  ".join(row_hexes))
