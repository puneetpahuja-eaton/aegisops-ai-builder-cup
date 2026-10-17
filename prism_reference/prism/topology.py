"""
Topology / causal-graph engine.

The physical power chain (Utility -> Transformer -> Switchgear -> UPS -> PDU ->
Breaker -> Rack) is a tree. That tree IS PRISM's causal graph: a fault upstream
propagates symptoms downstream. The Diagnostician agent uses this structure to
separate the true ROOT CAUSE from the many downstream SYMPTOMS it produces.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import config


@dataclass
class Asset:
    asset_id: str
    name: str
    type: str
    parent_id: Optional[str]
    site: str
    rated_kw: float
    criticality: str
    children: List[str] = field(default_factory=list)


class Topology:
    """Loads the asset fleet and exposes causal-graph helpers."""

    def __init__(self, assets: Dict[str, Asset]):
        self.assets = assets

    # -- construction ------------------------------------------------------- #
    @classmethod
    def load(cls, path=None) -> "Topology":
        path = path or config.ASSETS_FILE
        assets: Dict[str, Asset] = {}
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                parent = row["parent_id"].strip() or None
                assets[row["asset_id"]] = Asset(
                    asset_id=row["asset_id"],
                    name=row["name"],
                    type=row["type"],
                    parent_id=parent,
                    site=row["site"],
                    rated_kw=float(row["rated_kw"]),
                    criticality=row["criticality"],
                )
        # wire up children
        for a in assets.values():
            if a.parent_id and a.parent_id in assets:
                assets[a.parent_id].children.append(a.asset_id)
        return cls(assets)

    # -- lookups ------------------------------------------------------------ #
    def get(self, asset_id: str) -> Asset:
        return self.assets[asset_id]

    def all_ids(self) -> List[str]:
        return list(self.assets.keys())

    def ancestors(self, asset_id: str) -> List[str]:
        """Return ancestors from immediate parent up to the utility feed."""
        out: List[str] = []
        cur = self.assets[asset_id].parent_id
        while cur:
            out.append(cur)
            cur = self.assets[cur].parent_id
        return out

    def descendants(self, asset_id: str) -> List[str]:
        """Return every asset fed (directly or indirectly) by this asset."""
        out: List[str] = []
        stack = list(self.assets[asset_id].children)
        while stack:
            cur = stack.pop()
            out.append(cur)
            stack.extend(self.assets[cur].children)
        return out

    def depth(self, asset_id: str) -> int:
        """Distance from the utility feed (root = 0). Lower = more upstream."""
        return len(self.ancestors(asset_id))
