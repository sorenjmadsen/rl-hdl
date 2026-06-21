"""Render a pitch-grade per-task pass-rate chart from an eval JSON.

  python -m cologic.chart_baseline [results.json] [out.png]

Input JSON shape (what baseline_local.py writes): {model, split, n, pass_at_1,
mean_reward, per_task:[{task_id, pass_rate, mean_reward}]}.
"""
import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

src = sys.argv[1] if len(sys.argv) > 1 else ".context/hud/baseline.json"
out = sys.argv[2] if len(sys.argv) > 2 else "charts/baseline_heldout.png"
d = json.load(open(src))

tasks = [t["task_id"] for t in d["per_task"]]
rates = [t["pass_rate"] for t in d["per_task"]]
p1 = d["pass_at_1"]
# green = solved, amber = partial (within-group spread → trainable), red = unsolved
colors = ["#2e7d32" if r >= 0.999 else "#c62828" if r <= 0.001 else "#f9a825" for r in rates]

fig, ax = plt.subplots(figsize=(8, 4.2))
bars = ax.bar(tasks, rates, color=colors, edgecolor="#222", linewidth=0.6, zorder=3)
ax.axhline(p1, ls="--", color="#1565c0", lw=1.6, zorder=2,
           label=f"pass@1 = {p1:.2f}")
for b, r in zip(bars, rates):
    ax.text(b.get_x() + b.get_width() / 2, r + 0.02, f"{r:.1f}",
            ha="center", va="bottom", fontsize=9)

ax.set_ylim(0, 1.08)
ax.set_ylabel("pass rate (n={})".format(d.get("n", "?")))
ax.set_title(f"Cologic baseline — {d.get('model','?')}\n{d.get('split','')} split · "
             f"pass@1 {p1:.2f} · amber = within-group spread (trainable)", fontsize=10)
ax.legend(loc="upper right", frameon=False)
ax.grid(axis="y", ls=":", alpha=0.5, zorder=0)
plt.xticks(rotation=30, ha="right", fontsize=8)
plt.tight_layout()
plt.savefig(out, dpi=160)
print("wrote", out)
