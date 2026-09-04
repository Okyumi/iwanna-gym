"""iwanna_gym: an RL environment with exact I Wanna fangame physics.

Physics is a C port of the Renex GM8 fangame engine (Yuuutu-family):
50 Hz, run 3 px/f, jump -8.5, double jump -7, gravity 0.4, vspeed cap 9,
release-to-shorthop *0.45, 11x20 px hitbox, pixel-perfect spike triangles.
"""
from .clib import NUM_ACTIONS, OBS_SIZE, CIWanna
from .env import (IWannaDiscoveryEnv, IWannaEnv, IWannaGoalEnv,
                  PixelObsWrapper)
from .levels import generate_needle, list_levels, load_level

__version__ = "0.1.0"
__all__ = [
    "IWannaEnv", "IWannaGoalEnv", "IWannaDiscoveryEnv",
    "PixelObsWrapper", "CIWanna",
    "load_level", "list_levels", "generate_needle",
    "OBS_SIZE", "NUM_ACTIONS",
]

try:
    from gymnasium.envs.registration import register

    register(id="IWanna-v0", entry_point="iwanna_gym.env:IWannaEnv")
    register(id="IWannaGoal-v0", entry_point="iwanna_gym.env:IWannaGoalEnv")
    register(id="IWannaDiscovery-v0",
             entry_point="iwanna_gym.env:IWannaDiscoveryEnv")
except Exception:  # gymnasium optional for the raw C interface
    pass
