import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Instrument_Serif } from "next/font/google";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const jetmono = JetBrains_Mono({ variable: "--font-jet", subsets: ["latin"] });
const instrument = Instrument_Serif({
  variable: "--font-instrument",
  subsets: ["latin"],
  weight: "400",
});

export const metadata: Metadata = {
  title: "Cologic · agents that optimize your Verilog",
  description:
    "Cologic optimizes RTL: agents rewrite your Verilog for fewer gates while proving it stays equivalent.",
};

import { Navbar } from "@/components/Navbar";

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetmono.variable} ${instrument.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <Navbar />
        <main className="flex-1">{children}</main>
        <footer className="border-t border-border">
          <div className="mx-auto max-w-6xl px-6 py-8 font-[family-name:var(--font-jet)] text-xs text-muted-foreground">
            Cologic · agents optimize Verilog for fewer gates, equivalence-checked. Optimizer runs
            live against the grader backend; benchmark numbers are real Verilator eval.
          </div>
        </footer>
      </body>
    </html>
  );
}
