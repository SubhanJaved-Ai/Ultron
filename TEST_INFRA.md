# E2E Test Infra: Ultron 3D Hologram Production Polish

## Test Philosophy
- Opaque-box, requirement-driven. No dependency on implementation design.
- Derived strictly from `ORIGINAL_REQUEST.md` and user-facing acceptance criteria.
- Methodology: Category-Partition + Boundary Value Analysis + Pairwise Combinatorial Testing + Real-World Workload Testing.

## Feature Inventory & Test Matrix
| # | Feature | Source | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---------|--------|:------:|:------:|:------:|:------:|
| 1 | R1: Hologram Performance & Cortex Preservation | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 2 | R2: System Theme Synchronization | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 3 | R3: Strict Wake Word & Operational States | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 4 | R4: Streamlined UI & Cyan Accent Theme | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |
| 5 | R5: Unified System Brain Routing & Mock Removal | ORIGINAL_REQUEST §R5 | 5 | 5 | ✓ | ✓ |

## Test Architecture
- Test runner: Python virtual environment pytest (`.venv\Scripts\pytest.exe`)
- Test suite file: `tests/e2e/test_hologram_production_e2e.py`
- Pass/fail semantics: Exit code 0, all assertions pass cleanly
- Directory layout:
  - `tests/e2e/` for end-to-end requirement suites
  - `tests/server/` for existing server/unit regression tests

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Continuous Voice Directive in Dark Mode with Real System Tool Action | R1, R2, R3, R5 | High |
| 2 | Dynamic Theme Switching during Active Neural Animation and Chat Submission | R1, R2, R4 | High |
| 3 | High-Noise Wake Word Gating: "Ultron" Activation vs "Jarvis" Rejection | R3, R4 | Medium |
| 4 | Multi-Model Brain Fallback and Real Telemetry Streaming without Mock Fallbacks | R4, R5 | High |
| 5 | End-to-End Operational Lifecycle: Standby -> Listening -> Executing -> Speaking -> Standby | R1, R3, R4, R5 | High |

## Coverage Thresholds
- Tier 1: ≥5 tests per requirement (≥25 tests)
- Tier 2: ≥5 boundary tests per requirement (≥25 tests)
- Tier 3: ≥10 pairwise interaction tests
- Tier 4: ≥5 full-scenario end-to-end tests
- **Total Minimum Threshold: ≥65 comprehensive E2E tests**

