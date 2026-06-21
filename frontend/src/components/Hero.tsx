"use client";

import * as React from "react";
import { useEffect, useState } from "react";
import { CodeBox } from "./CodeBox";
import { SAMPLE_RTL, SAMPLE_NAME } from "@/lib/optimizer";

const AGENTS = [
  { role: "PLAN", color: "#5fa8d6", verb: "reads the module, finds redundant logic" },
  { role: "FORGE", color: "#3FA34D", verb: "rewrites the Verilog for fewer gates" },
  { role: "PROVE", color: "#c062a0", verb: "checks it stays logically equivalent" },
];

export function Hero() {
  const lineCount = SAMPLE_RTL.replace(/\n$/, "").split("\n").length;
  const [step, setStep] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setStep((s) => s + 1), 900);
    return () => clearInterval(id);
  }, []);

  const agent = AGENTS[step % AGENTS.length];
  const activeLine = 4 + (step % Math.max(1, lineCount - 6));

  return (
    <section id="top" className="mx-auto max-w-6xl px-6 pt-10 pb-16">
      <div className="grid md:grid-cols-2 gap-10 items-center">
        <div>
          <div className="font-[family-name:var(--font-jet)] text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
            RTL optimization · verifiable
          </div>
          <h1 className="font-[family-name:var(--font-instrument)] text-5xl leading-[1.05] mt-3 mb-4">
            Agents that optimize your Verilog.
          </h1>
          <p className="text-[15px] text-foreground/70 max-w-prose">
            Hand Cologic an RTL file and a goal. A loop of agents rewrites the Verilog for
            fewer gates and proves every version stays logically equivalent. The chip gets
            smaller because the <em>code</em> gets better, no manual tuning.
          </p>
          <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2 font-[family-name:var(--font-jet)] text-xs text-muted-foreground">
            <span><strong className="text-primary">−54%</strong> gates on mux4 (52→24)</span>
            <span className="text-foreground/30">·</span>
            <span>equivalence-proven</span>
            <span className="text-foreground/30">·</span>
            <span>FORGE = Kimi K2.7 Code on Fireworks</span>
          </div>
          <div className="mt-6 flex flex-wrap gap-3">
            {AGENTS.map((a) => (
              <div
                key={a.role}
                className="flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5"
                style={agent.role === a.role ? { borderColor: a.color } : undefined}
              >
                <span className="w-2 h-2 rounded-full" style={{ background: a.color }} />
                <span className="font-[family-name:var(--font-jet)] text-xs">{a.role}</span>
              </div>
            ))}
          </div>
          <p className="mt-3 font-[family-name:var(--font-jet)] text-xs text-muted-foreground">
            <span style={{ color: agent.color }}>{agent.role}</span> {agent.verb}
          </p>
          <div className="mt-7 flex gap-3">
            <a
              href="#optimizer"
              className="inline-flex items-center rounded-full bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:opacity-90 font-[family-name:var(--font-jet)]"
            >
              Optimize a design →
            </a>
            <a
              href="#benchmark"
              className="inline-flex items-center rounded-full border border-border px-5 py-2.5 text-sm font-medium hover:bg-secondary font-[family-name:var(--font-jet)]"
            >
              See the benchmark
            </a>
          </div>
        </div>

        <div>
          <CodeBox
            code={SAMPLE_RTL}
            filename={SAMPLE_NAME}
            activeLine={activeLine}
            activeColor={agent.color}
            height={340}
          />
        </div>
      </div>
    </section>
  );
}
