"use client";

import * as React from "react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { CodeBox } from "./CodeBox";
import {
  runOptimize,
  SAMPLE_RTL,
  SAMPLE_NAME,
  DEFAULT_TOKEN,
  type OptOutcome,
} from "@/lib/optimizer";

export function Optimizer() {
  const [rtl, setRtl] = useState(SAMPLE_RTL);
  const [filename, setFilename] = useState(SAMPLE_NAME);
  const [prompt, setPrompt] = useState("Optimize this 4:1 mux for gate count; keep it equivalent.");
  const [token, setToken] = useState(DEFAULT_TOKEN);
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<string>("");
  const [outcome, setOutcome] = useState<OptOutcome | null>(null);
  const [error, setError] = useState<string>("");
  const abort = useRef<AbortController | null>(null);

  async function run() {
    if (!token.trim()) {
      setError("enter your X-RLHDL-Token to run a live optimization");
      return;
    }
    setRunning(true);
    setError("");
    setOutcome(null);
    setLog("starting…");
    abort.current = new AbortController();
    try {
      const res = await runOptimize({
        rtl,
        filename,
        prompt,
        token,
        mode: "harness",
        onProgress: (m) => setLog(m),
        signal: abort.current.signal,
      });
      setOutcome(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    f.text().then((t) => {
      setRtl(t);
      setFilename(f.name);
    });
  }

  const pct = outcome ? Math.round(outcome.areaImprovement * 100) : 0;

  return (
    <section id="optimizer" className="mx-auto max-w-6xl px-6 py-16 scroll-mt-20">
      <div className="font-[family-name:var(--font-jet)] text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
        live · soren&apos;s grader (Verilator + Yosys)
      </div>
      <h2 className="font-[family-name:var(--font-instrument)] text-4xl mt-2 mb-2">
        Optimize a real design
      </h2>
      <p className="text-foreground/70 max-w-prose mb-8">
        Edit the Verilog or upload a <code className="font-[family-name:var(--font-jet)]">.v</code> file,
        give a goal, and run. The backend rewrites it and reports the gate-count reduction with an
        equivalence proof — measured in gate count, not estimates.
      </p>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* input */}
        <div className="space-y-3">
          <div className="flex items-center gap-3 flex-wrap">
            <label className="inline-flex items-center rounded-md border border-border bg-card px-3 py-1.5 text-sm cursor-pointer hover:bg-secondary font-[family-name:var(--font-jet)]">
              upload .v
              <input type="file" accept=".v,.sv" className="hidden" onChange={onFile} />
            </label>
            <span className="font-[family-name:var(--font-jet)] text-xs text-muted-foreground">
              {filename}
            </span>
          </div>
          <textarea
            value={rtl}
            onChange={(e) => setRtl(e.target.value)}
            spellCheck={false}
            className="w-full h-64 rounded-lg border border-border bg-card p-3 font-[family-name:var(--font-jet)] text-[11.5px] leading-[1.5] resize-y"
          />
          <Input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="optimization goal"
            className="font-[family-name:var(--font-jet)] text-sm"
          />
          <div className="flex items-center gap-2">
            <Input
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="X-RLHDL-Token"
              className="font-[family-name:var(--font-jet)] text-xs max-w-[180px]"
            />
            <Button onClick={run} disabled={running} className="font-[family-name:var(--font-jet)]">
              {running ? "optimizing…" : "Run optimization"}
            </Button>
            {running && (
              <Button
                variant="outline"
                onClick={() => abort.current?.abort()}
                className="font-[family-name:var(--font-jet)]"
              >
                cancel
              </Button>
            )}
          </div>
          {(running || log) && (
            <div className="font-[family-name:var(--font-jet)] text-xs text-muted-foreground">
              {running && <span className="inline-block w-2 h-2 rounded-full bg-primary mr-2 animate-pulse" />}
              {log}
            </div>
          )}
          {error && (
            <div className="font-[family-name:var(--font-jet)] text-xs text-destructive">
              error: {error}
            </div>
          )}
        </div>

        {/* output */}
        <div className="space-y-4">
          {!outcome && !running && (
            <div className="rounded-lg border border-dashed border-border bg-card/50 p-8 text-center text-muted-foreground font-[family-name:var(--font-jet)] text-sm">
              results appear here — gate count, equivalence, optimized Verilog.
            </div>
          )}
          {outcome && (
            <>
              <div className="grid grid-cols-3 gap-3">
                <Metric k="baseline" v={`${outcome.baselineCells}`} u="cells" />
                <Metric k="optimized" v={`${outcome.bestCells}`} u="cells" accent />
                <Metric k="reduction" v={`−${pct}%`} u="gates" accent />
              </div>
              <div className="flex items-center gap-2">
                <Badge
                  className="font-[family-name:var(--font-jet)]"
                  variant={outcome.equivalent ? "default" : "destructive"}
                >
                  {outcome.equivalent ? "equivalence ✓ proven" : "not equivalent ✗"}
                </Badge>
                <span className="font-[family-name:var(--font-jet)] text-xs text-muted-foreground">
                  top module: {outcome.topModule}
                </span>
              </div>
              {outcome.bestRtl && (
                <CodeBox code={outcome.bestRtl} filename={`optimized · ${outcome.topModule}.v`} height={300} />
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function Metric({ k, v, u, accent }: { k: string; v: string; u: string; accent?: boolean }) {
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3">
      <div className="font-[family-name:var(--font-jet)] text-[9px] uppercase tracking-wide text-muted-foreground">
        {k}
      </div>
      <div
        className={`font-[family-name:var(--font-jet)] text-2xl font-bold leading-tight ${
          accent ? "text-primary" : ""
        }`}
      >
        {v}
      </div>
      <div className="font-[family-name:var(--font-jet)] text-[10px] text-muted-foreground">{u}</div>
    </div>
  );
}
