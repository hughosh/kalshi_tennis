"""
Catan Player Module
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from .board import Resource, PortType, BuildingType


@dataclass
class Player:
    player_id: int
    name: str
    strategy: str = "balanced"

    # Resources
    resources: Dict[Resource, int] = field(default_factory=lambda: {
        r: 0 for r in Resource if r != Resource.DESERT
    })

    # Buildings
    settlements: List[int] = field(default_factory=list)  # vertex_ids
    cities: List[int] = field(default_factory=list)       # vertex_ids
    roads: List[int] = field(default_factory=list)         # edge_ids

    # Development cards
    dev_cards: List[str] = field(default_factory=list)
    knights_played: int = 0

    # Victory points
    victory_points: int = 0

    # Limits
    MAX_SETTLEMENTS = 5
    MAX_CITIES = 4
    MAX_ROADS = 15

    @property
    def total_resources(self) -> int:
        return sum(self.resources.values())

    @property
    def settlement_count(self) -> int:
        return len(self.settlements)

    @property
    def city_count(self) -> int:
        return len(self.cities)

    @property
    def road_count(self) -> int:
        return len(self.roads)

    def can_build_settlement(self) -> bool:
        r = self.resources
        return (r[Resource.WOOD] >= 1 and r[Resource.BRICK] >= 1 and
                r[Resource.SHEEP] >= 1 and r[Resource.WHEAT] >= 1 and
                self.settlement_count < self.MAX_SETTLEMENTS)

    def can_build_city(self) -> bool:
        r = self.resources
        return (r[Resource.ORE] >= 3 and r[Resource.WHEAT] >= 2 and
                self.city_count < self.MAX_CITIES and
                self.settlement_count > 0)

    def can_build_road(self) -> bool:
        r = self.resources
        return (r[Resource.WOOD] >= 1 and r[Resource.BRICK] >= 1 and
                self.road_count < self.MAX_ROADS)

    def can_buy_dev_card(self) -> bool:
        r = self.resources
        return (r[Resource.ORE] >= 1 and r[Resource.WHEAT] >= 1 and
                r[Resource.SHEEP] >= 1)

    def spend_settlement(self):
        self.resources[Resource.WOOD] -= 1
        self.resources[Resource.BRICK] -= 1
        self.resources[Resource.SHEEP] -= 1
        self.resources[Resource.WHEAT] -= 1

    def spend_city(self):
        self.resources[Resource.ORE] -= 3
        self.resources[Resource.WHEAT] -= 2

    def spend_road(self):
        self.resources[Resource.WOOD] -= 1
        self.resources[Resource.BRICK] -= 1

    def spend_dev_card(self):
        self.resources[Resource.ORE] -= 1
        self.resources[Resource.WHEAT] -= 1
        self.resources[Resource.SHEEP] -= 1

    def get_ports(self, board) -> List[PortType]:
        """Get all ports this player has access to."""
        ports = []
        for vid in self.settlements + self.cities:
            v = board.vertices[vid]
            if v.port and v.port not in ports:
                ports.append(v.port)
        return ports

    def can_trade(self, give: Resource, want: Resource, board) -> bool:
        """Check if player can trade give->want."""
        ports = self.get_ports(board)
        # Check 2:1 port
        resource_port_map = {
            Resource.WOOD: PortType.WOOD,
            Resource.BRICK: PortType.BRICK,
            Resource.SHEEP: PortType.SHEEP,
            Resource.WHEAT: PortType.WHEAT,
            Resource.ORE: PortType.ORE,
        }
        port_for_resource = resource_port_map.get(give)
        if port_for_resource in ports:
            return self.resources[give] >= 2
        if PortType.THREE_TO_ONE in ports:
            return self.resources[give] >= 3
        return self.resources[give] >= 4

    def trade_rate(self, give: Resource, board) -> int:
        """Get the trade rate for a resource (2, 3, or 4)."""
        ports = self.get_ports(board)
        resource_port_map = {
            Resource.WOOD: PortType.WOOD,
            Resource.BRICK: PortType.BRICK,
            Resource.SHEEP: PortType.SHEEP,
            Resource.WHEAT: PortType.WHEAT,
            Resource.ORE: PortType.ORE,
        }
        port_for_resource = resource_port_map.get(give)
        if port_for_resource in ports:
            return 2
        if PortType.THREE_TO_ONE in ports:
            return 3
        return 4

    def receive_resources(self, resource: Resource, amount: int):
        self.resources[resource] = self.resources.get(resource, 0) + amount

    def calculate_vp(self) -> int:
        vp = self.settlement_count + (self.city_count * 2)
        for card in self.dev_cards:
            if card == "victory_point":
                vp += 1
        return vp

    def __repr__(self):
        return (f"Player({self.name}, VP={self.calculate_vp()}, "
                f"Resources={self.total_resources}, "
                f"Settlements={self.settlement_count}, Cities={self.city_count})")
