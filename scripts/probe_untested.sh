#!/usr/bin/env bash
# probe_untested.sh — throwaway negative control for the D-80 gate-parity check.
#
# Deliberately shipped with NO tests/test_probe_untested.sh and NO invoker, so that
# scripts/check_gate_parity.py must report BOTH an R1 finding (no fixture) and an R3
# finding (named by nothing executable) and exit 1. That check runs as a step inside the
# required `Validate Repo Allow-List` context, so the point being proven is not the script's
# behaviour but the protection layer's: a red required context genuinely blocks a merge.
#
# This branch is closed unmerged and deleted. It is not a gate and is not referenced anywhere.
set -eu

echo "negative-control probe: expecting R1 and R3 from check_gate_parity.py"
