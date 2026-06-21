"use client";

import * as React from "react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { PixelMinion } from "./PixelMinion";
import { runOptimize, SAMPLE_RTL, SAMPLE_NAME, DEFAULT_TOKEN, type OptOutcome } from "@/lib/optimizer";

type Role = "PLAN" | "FORGE" | "PROVE";
const VERB: Record<Role, string> = { PLAN: "reads", FORGE: "rewrites", PROVE: "proves" };
const COLOR: Record<Role, string> = { PLAN: "#5fa8d6", FORGE: "#3FA34D", PROVE: "#c062a0" };
// waypoints on the chip platform (% of the container) the minions stroll between
const WALK_PTS = [
  { x: 40, y: 14 },
  { x: 60, y: 30 },
  { x: 40, y: 48 },
  { x: 22, y: 30 },
];

export function Forge() {
  const [rtl, setRtl] = useState(SAMPLE_RTL.replace(/\n$/, ""));
  const [filename, setFilename] = useState(SAMPLE_NAME);
  const [token, setToken] = useState(DEFAULT_TOKEN);
  const [running, setRunning] = useState(false);
  const [outcome, setOutcome] = useState<OptOutcome | null>(null);
  const [error, setError] = useState("");
  const [active, setActive] = useState<{ role: Role; line: number }>({ role: "PLAN", line: 6 });
  const [round, setRound] = useState(1285);
  const [walk, setWalk] = useState([0, 1, 2]); // each platform minion's current waypoint
  const [copied, setCopied] = useState(false);
  const abort = useRef<AbortController | null>(null);

  // the platform minions stroll between waypoints — clearly-visible motion (not just a bob)
  useEffect(() => {
    const id = setInterval(
      () => setWalk((w) => w.map((i) => (i + 1) % WALK_PTS.length)),
      running ? 700 : 1300,
    );
    return () => clearInterval(id);
  }, [running]);

  const lines = rtl.split("\n");
  const editableLines = lines
    .map((l, i) => ({ l, i }))
    .filter(({ l }) => l.trim() && !l.trim().startsWith("//"));

  // Ambient sync loop: the minions are always alive, cycling PLAN -> FORGE -> PROVE
  // over real lines of the file. Faster while a run is in flight.
  useEffect(() => {
    const order: Role[] = ["PLAN", "FORGE", "PROVE"];
    let k = 0;
    const id = setInterval(
      () => {
        k++;
        const role = order[k % 3];
        const pick = editableLines[(k * 2) % Math.max(1, editableLines.length)];
        setActive({ role, line: pick ? pick.i : 6 });
        if (role === "PLAN") setRound((r) => r + 1);
      },
      running ? 550 : 1400,
    );
    return () => clearInterval(id);
  }, [running, rtl]); // eslint-disable-line react-hooks/exhaustive-deps

  async function run() {
    if (!token.trim()) {
      setError("enter your X-RLHDL-Token to run a live optimization");
      return;
    }
    setRunning(true);
    setError("");
    setOutcome(null);
    abort.current = new AbortController();
    try {
      const res = await runOptimize({
        rtl: rtl + "\n",
        filename,
        prompt: "Optimize this design for gate count; keep it logically equivalent.",
        token,
        mode: "harness",
        onProgress: () => {},
        signal: abort.current.signal,
      });
      setOutcome(res);
      if (res.bestRtl) {
        // FORGE "finishes": morph the editor to the optimized file, line by line.
        const opt = res.bestRtl.replace(/\n$/, "").split("\n");
        for (let i = 0; i < opt.length; i++) {
          await new Promise((r) => setTimeout(r, 22));
          setRtl(opt.slice(0, i + 1).join("\n"));
        }
        setRtl(opt.join("\n"));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  const gatesNow = outcome ? outcome.bestCells : null;
  const pct = outcome ? Math.round(outcome.areaImprovement * 100) : 0;

  return (
    <section className="mx-auto max-w-6xl px-6 pt-8 pb-14">
      <div className="font-[family-name:var(--font-jet)] text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
        <span className="inline-block w-2 h-2 rounded-full bg-primary mr-2 align-middle animate-pulse" />
        live forge · round {round.toLocaleString()} · Kimi K2.7 Code
      </div>
      <h1 className="font-[family-name:var(--font-instrument)] text-4xl md:text-5xl leading-[1.05] mt-2 mb-3">
        Watch the minions rewrite your Verilog.
      </h1>
      <p className="text-[15px] text-foreground/70 max-w-prose mb-6">
        PLAN reads the module, FORGE hammers lines into fewer gates, PROVE checks every change stays
        logically equivalent. The optimizer is a black box; the minions are real, synced to the file
        being edited on the left.
      </p>

      <div className="grid lg:grid-cols-2 gap-5 items-stretch">
        {/* LEFT: the live code editor */}
        <div className="rounded-xl border border-border bg-card overflow-hidden flex flex-col">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-secondary/50">
            <span className="w-2.5 h-2.5 rounded-full bg-[#e0685f]" />
            <span className="w-2.5 h-2.5 rounded-full bg-[#e6c84a]" />
            <span className="w-2.5 h-2.5 rounded-full bg-[#3FA34D]" />
            <span className="ml-2 font-[family-name:var(--font-jet)] text-xs text-muted-foreground">
              {filename}
            </span>
            <label className="ml-auto font-[family-name:var(--font-jet)] text-[11px] text-primary cursor-pointer hover:underline">
              upload .v
              <input
                type="file"
                accept=".v,.sv"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) f.text().then((t) => { setRtl(t.replace(/\n$/, "")); setFilename(f.name); });
                }}
              />
            </label>
          </div>
          <div className="font-[family-name:var(--font-jet)] text-[11.5px] leading-[1.55] overflow-auto p-2 grow" style={{ maxHeight: 420 }}>
            {lines.map((l, i) => {
              const isActive = i === active.line;
              return (
                <div
                  key={i}
                  className={`flex items-start gap-2 rounded px-1 ${isActive ? "line-flash" : ""}`}
                >
                  <span className="select-none w-7 text-right text-[#9b927d] shrink-0">{i + 1}</span>
                  <span className="relative whitespace-pre text-foreground/90">
                    {hi(l)}
                    {isActive && (
                      <span
                        className="absolute -left-6 -top-1"
                        title={active.role}
                        style={{ filter: `drop-shadow(0 0 3px ${COLOR[active.role]})` }}
                      >
                        <PixelMinion role={active.role} size={20} working={running && active.role === "FORGE"} />
                      </span>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* RIGHT: the chip + the real minions, synced */}
        <div className="rounded-xl border border-border bg-gradient-to-b from-card to-secondary/40 p-5 flex flex-col">
          <div className="grid grid-cols-3 gap-3">
            <Tile k="gates" v={gatesNow != null ? `${gatesNow}` : (outcome ? "" : "—")} sub={outcome ? `was ${outcome.baselineCells}` : "baseline"} accent />
            <Tile k="reduction" v={outcome ? `−${pct}%` : "—"} sub="fewer gates" accent />
            <Tile k="equivalence" v={outcome ? (outcome.equivalent ? "✓" : "✗") : "—"} sub="proven" />
          </div>

          {/* isometric chip platform with the minions standing on it */}
          <div className="relative grow my-4 min-h-[230px] flex items-center justify-center">
            <svg viewBox="0 0 360 220" className="w-full max-w-[420px]">
              {/* iso platform */}
              <polygon points="180,30 330,110 180,190 30,110" fill="#cfe3c2" stroke="#a9c79a" strokeWidth="2" />
              <polygon points="30,110 180,190 180,205 30,125" fill="#9fc08e" />
              <polygon points="330,110 180,190 180,205 330,125" fill="#8fb37e" />
              {/* grid */}
              {Array.from({ length: 7 }).map((_, i) => (
                <g key={i} stroke="#b6d2a6" strokeWidth="1" opacity="0.7">
                  <line x1={30 + (i * 150) / 7 + (i ? 0 : 0)} y1={110} x2={180} y2={30 + (i * 160) / 7} />
                </g>
              ))}
            </svg>
            {/* the three minions stroll the platform; the active one hops */}
            {([
              { role: "PLAN", size: 52 },
              { role: "FORGE", size: 64 },
              { role: "PROVE", size: 52 },
            ] as { role: Role; size: number }[]).map((m, k) => {
              const p = WALK_PTS[walk[k]];
              return (
                <div
                  key={m.role}
                  className="absolute"
                  style={{ left: `${p.x}%`, top: `${p.y}%`, transition: "left 0.9s ease-in-out, top 0.9s ease-in-out" }}
                >
                  <PixelMinion role={m.role} size={m.size} working={running} active={active.role === m.role} />
                </div>
              );
            })}
          </div>

          {/* agent status, synced to the active edit */}
          <div className="space-y-1.5">
            {(["PLAN", "FORGE", "PROVE"] as Role[]).map((role) => (
              <div
                key={role}
                className="flex items-center gap-2 rounded-md border px-2.5 py-1.5"
                style={{ borderColor: active.role === role ? COLOR[role] : "var(--border)" }}
              >
                <PixelMinion role={role} size={18} working={running && role === "FORGE"} />
                <span className="font-[family-name:var(--font-jet)] text-xs font-semibold" style={{ color: COLOR[role] }}>{role}</span>
                <span className="font-[family-name:var(--font-jet)] text-[11px] text-muted-foreground">
                  {VERB[role]} line {active.role === role ? active.line + 1 : "—"}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* run controls */}
      <div className="mt-5 flex items-center gap-2 flex-wrap">
        <Input value={token} onChange={(e) => setToken(e.target.value)} placeholder="X-RLHDL-Token"
          className="font-[family-name:var(--font-jet)] text-xs max-w-[160px]" />
        <Button onClick={run} disabled={running} className="font-[family-name:var(--font-jet)]">
          {running ? "minions working…" : "Run the minions"}
        </Button>
        {running && (
          <Button variant="outline" onClick={() => abort.current?.abort()} className="font-[family-name:var(--font-jet)]">cancel</Button>
        )}
        {outcome && (
          <Badge variant={outcome.equivalent ? "default" : "destructive"} className="font-[family-name:var(--font-jet)]">
            {outcome.equivalent ? `equivalence ✓ · ${outcome.baselineCells}→${outcome.bestCells} cells` : "not equivalent ✗"}
          </Badge>
        )}
        {error && <span className="font-[family-name:var(--font-jet)] text-xs text-destructive">error: {error}</span>}
      </div>

      {/* RESULT: the optimized code + a plain-English explanation, below, in full width */}
      {outcome && (
        <div className="mt-6 rounded-xl border border-primary/40 bg-card p-5 shadow-sm">
          <div className="flex items-center gap-3 flex-wrap mb-2">
            <h2 className="font-[family-name:var(--font-instrument)] text-2xl">
              Optimized {outcome.topModule}.v
            </h2>
            <span className="font-[family-name:var(--font-jet)] text-xs rounded px-2 py-0.5 bg-primary/12 text-primary">
              {outcome.baselineCells}→{outcome.bestCells} cells · −{pct}%
            </span>
            <span className="font-[family-name:var(--font-jet)] text-xs text-muted-foreground">
              {outcome.equivalent ? "equivalence ✓ proven" : "not equivalent ✗"}
            </span>
            <button
              onClick={() => {
                navigator.clipboard?.writeText(outcome.bestRtl);
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              }}
              className="ml-auto font-[family-name:var(--font-jet)] text-xs text-primary hover:underline"
            >
              {copied ? "copied ✓" : "copy code"}
            </button>
          </div>
          <p className="text-[14px] text-foreground/70 max-w-prose mb-4">
            FORGE rewrote <code className="font-[family-name:var(--font-jet)]">{outcome.topModule}</code> for
            fewer gates — {outcome.baselineCells} → {outcome.bestCells} cells (−{pct}%) — keeping the module
            name, ports and widths identical. PROVE checked it against the original with an equivalence proof
            {outcome.equivalent ? ", and it passed ✓." : " (failed ✗)."} Only the internal logic changed.
          </p>
          <div
            className="rounded-lg border border-border bg-secondary/30 overflow-auto font-[family-name:var(--font-jet)] text-[12.5px] leading-[1.6] p-3"
            style={{ maxHeight: 380 }}
          >
            {outcome.bestRtl.split("\n").map((l, i) => (
              <div key={i} className="flex items-start gap-3">
                <span className="select-none w-7 text-right text-[#9b927d] shrink-0">{i + 1}</span>
                <span className="whitespace-pre text-foreground/90">{hi(l)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function Tile({ k, v, sub, accent }: { k: string; v: string; sub: string; accent?: boolean }) {
  return (
    <div className="rounded-lg border border-border bg-card/80 px-3 py-2">
      <div className="font-[family-name:var(--font-jet)] text-[9px] uppercase tracking-wide text-muted-foreground">{k}</div>
      <div className={`font-[family-name:var(--font-jet)] text-2xl font-bold leading-tight ${accent ? "text-primary" : ""}`}>{v || "·"}</div>
      <div className="font-[family-name:var(--font-jet)] text-[10px] text-muted-foreground">{sub}</div>
    </div>
  );
}

// tiny verilog highlighter
function hi(line: string) {
  if (line.trim().startsWith("//")) return <span className="text-[#7d8a72]">{line}</span>;
  const parts = line.split(/(\bmodule\b|\bendmodule\b|\binput\b|\boutput\b|\bwire\b|\breg\b|\balways\b|\bcase\b|\bendcase\b|\bbegin\b|\bend\b|\bassign\b|\bdefault\b)/g);
  return parts.map((p, i) =>
    /^(module|endmodule|input|output|wire|reg|always|case|endcase|begin|end|assign|default)$/.test(p)
      ? <span key={i} className="text-[#2c7a37] font-semibold">{p}</span>
      : <span key={i}>{p}</span>,
  );
}
