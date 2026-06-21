"use client";

import * as React from "react";
import { useEffect, useRef, useState } from "react";

// Light-themed isometric 8x8 PE lattice with animated PLAN/FORGE/PROVE minions.
// The fun, restored — agents walk the array the optimizer is working on.

const N = 8;
const TW = 46; // tile width
const TH = 26; // tile height
const OX = 300; // origin x
const OY = 40; // origin y

const AGENTS = [
  { role: "PLAN", color: "#3b82c4", glow: "rgba(59,130,196,0.5)" },
  { role: "FORGE", color: "#3FA34D", glow: "rgba(63,163,77,0.5)" },
  { role: "PROVE", color: "#b8568f", glow: "rgba(184,86,143,0.5)" },
];

function iso(i: number, j: number): [number, number] {
  return [OX + (j - i) * (TW / 2), OY + (j + i) * (TH / 2)];
}

type Mini = { role: string; color: string; glow: string; i: number; j: number; ti: number; tj: number; p: number };

export function Foundry() {
  const [busy] = useState(false);
  const dotsRef = useRef<(SVGGElement | null)[]>([]);
  const pulseRef = useRef<Record<string, SVGPathElement | null>>({});
  const minis = useRef<Mini[]>(
    AGENTS.map((a, k) => ({
      ...a,
      i: k * 2,
      j: k * 2 + 1,
      ti: Math.floor((k * 5 + 2) % N),
      tj: Math.floor((k * 3 + 4) % N),
      p: 0,
    })),
  );

  useEffect(() => {
    let raf = 0;
    const speed = busy ? 0.04 : 0.018;
    const tick = () => {
      minis.current.forEach((m, k) => {
        m.p += speed;
        if (m.p >= 1) {
          m.p = 0;
          m.i = m.ti;
          m.j = m.tj;
          m.ti = Math.floor(Math.random() * N);
          m.tj = Math.floor(Math.random() * N);
          // light up the destination PE
          const key = `${m.ti}-${m.tj}`;
          const cell = pulseRef.current[key];
          if (cell) {
            cell.style.transition = "none";
            cell.style.fill = "color-mix(in oklch, var(--primary) 30%, var(--card))";
            requestAnimationFrame(() => {
              cell.style.transition = "fill 1.1s ease";
              cell.style.fill = "";
            });
          }
        }
        const ci = m.i + (m.ti - m.i) * m.p;
        const cj = m.j + (m.tj - m.j) * m.p;
        const [x, y] = iso(ci, cj);
        const g = dotsRef.current[k];
        if (g) g.setAttribute("transform", `translate(${x.toFixed(1)},${(y - 7).toFixed(1)})`);
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [busy]);

  const tiles = [];
  for (let i = 0; i < N; i++)
    for (let j = 0; j < N; j++) {
      const [x, y] = iso(i, j);
      tiles.push({ i, j, x, y });
    }

  return (
    <section id="showcase" className="mx-auto max-w-6xl px-6 py-16 scroll-mt-20">
      <div className="font-[family-name:var(--font-jet)] text-[11px] uppercase tracking-[0.14em] text-muted-foreground flex items-center gap-2">
        <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" /> live foundry
      </div>
      <h2 className="font-[family-name:var(--font-instrument)] text-4xl mt-2 mb-2">
        Agents on the array
      </h2>
      <p className="text-foreground/70 max-w-prose mb-8">
        PLAN, FORGE and PROVE walk the 8×8 processing-element array your RTL synthesizes into,
        probing cells, rewriting logic, proving equivalence. Every gate they remove makes the
        silicon smaller.
      </p>

      <div className="rounded-xl border border-border bg-gradient-to-b from-card to-secondary/40 p-6 shadow-sm">
        <svg viewBox="0 0 600 360" className="w-full" style={{ overflow: "visible" }}>
          <defs>
            <filter id="soft" x="-40%" y="-40%" width="180%" height="180%">
              <feDropShadow dx="0" dy="2" stdDeviation="2" floodColor="#000" floodOpacity="0.12" />
            </filter>
          </defs>
          {/* tiles */}
          {tiles.map(({ i, j, x, y }) => {
            const top = `M ${x} ${y - TH / 2} L ${x + TW / 2} ${y} L ${x} ${y + TH / 2} L ${x - TW / 2} ${y} Z`;
            const h = 8;
            const left = `M ${x - TW / 2} ${y} L ${x} ${y + TH / 2} L ${x} ${y + TH / 2 + h} L ${x - TW / 2} ${y + h} Z`;
            const right = `M ${x + TW / 2} ${y} L ${x} ${y + TH / 2} L ${x} ${y + TH / 2 + h} L ${x + TW / 2} ${y + h} Z`;
            return (
              <g key={`${i}-${j}`} filter="url(#soft)">
                <path d={left} fill="color-mix(in oklch, var(--primary) 8%, #d9cfb6)" />
                <path d={right} fill="color-mix(in oklch, var(--primary) 4%, #cfc4a8)" />
                <path
                  ref={(el) => {
                    pulseRef.current[`${i}-${j}`] = el;
                  }}
                  d={top}
                  fill={(i + j) % 2 ? "var(--accent)" : "var(--card)"}
                  stroke="var(--border)"
                  strokeWidth={1}
                  style={{ transition: "fill 1.1s ease" }}
                />
                <circle cx={x} cy={y} r={2} fill="var(--primary)" opacity={0.25} />
              </g>
            );
          })}
          {/* minions */}
          {minis.current.map((m, k) => (
            <g
              key={m.role}
              ref={(el) => {
                dotsRef.current[k] = el;
              }}
            >
              <circle r={9} fill={m.glow} opacity={0.6} />
              <circle r={5} fill={m.color} stroke="#fff" strokeWidth={1.5} />
            </g>
          ))}
        </svg>

        <div className="mt-4 flex flex-wrap gap-4 justify-center">
          {AGENTS.map((a) => (
            <div key={a.role} className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: a.color }} />
              <span className="font-[family-name:var(--font-jet)] text-xs text-muted-foreground">
                {a.role}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
