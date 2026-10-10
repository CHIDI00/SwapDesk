"use client";

import { useState } from "react";
import { AppShell, PageTitle } from "@/components/AppShell";

const tables: Record<string, string[]> = {
  Orders: ["id TEXT PK", "customer_id TEXT", "sku TEXT", "delivered_at TIMESTAMPTZ", "status TEXT"],
  Return_Policy: ["category TEXT PK", "window_days INT", "swap_allowed BOOL", "requires_unworn BOOL"],
  inventory: ["sku TEXT PK", "size INT", "stock INT", "reserved INT", "warehouse TEXT"],
  shipping_labels: ["label_id TEXT PK", "op_id TEXT UNIQUE", "carrier TEXT", "status TEXT", "created_at TIMESTAMPTZ"],
  operations: ["op_id TEXT PK", "ticket_id TEXT", "tool TEXT", "status TEXT", "latency_ms INT"],
};

export default function DatabasePage() {
  const names = Object.keys(tables);
  const [sel, setSel] = useState<string>("Orders");

  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Database" }]}>
      <PageTitle title="Database" sub="op_id UNIQUE constraints enforce idempotency at the storage layer." />
      <div className="grid gap-4 md:grid-cols-[220px_minmax(0,1fr)]">
        <div className="panel flex gap-1 overflow-x-auto p-2 md:flex-col">
          {names.map((n) => (
            <button
              key={n}
              onClick={() => setSel(n)}
              className={`shrink-0 rounded-lg px-3 py-2 text-left font-mono text-xs transition-colors ${sel === n ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/50"}`}
            >
              {n}
            </button>
          ))}
        </div>
        <div className="panel min-w-0 p-5 font-mono text-sm">
          <p className="mb-3 text-success">CREATE TABLE {sel} (</p>
          {(tables[sel] ?? []).map((c) => (
            <p key={c} className="break-words pl-5 text-foreground/85">
              {c},
            </p>
          ))}
          <p className="mt-1 text-success">);</p>
        </div>
      </div>
    </AppShell>
  );
}
