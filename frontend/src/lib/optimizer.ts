// Client for Soren's live RTL optimizer backend (Modal). Real gate-count
// reductions: upload Verilog → agents rewrite it → equivalence-checked result.

export const OPT_BASE = "https://yc-hack27--rl-hdl-web.modal.run";
// No token in source. Optionally injected at build via NEXT_PUBLIC_RLHDL_TOKEN
// (Vercel env); otherwise the user pastes their own X-RLHDL-Token in the UI.
export const DEFAULT_TOKEN = process.env.NEXT_PUBLIC_RLHDL_TOKEN ?? "";

// A small default design so the demo runs with zero setup (a 4:1 mux).
export const SAMPLE_NAME = "mux4.v";
export const SAMPLE_RTL = `// mux4.v — 4:1 multiplexer, 8-bit data
module mux4 (
  input  wire [7:0] a,
  input  wire [7:0] b,
  input  wire [7:0] c,
  input  wire [7:0] d,
  input  wire [1:0] sel,
  output reg  [7:0] y
);
  always @(*) begin
    case (sel)
      2'b00: y = a;
      2'b01: y = b;
      2'b10: y = c;
      default: y = d;
    endcase
  end
endmodule
`;

export type HistoryStep = {
  gen: number;
  cells: number;
  reward: number;
  equivalent: boolean;
  improved: boolean;
  area_um2?: number;
};
// Real backend result (harness mode).
export type OptResult = {
  task_id?: string;
  baseline_cells?: number;
  best_cells?: number;
  total_improvement?: number; // gate-count reduction fraction, 0..1
  plateaued?: boolean;
  history?: HistoryStep[];
  best_rtl?: string | Record<string, string>;
};
export type OptOutcome = {
  baselineCells: number;
  bestCells: number;
  areaImprovement: number; // gate-count reduction, 0..1
  equivalent: boolean;
  bestRtl: string;
  topModule: string;
  history: HistoryStep[];
};

export type Progress = (msg: string) => void;

function authHeaders(token: string): HeadersInit {
  return { "X-RLHDL-Token": token };
}

export async function runOptimize(opts: {
  rtl: string;
  filename: string;
  prompt: string;
  token?: string;
  mode?: "harness" | "sia";
  onProgress?: Progress;
  signal?: AbortSignal;
}): Promise<OptOutcome> {
  const token = opts.token || DEFAULT_TOKEN;
  const mode = opts.mode || "harness";
  const log = opts.onProgress || (() => {});

  log("uploading design…");
  const fd = new FormData();
  fd.append("files", new File([opts.rtl], opts.filename, { type: "text/plain" }));
  fd.append("prompt", opts.prompt);
  fd.append("mode", mode);
  fd.append("n_candidates", "3");
  fd.append("temperature", "0.7");
  fd.append("max_repair_rounds", "1");
  fd.append("n_vectors", "64");
  if (mode === "harness") fd.append("patience", "2");
  else fd.append("max_generations", "2");

  const sub = await fetch(`${OPT_BASE}/optimize`, {
    method: "POST",
    headers: authHeaders(token),
    body: fd,
    signal: opts.signal,
  });
  if (!sub.ok) throw new Error(`optimize submit failed (${sub.status})`);
  const { job_id, baseline_cells, top_module } = await sub.json();
  log(`parsing ${top_module || "design"} · baseline ${baseline_cells ?? "?"} cells`);

  // poll (up to ~18 min; the grader can be slow under load)
  for (let i = 0; i < 220; i++) {
    await new Promise((r) => setTimeout(r, 5000));
    if (opts.signal?.aborted) throw new Error("cancelled");
    const r = await fetch(`${OPT_BASE}/jobs/${job_id}`, {
      headers: authHeaders(token),
      signal: opts.signal,
    });
    if (!r.ok) throw new Error(`poll failed (${r.status})`);
    const j = await r.json();
    if (j.status === "running") {
      log(`optimizing… (${mode}, ${i * 5 + 5}s)`);
      continue;
    }
    if (j.status === "error") throw new Error(j.error || "optimizer error");
    if (j.status === "done") {
      log("done");
      return normalize(j.result as OptResult, baseline_cells, top_module);
    }
  }
  throw new Error("timed out");
}

function stripFences(s: string): string {
  return s
    .replace(/^```[a-zA-Z]*\n?/, "")
    .replace(/\n?```\s*$/, "")
    .trim();
}

function normalize(res: OptResult, baselineCells: number, topModule: string): OptOutcome {
  const history = res.history || [];
  const base = res.baseline_cells ?? baselineCells ?? 0;
  const best = res.best_cells ?? base;
  // equivalence: the winning (best_cells) step, else the last equivalent step
  const win =
    history.find((h) => h.cells === best && h.equivalent) ||
    [...history].reverse().find((h) => h.equivalent);
  const rawRtl =
    typeof res.best_rtl === "string"
      ? res.best_rtl
      : res.best_rtl
        ? Object.values(res.best_rtl)[0] || ""
        : "";
  return {
    baselineCells: base,
    bestCells: best,
    areaImprovement:
      res.total_improvement ?? (base ? Math.max(0, (base - best) / base) : 0),
    equivalent: win?.equivalent ?? best <= base, // backend only keeps equivalent improvements
    bestRtl: stripFences(rawRtl),
    topModule: topModule || "design",
    history,
  };
}
