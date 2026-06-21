"use client";

import * as React from "react";
import { useEffect, useState } from "react";
import { fetchBenchmark, SNAPSHOT, type Benchmark as B } from "@/lib/data";

export function Benchmark() {
  const [data, setData] = useState<B>(SNAPSHOT);
  const [live, setLive] = useState(false);

  useEffect(() => {
    fetchBenchmark().then(({ data, live }) => {
      setData(data);
      setLive(live);
    });
  }, []);

  const upRel = data.baseline_pass_at_1
    ? (data.uplift / data.baseline_pass_at_1) * 100
    : 0;
  const short = (m: string) => m.split("/").pop() || m;

  return (
    <section id="benchmark" className="mx-auto max-w-6xl px-6 py-16 scroll-mt-20">
      <div className="font-[family-name:var(--font-jet)] text-[11px] uppercase tracking-[0.14em] text-muted-foreground flex items-center gap-2">
        <span
          className="w-1.5 h-1.5 rounded-full"
          style={{ background: live ? "var(--primary)" : "var(--muted-foreground)" }}
        />
        {live ? "live eval" : "snapshot"} · pass@1 · n={data.n_per_task}/task
      </div>
      <h2 className="font-[family-name:var(--font-instrument)] text-4xl mt-2 mb-2">
        Training moves the needle
      </h2>
      <p className="text-foreground/70 max-w-prose mb-8">
        Same held-out tasks, graded by Verilator against golden testbenches. The Cologic-trained
        model beats the base model on pass@1, measured, not claimed.
      </p>

      <div className="flex flex-wrap gap-4 mb-8">
        <Stat k={`${short(data.baseline_model)} · baseline`} v={data.baseline_pass_at_1.toFixed(3)} />
        <Stat
          k={`${short(data.cologic_model)} · cologic`}
          v={data.cologic_pass_at_1.toFixed(3)}
          accent
        />
        <Stat
          k="improvement"
          v={`${data.uplift >= 0 ? "+" : ""}${upRel.toFixed(1)}%`}
          sub={`${data.uplift >= 0 ? "+" : ""}${(data.uplift * 100).toFixed(1)} pts`}
          dark
        />
      </div>

      <div className="rounded-lg border border-border bg-card overflow-hidden">
        <div className="grid grid-cols-[1fr_auto_auto] gap-4 px-4 py-2.5 bg-secondary font-[family-name:var(--font-jet)] text-[10px] uppercase tracking-wide text-muted-foreground">
          <span>task</span>
          <span className="w-24 text-right">{short(data.baseline_model)}</span>
          <span className="w-24 text-right">{short(data.cologic_model)}</span>
        </div>
        {data.per_task.map((t) => (
          <div
            key={t.id}
            className="grid grid-cols-[1fr_auto_auto] gap-4 px-4 py-2.5 border-t border-border font-[family-name:var(--font-jet)] text-[12.5px]"
          >
            <span>{t.short}</span>
            <span className="w-24 text-right text-muted-foreground">
              {t.baseline.toFixed(2)} ({t.bp})
            </span>
            <span
              className="w-24 text-right font-semibold"
              style={t.cologic > t.baseline ? { color: "var(--primary)" } : undefined}
            >
              {t.cologic.toFixed(2)} ({t.cp})
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function Stat({
  k,
  v,
  sub,
  accent,
  dark,
}: {
  k: string;
  v: string;
  sub?: string;
  accent?: boolean;
  dark?: boolean;
}) {
  return (
    <div
      className="flex-1 min-w-[170px] rounded-lg border px-5 py-4"
      style={
        dark
          ? { background: "#06210c", borderColor: "#06210c" }
          : accent
            ? { borderColor: "var(--primary)" }
            : { borderColor: "var(--border)", background: "var(--card)" }
      }
    >
      <div
        className="font-[family-name:var(--font-jet)] text-[10px] uppercase tracking-wide"
        style={{ color: dark ? "#8fcf98" : "var(--muted-foreground)" }}
      >
        {k}
      </div>
      <div
        className="font-[family-name:var(--font-jet)] text-3xl font-bold leading-none mt-2"
        style={{ color: dark ? "#7BE05A" : accent ? "var(--primary)" : "var(--foreground)" }}
      >
        {v}
      </div>
      {sub && (
        <div className="font-[family-name:var(--font-jet)] text-[11px] mt-1" style={{ color: "#8fcf98" }}>
          {sub}
        </div>
      )}
    </div>
  );
}
