#!/usr/bin/env bash
# correctness.sh <build_dir>
# Compare MPI runs against serial baseline using Max/SumSq from program output.

set -euo pipefail

# ---- Args ----
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <build_dir> [config_path]"
  exit 1
fi
BUILDDIR="$1"
CONF="${2:-./tests/test500.config}"

# ---- Paths ----
UNI="${BUILDDIR}/wave260uni"
MPI="${BUILDDIR}/wave260mpi"
MPIRUN="${MPIRUN:-mpirun}"
EPS="${EPS:-1e-9}"

# ---- Sanity ----
command -v "$MPIRUN" >/dev/null || { echo "mpirun not found"; exit 2; }
[[ -x "$UNI" ]] || { echo "Not executable: $UNI"; exit 2; }
[[ -x "$MPI" ]] || { echo "Not executable: $MPI"; exit 2; }
[[ -f "$CONF" ]] || { echo "Config not found: $CONF"; exit 2; }

# ---- Detect core count ----
CORES="$( (command -v sysctl >/dev/null && sysctl -n hw.ncpu) || getconf _NPROCESSORS_ONLN || echo 1 )"

# ---- Detect Open MPI once ----
IS_OPENMPI=0
if "$MPIRUN" --version 2>&1 | grep -qi 'Open MPI'; then
  IS_OPENMPI=1
fi

# ---- Parsers ----
parse_ms() {  # prints "MAX SUMSQ" or exits 3 if not found
  perl -ne 'if(/Max\s*=\s*([0-9.+-eE]+).*?SumSq\s*=\s*([0-9.+-eE]+)/){print "$1 $2\n"; exit 0} END{exit 3}'
}
float_close() { # a b eps → 0 if |a-b|<=eps
  python3 - "$1" "$2" "$3" <<'PY'
import sys, math
a=float(sys.argv[1]); b=float(sys.argv[2]); e=float(sys.argv[3])
sys.exit(0 if abs(a-b)<=e else 1)
PY
}

# ---- Baseline ----
echo "== Baseline (serial) =="
BOUT="$("$UNI" "$CONF" 2>&1 | tee /dev/stderr)"
read -r BMAX BSUM <<<"$(printf '%s\n' "$BOUT" | parse_ms)" || { echo "ERROR: failed to parse baseline Max/SumSq"; exit 3; }
echo "Baseline Max=$BMAX  SumSq=$BSUM"
echo

# ---- Cases: (np x y) total = 15 ----
CASES=(
  "1 1 1"
  "2 1 2" "2 2 1"
  "4 1 4" "4 2 2" "4 4 1"
  "8 1 8" "8 2 4" "8 4 2" "8 8 1"
  "16 1 16" "16 2 8" "16 4 4" "16 8 2" "16 16 1"
)

# ---- Run ----
pass=0; fail=0; idx=0
for c in "${CASES[@]}"; do
  idx=$((idx+1))
  set -- $c
  NP="$1"; X="$2"; Y="$3"

  # Decide oversubscribe per case: only for Open MPI AND np > cores
  USE_OSUB=0
  if [[ $IS_OPENMPI -eq 1 && "$NP" -gt "$CORES" ]]; then
    USE_OSUB=1
    echo "Note: Open MPI and np=$NP > cores=$CORES → enabling --oversubscribe"
  fi

  echo "== [$idx/${#CASES[@]}] np=$NP grid=${X}x${Y} =="

  if [[ $USE_OSUB -eq 1 ]]; then
    echo "+ $MPIRUN --oversubscribe -np $NP $MPI $CONF -x $X -y $Y"
    OUT="$("$MPIRUN" --oversubscribe -np "$NP" "$MPI" "$CONF" -x "$X" -y "$Y" 2>&1 | tee /dev/stderr)" || true
  else
    echo "+ $MPIRUN -np $NP $MPI $CONF -x $X -y $Y"
    OUT="$("$MPIRUN" -np "$NP" "$MPI" "$CONF" -x "$X" -y "$Y" 2>&1 | tee /dev/stderr)" || true
  fi

  if ! read -r M S <<<"$(printf '%s\n' "$OUT" | parse_ms)"; then
    echo "FAIL: could not parse Max/SumSq"; fail=$((fail+1)); echo; continue
  fi

  if float_close "$M" "$BMAX" "$EPS" && float_close "$S" "$BSUM" "$EPS"; then
    echo "PASS: Max=$M ≈ $BMAX, SumSq=$S ≈ $BSUM (eps=$EPS)"; pass=$((pass+1))
  else
    echo "FAIL:"
    echo "  Max:   got $M   vs $BMAX"
    echo "  SumSq: got $S   vs $BSUM"
    fail=$((fail+1))
  fi
  echo
done

echo "== Summary =="
echo "  Passed: $pass"
echo "  Failed: $fail"
echo "  Total:  $((pass+fail))"
[[ $fail -eq 0 ]] || exit 1
