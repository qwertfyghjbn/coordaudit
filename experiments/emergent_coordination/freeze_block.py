#!/usr/bin/env python3
"""Freeze a preregistered matched-block contract without executing model calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments.emergent_coordination.harness.block_runner import BlockRunner
from experiments.emergent_coordination.harness.contract import load_block_config
from experiments.emergent_coordination.harness.paths import DEFAULT_RUNS_DIR, EXPERIMENT_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze a preregistered matched-block contract.")
    parser.add_argument("--block-id", required=True, help="New immutable block directory name.")
    parser.add_argument(
        "--config",
        type=Path,
        default=EXPERIMENT_ROOT / "manifests" / "n4_pilot_v0.json",
        help=(
            "Preregistered block contract JSON; the contract_id field selects the family "
            "(legacy pilot JSON without contract_id maps to n4_pilot_v0)."
        ),
    )
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR, help="Parent directory for the block artifact.")
    args = parser.parse_args()

    frozen = BlockRunner(load_block_config(args.config), args.runs_dir).freeze(args.block_id)
    print(json.dumps({"block_dir": str(frozen.block_dir), "manifest": str(frozen.manifest_path), "manifest_hash": frozen.manifest_hash}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
