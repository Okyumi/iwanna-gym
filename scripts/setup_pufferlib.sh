#!/usr/bin/env bash
# Stage the iwanna Ocean env into a pinned PufferLib checkout for a real
# `puffer` training run. Pinned PufferLib: 4.0.0 @ 42f70d69.
#
#   bash scripts/setup_pufferlib.sh [PUFFERLIB_DIR]
#
# Requires (on a training-capable machine — NOT this sandbox, which has
# no torch and blocks pypi): python with torch + pufferlib installed, a
# C toolchain with OpenMP. See docs/pufferlib_integration.md.
set -euo pipefail

PIN=42f70d6932c30ac977736f861006809c50168ba9
REPO=https://github.com/PufferAI/PufferLib
PUF=${1:-"$HOME/PufferLib"}
HERE=$(cd "$(dirname "$0")/.." && pwd)

if [ ! -d "$PUF/.git" ]; then
  git clone "$REPO" "$PUF"
fi
git -C "$PUF" fetch --all --tags
git -C "$PUF" checkout "$PIN"

# stage the env: PufferLib 4.0 ocean envs live in ocean/<name>/ with
# binding.c + <name>.h (+ optional demo). Our binding.c includes
# iwanna_puffer.h which includes ../iwanna.h, so copy the whole c_src.
DST="$PUF/ocean/iwanna"
mkdir -p "$DST"
cp "$HERE/c_src/iwanna.h" "$DST/"
cp -r "$HERE/c_src/gamepack" "$DST/"
cp -r "$HERE/c_src/exact.h" "$HERE/c_src/exact_impl.h" "$DST/" 2>/dev/null || true
cp -r "$HERE/c_src/boss" "$DST/" 2>/dev/null || true
mkdir -p "$DST/puffer"
cp "$HERE/c_src/puffer/iwanna_puffer.h" "$DST/puffer/"
# binding.c must sit at ocean/iwanna/ and include the adapter; rewrite
# its include path to the staged layout
sed 's#"iwanna_puffer.h"#"puffer/iwanna_puffer.h"#' \
    "$HERE/c_src/puffer/binding.c" > "$DST/binding.c"
cp "$HERE/config/iwanna_puffer.ini" "$PUF/config/iwanna.ini"

echo "staged iwanna env into $DST (PufferLib pinned at $PIN)"
echo
echo "Build + short smoke train (controlled room):"
echo "  export IWG_LEVEL_FILE=$HERE/iwanna_gym/levels/traps/t06_crusher.txt"
echo "  cd $PUF && puffer build iwanna && puffer train iwanna --train.total-timesteps 2000000"
echo
echo "Native task (needs a locally-built pack; never committed):"
echo "  python -m iwanna_gym.games.iwbtgr_1_5_3 build <source_checkout>"
echo "  # then emit the task's numeric kwargs + IWG_PACK via"
echo "  #   python -c 'import iwanna_gym.discovery as d,json;"
echo "  #     k,e=d.binding_kwargs(\"disc.iwbtgr_1_5_3.rGuyFortress1.chalice_hall\");"
echo "  #     print(json.dumps(k)); print(e)'"
echo "  # set IWG_PACK + the printed [env] overrides in config/iwanna.ini,"
echo "  # then: cd $PUF && puffer build iwanna && puffer train iwanna"
