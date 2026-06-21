# Generation 2 Improvements

## Analysis of Generation 1 Performance

### Results Summary
- mean_reward: 0.640 | mean_area_improvement: 0.281 | n_equivalent: 4/4

| Design     | ref_cells | cand_cells | area_improvement | reward |
|------------|-----------|------------|-----------------|--------|
| mul8       | 366       | 354        | +3.3%           | 0.516  |
| mux4       | 60        | 24         | +60.0%          | 0.800  |
| popcount8  | 27        | 27         | 0.0%            | 0.500  |
| share_mul  | 726       | 370        | +49.0%          | 0.745  |

### Environment Discovery
The log line `"baseline + 2 rewrites (temp=0.9, repair<=1)"` reveals that the test
environment sets `COLOGIC_N_CANDIDATES=2` and `COLOGIC_MAX_REPAIR=1` via env vars,
overriding our defaults of 6 and 2. With only 2 candidates and 1 repair round, each
call must be maximally effective.

### What Worked Well
- **share_mul**: Strategy 0 (arithmetic sharing) nailed it on the first try: 726→370 cells (+49%)
- **mux4**: Strategy 1 succeeded on the second try: 60→24 cells (+60%)
- **mul8**: Strategy 0 found the `assign p = a * b` simplification: 366→354 cells (+3.3%)

### What Failed
1. **popcount8 (0% improvement)** — both rewrites had `equiv=False, cells=n/a, reward≈0`
   indicating compile errors. The repair loop **never fired** due to the `r.info.get("compiled")`
   guard in the condition. Both attempts received zero repair chances.

2. **mul8 second candidate** — with hill climbing, the second candidate could have tried to
   push the 354-cell result further. Instead, it started fresh from the 366-cell baseline
   and again found the same 354-cell result.

3. **share_mul second candidate** — same issue: second candidate found the same 370-cell
   result rather than pushing further.

## Root Cause: Repair Loop Bug

```python
# BROKEN: compile errors get no repair chance
while (
    rounds < MAX_REPAIR_ROUNDS
    and r.info.get("compiled")   # <-- this guard blocks repair of compile errors!
    and not r.info.get("equivalent")
):
```

When both popcount8 candidates failed to compile, `r.info.get("compiled")` was falsy, so
no repair was ever attempted. Both attempts were wasted.

## Root Cause: No Adaptive Hill Climbing

When rewrite 0 succeeds (mul8: 354 cells, share_mul: 370 cells), rewrite 1 starts fresh
from the baseline rather than trying to push the improved result further. This misses
opportunities for incremental improvement.

## Improvements Implemented

### 1. Fix Repair Loop (Critical)
Remove the `compiled` guard so compile errors also receive repair attempts:
```python
# FIXED: repairs both compile errors AND equivalence failures
while rounds < MAX_REPAIR_ROUNDS and not r.info.get("equivalent"):
```

This gives popcount8's failed candidates a second chance via repair.

### 2. Adaptive Hill Climbing
After a candidate improves best_rtl, subsequent candidates use the improved version
as their starting point (refinement) rather than restarting from baseline:
- **If best_rtl improved**: Use `SYSTEM_REFINE` + `_refine_prompt` targeting the best result
- **If best_rtl unchanged**: Use `SYSTEM_REWRITE` + standard strategy on baseline

This means:
- mul8: candidate 1 tries to push 354→? cells instead of rediscovering 354
- share_mul: candidate 1 tries to push 370→? cells instead of rediscovering 370
- mux4/popcount8: if candidate 0 fails, candidate 1 tries a different approach on baseline

### 3. Comprehensive First Strategy
Replace the narrow strategy 0 ("share arithmetic under selects") with a broad
"circuit-aware" analysis prompt that covers ALL major optimization patterns:
- Arithmetic operator sharing (for mul-mux circuits)
- Binary adder tree (for popcount circuits)
- Single-operator assignment (for manually-coded multipliers)
- Mux simplification (for redundant mux structures)
- Strength reduction (for constant multiplies)

This gives the model the full menu and lets it choose based on circuit analysis.

### 4. Direct/Clean Rewrite as Strategy 1
When strategy 0 fails, strategy 1 takes a "just write it cleanly" approach:
- `assign p = a * b` for multipliers
- Explicit parallel sum for popcount: `a[0]+a[1]+...+a[7]`  
- Case statement for mux

These simple rewrites often outperform complex structural ones because the synthesis
tool can optimize clean code better.

### 5. Clean RTL in Prompts
Use `extract_module()` to strip markdown fences before including best_rtl in refine
prompts, preventing double-wrapping artifacts.

### 6. Fresh Messages for Repair
Use fresh message lists for repair (reference agent style) rather than appending to
the failed conversation, avoiding context contamination.

## Expected Impact

| Design    | Gen1 area | Expected Gen2 area | Reason |
|-----------|-----------|-------------------|--------|
| mul8      | +3.3%     | +3.3% to +10%     | Hill climbing from 354 cells |
| mux4      | +60.0%    | +60.0%            | Already near-optimal |
| popcount8 | 0.0%      | 0% to +15%        | Repair loop fix gives 2 repair chances |
| share_mul | +49.0%    | +49% to +55%      | Hill climbing from 370 cells |

## Non-Changes (Preserved from Gen1)
- Full trajectory logging for debugging
- All grading goes through `grade_opt_remote` (no LLM equivalence checks)
- Fail-loud on grader errors (no fallbacks)
- Module name/interface preservation emphasis
