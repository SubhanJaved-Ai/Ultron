# Progress: teamwork_explorer_survey_1

- Last visited: 2026-10-31T06:53:00Z
- Status: Deep investigation underway for R1 (Hologram Performance) and R2 (System Theme Synchronization).

## Key Discoveries
1. **R1 Performance Bottlenecks**:
   - The 3D hologram is implemented as a custom hardware-accelerated volumetric 3D projection engine in `src/openjarvis/server/static/hologram.html` (mirrored in `frontend/public/hologram.html` and `frontend/dist/hologram.html`).
   - Every frame in `stepFrame()`, `project3D()` generates ~24,000 ephemeral `{sx, sy, rz, depth, scale}` objects, and segment push batches generate another ~18,000 `{x1, y1, x2, y2}` objects per frame.
   - Total heap allocation rate is ~2.7M to 3.0M objects/second, inducing severe V8 Garbage Collection (GC) pauses and frame stutters.
   - Additional CPU bottlenecks: `Math.pow` called 18,480 times/frame inside the cortical ring striation loop; redundant double-stroking of thousands of segments in `ridgeFoldBatch` and `brightCrestBatch`; hundreds of unbatched `ctx.drawImage` calls in `lighter` composite mode.
   - The 12 cortical lobes (`CORTICAL_LOBES`), undulating gyri formula (`corticalFoldDisplacement`), dendritic singularity tree (56 branches), sweeping fiber streams (28 streams), and particle matrices can be preserved with 100% mathematical fidelity while eliminating 99% of allocations via zero-allocation structs and direct canvas path streaming.

2. **R2 Theme Synchronization Bottlenecks**:
   - `frontend/src/pages/HologramPage.tsx` hardcodes light background `#f8fafc` and white navbar styling with zero dark-theme CSS classes.
   - `HologramPage.tsx` has no communication with the iframe regarding system theme.
   - `hologram.html` defines all CSS tokens (`--bg-void: #f8fafc;`) as light mode, with white radial background gradients and white vignette (`box-shadow: inset 0 0 100px 25px rgba(255, 255, 255, 0.65)`). Additive blending (`lighter`) on white background completely washes out cyan glow.
   - System theme state is in `useAppStore` (`settings.theme`: 'light' | 'dark' | 'system').
   - Solution requires full dark mode token styling in `hologram.html`, dark mode wrapper in `HologramPage.tsx`, theme URL param + `postMessage` synchronization, and unified Cyan / Arc-reactor blue accent.

## Next Steps
- Complete test verification.
- Update BRIEFING.md.
- Author detailed analysis.md.
- Author handoff.md.
- Notify orchestrator parent.
