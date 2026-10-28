"""Default source for new real-contract evaluation runs.

Frozen selections keep their own source roots and hashes; this default is only
for new sampling, probes and runs (user instruction, 2026-10-27).
"""
from pathlib import Path

DEFAULT_SAMPLE_ROOT = Path(__file__).resolve().parents[2] / "funds_word" / "基金合同第一批"
