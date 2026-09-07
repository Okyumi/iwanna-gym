"""PufferLib 4.0.0 binding validation (torch-free).

These check the REAL integration surface without needing torch or a
PufferLib install: (1) every [env] kwarg the C binding reads is present
in the config that the puffer trainer passes; (2) the binding compiles
against the pinned PufferLib headers when a checkout is available.
"""
from __future__ import annotations

import configparser
import os
import re
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, ".")

BINDING = "c_src/puffer/binding.c"
CONFIG = "config/iwanna_puffer.ini"
PIN = "42f70d6932c30ac977736f861006809c50168ba9"


def _binding_dict_keys() -> set[str]:
    src = open(BINDING, encoding="utf-8").read()
    return set(re.findall(r'dict_get\(kwargs,\s*"([^"]+)"\)', src))


def test_binding_kwargs_are_all_in_config():
    keys = _binding_dict_keys()
    assert keys, "no dict_get keys parsed from binding.c"
    cp = configparser.ConfigParser()
    cp.optionxform = str          # preserve case (attempts_K != attempts_k)
    cp.read(CONFIG)
    env_keys = set(cp["env"].keys())
    missing = keys - env_keys
    assert not missing, f"binding reads kwargs absent from config: {missing}"


def test_registry_binding_kwargs_cover_binding_keys():
    # the discovery registry emits numeric kwargs for the PufferLib path;
    # every key the C binding reads must be produced (minus num_agents,
    # which my_init sets directly, and the file-path env vars)
    import iwanna_gym.discovery as d
    keys = _binding_dict_keys()
    kwargs, envvars = d.binding_kwargs("disc.research.t06_crusher")
    produced = set(kwargs) | {"num_agents"}
    missing = keys - produced
    assert not missing, f"registry does not emit binding kwargs: {missing}"
    # native task also covered (pack path)
    kwargs2, ev2 = d.binding_kwargs(
        "disc.iwbtgr_1_5_3.rGuyFortress1.chalice_hall")
    assert kwargs2["use_pack"] == 1 and "IWG_PACK" in ev2
    assert (set(keys) - (set(kwargs2) | {"num_agents"})) == set()


def _pufferlib_src() -> str | None:
    d = os.environ.get("IWG_PUFFERLIB_DIR")
    for cand in ([d] if d else []) + ["/tmp/PufferLib"]:
        if cand and os.path.exists(os.path.join(cand, "src", "vecenv.h")):
            return os.path.join(cand, "src")
    return None


@pytest.mark.skipif(_pufferlib_src() is None,
                    reason="pinned PufferLib checkout not present "
                           "(set IWG_PUFFERLIB_DIR); binding compile "
                           "validated externally")
def test_binding_compiles_against_pinned_pufferlib():
    src = _pufferlib_src()
    if shutil.which("gcc") is None:
        pytest.skip("gcc unavailable")
    r = subprocess.run(
        ["gcc", "-fsyntax-only", "-fopenmp", "-DIW_NO_RAYLIB",
         "-I", src, "-Ic_src/puffer", BINDING],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-3000:]


def test_binding_pins_pufferlib_version():
    for f in ("scripts/setup_pufferlib.sh", "scripts/puffer_smoke.py",
              "docs/pufferlib_integration.md"):
        assert PIN in open(f, encoding="utf-8").read(), f


def test_launcher_emits_valid_config_for_both_task_types(tmp_path=None):
    # the single launcher (scripts/puffer_launch.py) writes a task-specific
    # config whose [env] covers every key the binding reads, for BOTH a
    # controlled and a native task.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "puffer_launch", "scripts/puffer_launch.py")
    launch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launch)
    keys = _binding_dict_keys()
    for tid in ("disc.research.t06_crusher",
                "disc.iwbtgr_1_5_3.rGuyFortress1.chalice_hall"):
        out = f"build/puffer_launch/_test_{tid}.ini"
        env = launch._write_config(tid, out, timesteps=100000)
        cp = configparser.ConfigParser()
        cp.optionxform = str
        cp.read(out)
        env_keys = set(cp["env"].keys())
        assert not (keys - env_keys), (tid, keys - env_keys)
        assert env  # non-empty file-path env vars (IWG_PACK / IWG_LEVEL_FILE)
        os.remove(out)
