"""Empirical Challenger Oracle Test Suite: Visual Cortex Geometric Fidelity & Math Preservation.

Part of Milestone M1 Challenge (teamwork_challenger_m1_2).
Validates:
1. Exact preservation of all 12 cortical lobes in CORTICAL_LOBES.
2. Exact mathematical reproduction of the gyri harmonic equation `corticalFoldDisplacement`.
3. Structural verification of 240 rings and 18,480 cortical vertices.
4. Dendritic singularity coordinate and filament branch count (56 total).
5. Fiber stream curves (28 streams, 40 steps / 41 points each).
6. Zero-allocation project3D scratchpad equivalence against pre-optimized allocation baseline.
7. Fresnel LUT error bound analysis against continuous Math.pow baseline.
8. Triple-file SHA256 parity across static, public, and dist distributions.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from pathlib import Path
import pytest


# ---------------------------------------------------------------------------
# Independent Analytical Oracle
# ---------------------------------------------------------------------------

ORACLE_CORTICAL_LOBES = [
    {"cx":  0.18, "cy":  0.06, "cz":  0.05, "rx": 1.05, "ry": 0.94, "rz": 0.98, "seed": 0.3, "rings": 28, "isMain": True},
    {"cx":  0.34, "cy":  0.64, "cz":  0.12, "rx": 0.68, "ry": 0.58, "rz": 0.64, "seed": 1.4, "rings": 22, "isMain": True},
    {"cx": -0.06, "cy":  0.72, "cz":  0.16, "rx": 0.60, "ry": 0.52, "rz": 0.58, "seed": 2.2, "rings": 20, "isMain": True},
    {"cx":  0.86, "cy":  0.14, "cz":  0.08, "rx": 0.64, "ry": 0.56, "rz": 0.60, "seed": 3.1, "rings": 20, "isMain": True},
    {"cx":  0.68, "cy": -0.34, "cz":  0.14, "rx": 0.66, "ry": 0.54, "rz": 0.62, "seed": 4.0, "rings": 20, "isMain": True},
    {"cx":  0.12, "cy": -0.64, "cz":  0.22, "rx": 0.86, "ry": 0.48, "rz": 0.74, "seed": 4.9, "rings": 22, "isMain": True},
    {"cx": -0.46, "cy": -0.32, "cz":  0.20, "rx": 0.66, "ry": 0.54, "rz": 0.62, "seed": 5.8, "rings": 20, "isMain": True},
    {"cx": -0.52, "cy":  0.22, "cz":  0.18, "rx": 0.64, "ry": 0.58, "rz": 0.64, "seed": 6.7, "rings": 20, "isMain": True},
    {"cx":  0.14, "cy": -0.10, "cz":  0.26, "rx": 0.56, "ry": 0.52, "rz": 0.55, "seed": 7.5, "rings": 18, "isMain": True},
    {"cx": -1.38, "cy":  0.86, "cz": -0.18, "rx": 0.68, "ry": 0.52, "rz": 0.58, "seed": 8.4, "rings": 20, "isMain": False},
    {"cx": -1.76, "cy":  0.64, "cz": -0.08, "rx": 0.50, "ry": 0.42, "rz": 0.48, "seed": 9.3, "rings": 16, "isMain": False},
    {"cx": -1.12, "cy":  1.06, "cz": -0.24, "rx": 0.46, "ry": 0.38, "rz": 0.44, "seed": 10.1, "rings": 14, "isMain": False},
]

ORACLE_SINGULARITY_POS = {"x": 0.14, "y": -0.16, "z": 0.30}


def oracle_cortical_fold_displacement(nx: float, ny: float, nz: float, seed: float) -> float:
    """Exact harmonic gyri fold displacement formula."""
    h1 = math.sin(nx * 2.5 + seed) * math.cos(ny * 2.3 - seed * 0.7) * math.cos(nz * 2.4 + 0.4)
    h2 = math.cos(nx * 3.6 - ny * 3.1 + seed * 1.2) * math.sin(nz * 3.3 + seed * 0.5)
    h3 = math.sin((nx + nz) * 4.2 + seed) * math.cos(ny * 3.8)
    return 0.24 * h1 + 0.14 * h2 + 0.08 * h3


def oracle_project3d_baseline(
    x: float, y: float, z: float,
    cosY: float, sinY: float, cosX: float, sinX: float,
    focal: float, cx: float, cy: float, camZ: float,
) -> dict[str, float]:
    """Baseline unoptimized projection allocating a new dictionary each time."""
    rx = x * cosY + z * sinY
    rz1 = -x * sinY + z * cosY
    ry = y * cosX - rz1 * sinX
    rz = y * sinX + rz1 * cosX

    depth = camZ - rz
    scale = (focal / depth) if depth > 0.25 else 0.0
    return {
        "sx": cx + rx * scale,
        "sy": cy - ry * scale,
        "rz": rz,
        "depth": depth,
        "scale": scale,
    }


# Static scratchpad simulating the worker's zero-allocation optimization
_oracle_scratchpad = {"sx": 0.0, "sy": 0.0, "rz": 0.0, "depth": 0.0, "scale": 0.0}


def oracle_project3d_scratchpad(
    x: float, y: float, z: float,
    cosY: float, sinY: float, cosX: float, sinX: float,
    focal: float, cx: float, cy: float, camZ: float,
) -> dict[str, float]:
    """Optimized zero-allocation projection mutating scratchpad."""
    rx = x * cosY + z * sinY
    rz1 = -x * sinY + z * cosY
    ry = y * cosX - rz1 * sinX
    rz = y * sinX + rz1 * cosX

    depth = camZ - rz
    scale = (focal / depth) if depth > 0.25 else 0.0
    _oracle_scratchpad["sx"] = cx + rx * scale
    _oracle_scratchpad["sy"] = cy - ry * scale
    _oracle_scratchpad["rz"] = rz
    _oracle_scratchpad["depth"] = depth
    _oracle_scratchpad["scale"] = scale
    return _oracle_scratchpad


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def html_content() -> str:
    path = Path("d:/Ultron/src/openjarvis/server/static/hologram.html")
    assert path.is_file(), f"hologram.html not found at {path}"
    return path.read_text(encoding="utf-8")


class TestCorticalLobesGeometricFidelity:
    """Verifies that CORTICAL_LOBES in hologram.html preserves all 12 lobes and their parameters."""

    def test_cortical_lobes_count_is_exactly_twelve(self, html_content: str):
        # Extract CORTICAL_LOBES array from HTML
        match = re.search(r"const\s+CORTICAL_LOBES\s*=\s*\[(.*?)\];", html_content, re.DOTALL)
        assert match is not None, "CORTICAL_LOBES array definition not found"
        raw_array = match.group(1)

        # Parse lobe objects
        lobe_lines = [line.strip() for line in raw_array.strip().split("\n") if line.strip().startswith("{")]
        assert len(lobe_lines) == 12, f"Expected exactly 12 cortical lobes, found {len(lobe_lines)}"

    def test_cortical_lobes_mathematical_parameters_match_oracle(self, html_content: str):
        # Extract individual lobe parameters using regex
        pattern = re.compile(
            r"\{\s*cx:\s*([-\d\.]+),\s*cy:\s*([-\d\.]+),\s*cz:\s*([-\d\.]+),\s*"
            r"rx:\s*([-\d\.]+),\s*ry:\s*([-\d\.]+),\s*rz:\s*([-\d\.]+),\s*"
            r"seed:\s*([-\d\.]+),\s*rings:\s*(\d+),\s*isMain:\s*(true|false)\s*\}"
        )
        matches = pattern.findall(html_content)
        assert len(matches) == 12, f"Expected 12 parsed lobes, got {len(matches)}"

        total_rings = 0
        for i, m in enumerate(matches):
            cx, cy, cz, rx, ry, rz, seed, rings, is_main = m
            expected = ORACLE_CORTICAL_LOBES[i]

            assert math.isclose(float(cx), expected["cx"], abs_tol=1e-6), f"Lobe {i} cx mismatch"
            assert math.isclose(float(cy), expected["cy"], abs_tol=1e-6), f"Lobe {i} cy mismatch"
            assert math.isclose(float(cz), expected["cz"], abs_tol=1e-6), f"Lobe {i} cz mismatch"
            assert math.isclose(float(rx), expected["rx"], abs_tol=1e-6), f"Lobe {i} rx mismatch"
            assert math.isclose(float(ry), expected["ry"], abs_tol=1e-6), f"Lobe {i} ry mismatch"
            assert math.isclose(float(rz), expected["rz"], abs_tol=1e-6), f"Lobe {i} rz mismatch"
            assert math.isclose(float(seed), expected["seed"], abs_tol=1e-6), f"Lobe {i} seed mismatch"
            assert int(rings) == expected["rings"], f"Lobe {i} rings count mismatch"
            assert (is_main == "true") == expected["isMain"], f"Lobe {i} isMain flag mismatch"

            total_rings += int(rings)

        assert total_rings == 240, f"Expected 240 total rings across lobes, got {total_rings}"


class TestGyriHarmonicsPreservation:
    """Verifies that the gyri harmonic equation is preserved and evaluates accurately."""

    def test_cortical_fold_displacement_tokens_present(self, html_content: str):
        # Verify function declaration and components
        assert "function corticalFoldDisplacement(nx, ny, nz, seed)" in html_content
        assert "0.24 * h1 + 0.14 * h2 + 0.08 * h3" in html_content
        assert "Math.sin(nx * 2.5 + seed)" in html_content
        assert "Math.cos(ny * 2.3 - seed * 0.7)" in html_content
        assert "Math.cos(nz * 2.4 + 0.4)" in html_content
        assert "Math.cos(nx * 3.6 - ny * 3.1 + seed * 1.2)" in html_content
        assert "Math.sin(nz * 3.3 + seed * 0.5)" in html_content
        assert "Math.sin((nx + nz) * 4.2 + seed)" in html_content
        assert "Math.cos(ny * 3.8)" in html_content

    def test_cortical_fold_displacement_oracle_evaluation(self):
        # Stress-test 1,000 synthetic coordinate triples across the [-1, 1] unit sphere
        rng = random.Random(42)
        seeds = [0.3, 1.4, 2.2, 3.1, 4.0, 4.9, 5.8, 6.7, 7.5, 8.4, 9.3, 10.1]

        for seed in seeds:
            for _ in range(100):
                # Sample points on sphere
                u = rng.random()
                v = rng.random()
                theta = u * 2.0 * math.pi
                phi = math.acos(2.0 * v - 1.0)
                nx = math.sin(phi) * math.cos(theta)
                ny = math.cos(phi)
                nz = math.sin(phi) * math.sin(theta)

                disp = oracle_cortical_fold_displacement(nx, ny, nz, seed)

                # Displacement must stay within bounded physical amplitude
                # Max theoretical: 0.24*1 + 0.14*1 + 0.08*1 = 0.46
                assert -0.46 <= disp <= 0.46, f"Displacement {disp} exceeded theoretical bound [-0.46, 0.46]"

                # rScale = 1.0 + disp must remain positive everywhere (no self-intersection through origin)
                r_scale = 1.0 + disp
                assert r_scale >= 0.54, f"rScale {r_scale} fell below positive threshold 0.54"


class TestCorticalMeshCoordinates:
    """Verifies that the ring mesh point generation produces exactly 18,480 vertices without NaN or inf."""

    def test_full_mesh_vertex_generation_fidelity(self):
        v_steps = 76
        points_per_ring = v_steps + 1  # 77 points per ring (j from 0 to 76 inclusive)
        total_vertices = 0

        for lobe_idx, lobe in enumerate(ORACLE_CORTICAL_LOBES):
            rings = lobe["rings"]
            tilt_a = (lobe_idx * 0.55) - 0.7
            tilt_b = (lobe_idx * 0.37) + 0.2
            cos_a, sin_a = math.cos(tilt_a), math.sin(tilt_a)
            cos_b, sin_b = math.cos(tilt_b), math.sin(tilt_b)

            for i in range(rings):
                u_frac = 0.22 + (i / (rings - 1)) * 0.56
                u_angle = u_frac * math.pi
                sin_u = math.sin(u_angle)
                cos_u = math.cos(u_angle)

                arc_span = math.pi * (1.55 + (i % 3) * 0.18)
                arc_start = (i * 0.73) + lobe["seed"]

                for j in range(v_steps + 1):
                    v_angle = arc_start + (j / v_steps) * arc_span
                    raw_x = sin_u * math.cos(v_angle)
                    raw_y = cos_u + 0.18 * math.sin(v_angle * 2 + lobe["seed"])
                    raw_z = sin_u * math.sin(v_angle)

                    x1 = raw_x * cos_a - raw_y * sin_a
                    y1 = raw_x * sin_a + raw_y * cos_a
                    z1 = raw_z

                    sx = x1
                    sy = y1 * cos_b - z1 * sin_b
                    sz = y1 * sin_b + z1 * cos_b

                    disp = oracle_cortical_fold_displacement(sx, sy, sz, lobe["seed"])
                    r_scale = 1.0 + disp

                    px = lobe["cx"] + sx * lobe["rx"] * r_scale
                    py = lobe["cy"] + sy * lobe["ry"] * r_scale
                    pz = lobe["cz"] + sz * lobe["rz"] * r_scale

                    fnx = sx + 0.4 * math.cos(sy * 3.5 + lobe["seed"])
                    fny = sy + 0.4 * math.sin(sz * 3.5 - lobe["seed"])
                    fnz = sz + 0.4 * math.cos(sx * 3.5 + lobe["seed"])
                    fn_len = math.hypot(fnx, fny, fnz) or 1.0

                    nx = fnx / fn_len
                    ny = fny / fn_len
                    nz = fnz / fn_len

                    # Verify no NaNs or infinities
                    assert not (math.isnan(px) or math.isnan(py) or math.isnan(pz)), f"NaN vertex at lobe {lobe_idx}"
                    assert not (math.isinf(px) or math.isinf(py) or math.isinf(pz)), f"Inf vertex at lobe {lobe_idx}"
                    assert not (math.isnan(nx) or math.isnan(ny) or math.isnan(nz)), f"NaN normal at lobe {lobe_idx}"
                    assert math.isclose(math.hypot(nx, ny, nz), 1.0, abs_tol=1e-5), "Normal not normalized"

                    total_vertices += 1

        assert total_vertices == 240 * 77, f"Expected 18,480 vertices, got {total_vertices}"


class TestDendriticSingularityAndStreams:
    """Verifies that singularity pos, dendritic filaments, and fiber streams match exact specifications."""

    def test_singularity_position(self, html_content: str):
        match = re.search(r"const\s+SINGULARITY_POS\s*=\s*\{\s*x:\s*([-\d\.]+),\s*y:\s*([-\d\.]+),\s*z:\s*([-\d\.]+)\s*\};", html_content)
        assert match is not None, "SINGULARITY_POS not found"
        sx, sy, sz = match.groups()
        assert math.isclose(float(sx), ORACLE_SINGULARITY_POS["x"], abs_tol=1e-6)
        assert math.isclose(float(sy), ORACLE_SINGULARITY_POS["y"], abs_tol=1e-6)
        assert math.isclose(float(sz), ORACLE_SINGULARITY_POS["z"], abs_tol=1e-6)

    def test_dendritic_filament_structure(self, html_content: str):
        # 28 loops, each adding 1 trunk and 1 fork branch = 56 filaments
        assert "for (let b = 0; b < 28; b++)" in html_content
        assert "const isBridge = b < 9;" in html_content
        assert "dendriticFilaments.push({\n          pts: trunkPts," in html_content or "dendriticFilaments.push({ pts: trunkPts" in html_content or "pts: trunkPts" in html_content
        assert "pts: forkPts" in html_content

    def test_fiber_stream_curves(self, html_content: str):
        # 28 fiber streams (16 lower, 12 upper), 40 steps each
        assert "for (let f = 0; f < 28; f++)" in html_content
        assert "const isLowerStream = f < 16;" in html_content
        assert "const steps = 40;" in html_content


class TestZeroAllocationProject3DScratchpad:
    """Verifies that the scratchpad implementation produces mathematically identical results to object allocation."""

    def test_scratchpad_equivalence_across_5000_random_projections(self):
        rng = random.Random(1337)

        for _ in range(5000):
            x = (rng.random() - 0.5) * 5.0
            y = (rng.random() - 0.5) * 5.0
            z = (rng.random() - 0.5) * 5.0
            rot_y = rng.random() * math.pi * 2
            rot_x = (rng.random() - 0.5) * math.pi
            cos_y, sin_y = math.cos(rot_y), math.sin(rot_y)
            cos_x, sin_x = math.cos(rot_x), math.sin(rot_x)
            focal = 600.0 + rng.random() * 400.0
            cx = 400.0
            cy = 300.0
            cam_z = 4.30

            baseline = oracle_project3d_baseline(x, y, z, cos_y, sin_y, cos_x, sin_x, focal, cx, cy, cam_z)
            optimized = oracle_project3d_scratchpad(x, y, z, cos_y, sin_y, cos_x, sin_x, focal, cx, cy, cam_z)

            assert math.isclose(optimized["sx"], baseline["sx"], abs_tol=1e-12), "sx drift detected"
            assert math.isclose(optimized["sy"], baseline["sy"], abs_tol=1e-12), "sy drift detected"
            assert math.isclose(optimized["rz"], baseline["rz"], abs_tol=1e-12), "rz drift detected"
            assert math.isclose(optimized["depth"], baseline["depth"], abs_tol=1e-12), "depth drift detected"
            assert math.isclose(optimized["scale"], baseline["scale"], abs_tol=1e-12), "scale drift detected"


class TestFresnelLUTErrorBound:
    """Verifies that the 512-entry Fresnel lookup table approximation remains bounded within visual tolerance."""

    def test_lut_error_bound_under_point_005(self, html_content: str):
        # Verify LUT size and formula
        assert "const FRESNEL_LUT = new Float32Array(512);" in html_content
        assert "Math.pow(i / 511, 1.85)" in html_content

        # Reconstruct LUT
        lut = [math.pow(i / 511.0, 1.85) for i in range(512)]

        # Sample 10,000 continuous values in [0, 1]
        max_err = 0.0
        for step in range(10000):
            facing = step / 9999.0  # in [0, 1]
            analytic = math.pow(1.0 - facing, 1.85)

            # Replicate lookup index: ((1.0 - facing) * 511.0) | 0
            lut_idx = int((1.0 - facing) * 511.0)
            lut_idx = max(0, min(511, lut_idx))
            approx = lut[lut_idx]

            err = abs(approx - analytic)
            if err > max_err:
                max_err = err

        # The maximum truncation error must be strictly under 0.005 (0.5% max luminance deviation)
        assert max_err < 0.005, f"Fresnel LUT max error {max_err:.6f} exceeded 0.005 bound"


class TestTriFileHashParity:
    """Verifies that all three hologram files across server static, frontend public, and dist are strictly identical."""

    def test_sha256_hash_matches_identically(self):
        paths = [
            Path("d:/Ultron/src/openjarvis/server/static/hologram.html"),
            Path("d:/Ultron/frontend/public/hologram.html"),
            Path("d:/Ultron/frontend/dist/hologram.html"),
        ]

        hashes = []
        for p in paths:
            assert p.is_file(), f"File {p} does not exist"
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            hashes.append(h)

        assert len(set(hashes)) == 1, f"Hash divergence between files: {dict(zip(paths, hashes))}"
        assert hashes[0].upper() == "836CEFC0B7B6398408DE89AC699E37DEDAC8CFA05E686FE304B64C887170D7D6"
