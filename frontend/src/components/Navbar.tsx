"use client";

import * as React from "react";
import { useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "motion/react";
import { Menu, X } from "lucide-react";

const LINKS = [
  { label: "Forge", href: "/" },
  { label: "Benchmark", href: "/benchmark" },
];

export function Navbar() {
  const [isOpen, setIsOpen] = useState(false);
  const toggle = () => setIsOpen(!isOpen);

  return (
    <div className="sticky top-0 z-50 flex justify-center w-full py-4 px-4 bg-background/70 backdrop-blur-sm">
      <div className="flex items-center justify-between px-5 py-2.5 bg-card rounded-full shadow-sm border border-border w-full max-w-3xl">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="grid place-items-center w-8 h-8 rounded-lg text-primary-foreground font-[family-name:var(--font-instrument)] text-xl bg-gradient-to-br from-primary to-[#2c7a37]">
            C
          </span>
          <span className="font-[family-name:var(--font-instrument)] text-xl leading-none">
            Cologic
          </span>
        </Link>

        <nav className="hidden md:flex items-center gap-7">
          {LINKS.map((l) => (
            <Link
              key={l.label}
              href={l.href}
              className="font-[family-name:var(--font-jet)] text-xs uppercase tracking-wide text-muted-foreground hover:text-foreground transition-colors"
            >
              {l.label}
            </Link>
          ))}
        </nav>

        <Link
          href="/"
          className="hidden md:inline-flex items-center justify-center px-4 py-1.5 text-xs font-medium text-primary-foreground bg-primary rounded-full hover:opacity-90 transition-opacity font-[family-name:var(--font-jet)]"
        >
          Run the minions
        </Link>

        <button className="md:hidden flex items-center" onClick={toggle} aria-label="menu">
          <Menu className="h-6 w-6" />
        </button>
      </div>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            className="fixed inset-0 bg-background z-50 pt-24 px-6 md:hidden"
            initial={{ opacity: 0, x: "100%" }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: "100%" }}
            transition={{ type: "spring", damping: 25, stiffness: 300 }}
          >
            <button className="absolute top-6 right-6 p-2" onClick={toggle} aria-label="close">
              <X className="h-6 w-6" />
            </button>
            <div className="flex flex-col space-y-6">
              {LINKS.map((l) => (
                <Link
                  key={l.label}
                  href={l.href}
                  className="text-base font-medium font-[family-name:var(--font-jet)]"
                  onClick={toggle}
                >
                  {l.label}
                </Link>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
