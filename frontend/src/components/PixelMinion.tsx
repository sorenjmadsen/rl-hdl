"use client";

import * as React from "react";

// Cute 8-bit minion sprite (NOT realistic). Blocky body, two eyes, little legs.
// FORGE carries a hammer that swings when `working`. Roles: PLAN / FORGE / PROVE.

type Role = "PLAN" | "FORGE" | "PROVE";

const SKIN: Record<Role, { body: string; dark: string; tool: "hammer" | "lens" | "check" }> = {
  PLAN: { body: "#5fa8d6", dark: "#3b7fae", tool: "lens" },
  FORGE: { body: "#3FA34D", dark: "#2c7a37", tool: "hammer" },
  PROVE: { body: "#c062a0", dark: "#9c4a80", tool: "check" },
};

// 1px = one "pixel" cell; the svg is scaled by `size`.
export function PixelMinion({
  role,
  size = 48,
  working = false,
  active = false,
}: {
  role: Role;
  size?: number;
  working?: boolean;
  active?: boolean;
}) {
  const s = SKIN[role];
  const px = size / 16; // 16x16 logical grid
  const R = (x: number, y: number, w: number, h: number, fill: string) => (
    <rect x={x * px} y={y * px} width={w * px} height={h * px} fill={fill} />
  );
  return (
    <div
      style={{ width: size, height: size * 1.15 }}
      className={active ? "minion-active" : working ? "minion-bob-fast" : "minion-bob"}
    >
      <svg width={size} height={size * 1.15} viewBox={`0 0 ${size} ${size * 1.15}`} shapeRendering="crispEdges">
        {/* shadow */}
        <ellipse cx={size / 2} cy={size * 1.1} rx={size * 0.28} ry={px * 1.2} fill="rgba(40,30,10,0.18)" />
        {/* legs */}
        {R(5, 14, 2, 2, s.dark)}
        {R(9, 14, 2, 2, s.dark)}
        {/* body */}
        {R(4, 7, 8, 7, s.body)}
        {R(3, 8, 1, 5, s.body)}
        {R(12, 8, 1, 5, s.body)}
        {/* head cap */}
        {R(5, 5, 6, 2, s.dark)}
        {R(7, 3, 2, 2, s.dark)}
        {/* face plate */}
        {R(5, 8, 6, 3, "#f3efe2")}
        {/* eyes */}
        {R(6, 9, 1, 1, "#1c1917")}
        {R(9, 9, 1, 1, "#1c1917")}
        {/* belt */}
        {R(4, 12, 8, 1, s.dark)}
        {/* tool */}
        {s.tool === "hammer" && (
          <g
            className={working ? "hammer-swing" : "hammer-rest"}
            style={{ transformOrigin: `${12 * px}px ${10 * px}px` }}
          >
            {R(12, 9, 1, 4, "#7a5c3a")}
            {R(11, 6, 4, 2, "#8a8f98")}
          </g>
        )}
        {s.tool === "lens" && (
          <g>
            <circle cx={13 * px} cy={9.5 * px} r={2 * px} fill="none" stroke="#cdbf9a" strokeWidth={px} />
            {R(14, 11, 2, 1, "#7a5c3a")}
          </g>
        )}
        {s.tool === "check" && (
          <g>
            {R(12, 9, 1, 1, s.dark)}
            {R(13, 10, 1, 1, s.dark)}
            {R(14, 7, 1, 3, s.dark)}
          </g>
        )}
      </svg>
    </div>
  );
}

export const MINION_ROLES: Role[] = ["PLAN", "FORGE", "PROVE"];
