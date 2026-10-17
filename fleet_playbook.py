"""Sandbox-only action policies, independent of model-generated recommendations."""
PLAYBOOK = {
    "electrical_supply": {"reversibility": "MED", "action": "Simulate supply containment in the synthetic timeline.", "min_confidence": .8},
    "thermal": {"reversibility": "HIGH", "action": "Simulate restored thermal conditions; no real cooling control.", "min_confidence": .6},
    "overload": {"reversibility": "HIGH", "action": "Simulate restored load conditions; no real load shedding.", "min_confidence": .6},
    "harmonics": {"reversibility": "HIGH", "action": "Simulate restored waveform metrics; no real filter control.", "min_confidence": .6},
    "battery": {"reversibility": "NONE", "action": "Draft an engineer-review handoff for battery-risk indications.", "min_confidence": 1},
    "bearing": {"reversibility": "NONE", "action": "Draft an engineer-review handoff for bearing-risk indications.", "min_confidence": 1},
    "pressure": {"reversibility": "NONE", "action": "Draft an engineer-review handoff for pressure-loss indications.", "min_confidence": 1},
    "local": {"reversibility": "NONE", "action": "Unclassified condition: request an engineer assessment.", "min_confidence": 1},
}


def lookup_playbook(category: str) -> dict:
    return dict(PLAYBOOK.get(category, PLAYBOOK["local"]))
