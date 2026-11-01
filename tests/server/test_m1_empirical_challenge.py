"""Pytest integration test executing the Milestone M1 Empirical Adversarial Stress Suite.

Covers:
- Zero-allocation 3D projection engine (10,000 cycles, 1,000,000 projections, scratchpad invariance).
- Long-run frame cycle stability, batch buffer boundary enforcement.
- Fresnel LUT boundary clamping under extreme inputs (negative, overflow, NaN, Infinity).
- Rapid oscillatory theme toggling (2,000 rapid switches).
- Mathematical cortex preservation (12 lobes, displacement harmonics, particle matrix).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def test_m1_empirical_adversarial_stress_suite():
    """Execute Node.js adversarial stress test harness and assert exit code 0."""
    script_path = Path(__file__).resolve().parent.parent / "stress" / "test_m1_empirical_challenge.js"
    assert script_path.exists(), f"Stress script not found at {script_path}"

    result = subprocess.run(
        ["node", str(script_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )

    print("STDOUT:", result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr, file=sys.stderr)

    assert result.returncode == 0, f"Stress test failed with exit code {result.returncode}:\n{result.stdout}\n{result.stderr}"
    assert "ALL EMPIRICAL ADVERSARIAL CHALLENGES PASSED (5 / 5)" in result.stdout
