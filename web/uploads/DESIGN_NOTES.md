# Modal GPU Glossary - Chip Design Reference Screenshots

Source: https://modal.com/gpu-glossary/device-hardware/cuda-device-architecture

These screenshots are captured from Modal's GPU Glossary as design references for making the Cologic chip rendering more realistic. Be mindful of overtraining — use these for structural/layout inspiration, not pixel-perfect replication.

---

## Key Design Principles from Modal's Approach

### 1. Color Coding by Function Type (Most Important)
- **Green**: Compute units (INT32, FP32 cores, ALUs, CUDA Cores)
- **Pink/Maroon**: Specialized compute (Tensor Cores, FP64)
- **Orange/Yellow**: Scheduling & control (Warp Schedulers, Dispatch Units)
- **Blue/Cyan**: Memory & caches (L1/L2, Shared Memory, Register Files)
- **Teal**: Instruction caches, constants caches

### 2. Clean Block Layout (NOT busy lines/routes)
- Blocks are **flat-filled rectangles** with thin borders
- NO red/violet metal routes or GDS-layer textures
- Realism comes from **proper structural hierarchy**, not visual noise
- Labels inside blocks are small monospace text

### 3. Hierarchical Nesting
- SM contains 4 quadrants, each with its own Warp Scheduler + cores
- Each quadrant has: L0 Instruction Cache > Warp Scheduler > Dispatch > Register File > Cores grid > LD/ST units
- The quadrants sit inside a shared L1 + Shared Memory footer bar
- This nesting = realism. Not textures.

### 4. Grid Regularity
- Core grids are perfectly aligned (8x16 or similar)
- Each cell is labeled (INT32, FP32, FP64, etc.)
- Spacing is uniform — no jitter, no artistic randomness

### 5. Terminal/Dark Theme Aesthetic
- Dark background (#0a0f0a or similar very dark green-black)
- Green monospace text (like a terminal)
- Thin 1px borders on blocks
- Subtle glow/brightness on active elements
- This matches Cologic's existing dark foundry theme

---

## Screenshot Index

| File | Content | Key Takeaway |
|------|---------|--------------|
| 01-overview-fixed-pipeline-g71 | G71 fixed-pipeline architecture (pre-CUDA) | Hierarchical block layout with clean borders |
| 02-g71-pipeline-diagram-zoom | Zoomed G71 pipeline blocks | How blocks nest: Vertex Shader > Fragment Shader > Crossbar > Buffers |
| 03-unified-g80-architecture | G80 unified architecture (first CUDA) | **THE key reference**: 8 identical SM blocks + L2 + FB memory. Color-coded: green SPs, pink TFs, yellow L1/L2 |
| 04-g80-unified-arch-zoom | Zoomed G80 with color coding | Color hierarchy: green compute, pink texture, yellow cache, all on dark bg |
| 05-h100-sm-architecture | Full H100 SM with 4 quadrants | **Best structural reference**: 4 processing blocks with shared L1/shared memory footer |
| 06-h100-sm-detailed-zoom | Zoomed H100 SM internals | Individual core labels (INT32, FP32, FP64), Tensor Core blocks, LD/ST units, SFU — all in a grid |
| 07-sm-bottom-with-caption | SM bottom half + Tensor Memory Accelerator bar | How memory hierarchy bars span the full width below compute |
| 08-cpu-vs-gpu-compute-diagram | CPU vs GPU silicon area comparison | Simple but effective: Control/Cache vs Compute area visualization |
| 09-cpu-vs-gpu-zoom | Zoomed CPU vs GPU | Clean flat blocks with labels: CONTROL, ALU, CACHE |
| 10-sm-architecture-hopper | Hopper SM90 architecture page | Same H100 SM diagram + Tesla SM for comparison |
| 11-tesla-sm-original-architecture | Original Tesla SM (simple) | Simpler architecture: Instruction Cache > MT Issue > Constants Cache > RF > 4 Cores + SFU |
| 12-tesla-sm-zoom-clean | Zoomed Tesla SM blocks | **Cleanest reference**: just labeled rectangles, no textures, pure structure |
| 14-tensor-core-with-sm | Tensor Core page with SM diagram | Shows Tensor Core highlighted within SM context |
| 16-tensor-core-register-diagram | Register usage in Tensor Core MMA | Matrix register visualization: R20, R24 = R12, R14 @ R11, R17 |

---

## Recommendations for Cologic Chip Rendering

### DO:
- Use flat color-coded blocks for different unit types
- Keep thin 1px borders (no thick outlines)
- Label blocks with small monospace text (INT32, FP32, etc.)
- Show proper hierarchy: SM > Quadrant > Core Grid > Individual Cores
- Use the green/pink/orange/blue color scheme
- Keep spacing uniform and grid-like

### DON'T:
- Add red/violet metal routes or GDS texture overlays
- Add random lines across the chip surface
- Use thick borders or drop shadows on blocks
- Add noise/grain textures to simulate silicon
- Over-render with too many visual layers

### The "just enough realism" sweet spot:
Realism comes from **correct architectural structure** (proper nesting, right number of cores, correct hierarchy) rendered with **clean flat blocks and consistent color coding**. The surface should feel like a technical diagram from an NVIDIA white paper, not a photograph of a physical die.
