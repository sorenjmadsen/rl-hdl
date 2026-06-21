// Benchmark numbers — served by the optimizer backend's /state route, fallback
// to bundled snapshot.

export const STATE_URL = "https://yc-hack27--rl-hdl-web.modal.run/state";

export type Task = {
  id: string;
  short: string;
  baseline: number;
  cologic: number;
  bp: string;
  cp: string;
};
export type Benchmark = {
  baseline_model: string;
  cologic_model: string;
  baseline_pass_at_1: number;
  cologic_pass_at_1: number;
  uplift: number;
  gate: number;
  n_per_task: number;
  per_task: Task[];
};

// Bundled snapshot (real eval numbers) so the page renders if the store is down.
export const SNAPSHOT: Benchmark = {
  baseline_model: "Qwen/Qwen3-8B",
  cologic_model: "cologic-rtl",
  baseline_pass_at_1: 0.267,
  cologic_pass_at_1: 0.3,
  uplift: 0.033,
  gate: 0.6,
  n_per_task: 5,
  per_task: [
    { id: "ho_mux2_w16", short: "mux2_w16", baseline: 1.0, cologic: 1.0, bp: "5/5", cp: "5/5" },
    { id: "ho_cmp4", short: "cmp4", baseline: 0.0, cologic: 0.0, bp: "0/5", cp: "0/5" },
    { id: "ho_popcount16", short: "popcount16", baseline: 0.0, cologic: 0.0, bp: "0/5", cp: "0/5" },
    { id: "ho_max2", short: "max2", baseline: 0.4, cologic: 0.6, bp: "2/5", cp: "3/5" },
    { id: "ho_dec2to4", short: "dec2to4", baseline: 0.0, cologic: 0.0, bp: "0/5", cp: "0/5" },
    { id: "ho_gray2bin8", short: "gray2bin8", baseline: 0.2, cologic: 0.2, bp: "1/5", cp: "1/5" },
  ],
};

export async function fetchBenchmark(): Promise<{ data: Benchmark; live: boolean }> {
  try {
    const c = new AbortController();
    const to = setTimeout(() => c.abort(), 9000); // his /state can cold-start
    const r = await fetch(STATE_URL, { signal: c.signal, cache: "no-store" });
    clearTimeout(to);
    if (!r.ok) throw new Error("bad status");
    const rec = await r.json();
    const b = rec.benchmark || rec;
    if (b && typeof b.cologic_pass_at_1 === "number") return { data: b as Benchmark, live: true };
    throw new Error("no benchmark in record");
  } catch {
    return { data: SNAPSHOT, live: false };
  }
}
