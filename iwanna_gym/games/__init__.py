"""Exact-game packages.

Each subpackage identifies one precisely versioned game
(docs/fidelity_contract.md) and provides: an offline `build()` that
converts the locally supplied source into a compiled .iwpack, a
`load_pack()` used by the env at construction, and committed
manifests/graphs (never source assets).
"""
from __future__ import annotations

GAMES = ("iwbtgr_1_5_3", "k2warped_gms14")


def get_game(game_id: str):
    if game_id == "iwbtgr_1_5_3":
        from . import iwbtgr_1_5_3
        return iwbtgr_1_5_3
    if game_id == "k2warped_gms14":
        from . import k2warped_gms14
        return k2warped_gms14
    raise KeyError(f"unknown game {game_id!r}; available: {GAMES}")
