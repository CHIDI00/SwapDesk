"use client";

import { useEffect, useState } from "react";
import { AppShell, PageTitle } from "@/components/AppShell";
import { getInventory, type InventoryItem } from "@/lib/api";
import { Spinner } from "@/components/ui/spinner";
import { TableRowsSkeleton } from "@/components/ui/loading";

const PAGE = 100;

export default function InventoryPage() {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Initial load on mount and page change; guarded by cancelled flag.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    getInventory({ limit: PAGE, offset })
      .then((page) => {
        if (cancelled) return;
        setItems(page.items);
        setTotal(page.total);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Inventory failed to load");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [offset, reloadKey]);

  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Inventory" }]}>
      <PageTitle
        title="Inventory"
        sub="Live stock from the backend. Reservations made by the agent reduce availability."
      />
      {error && (
        <div className="panel mb-4 border-warning/20 p-4">
          <p className="text-sm text-warning">{error}</p>
          <button
            type="button"
            onClick={() => setReloadKey((k) => k + 1)}
            disabled={loading}
            className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-foreground underline disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading && <Spinner className="h-3.5 w-3.5" />}
            {loading ? "Retrying…" : "Retry"}
          </button>
        </div>
      )}
      <div className="panel overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr className="border-b border-hairline">
              {["SKU", "Size", "On hand", "Held", "Available"].map((h) => (
                <th key={h} className="px-5 py-3 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {loading && items.length === 0 && <TableRowsSkeleton rows={6} cols={5} />}
            {items.map((i) => (
              <tr key={`${i.sku}:${i.size}`} className="hover:bg-accent/30">
                <td className="px-5 py-3 font-mono text-xs">{i.sku}</td>
                <td className="num px-5 py-3">{i.size}</td>
                <td className="num px-5 py-3">{i.on_hand}</td>
                <td className={`num px-5 py-3 ${i.held ? "text-success" : "text-muted-foreground"}`}>{i.held}</td>
                <td className={`num px-5 py-3 ${i.available === 0 ? "text-danger" : ""}`}>{i.available}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex items-center justify-between">
        <span className="inline-flex items-center gap-2 font-mono text-[10px] text-muted-foreground/75">
          {loading && items.length > 0 && <Spinner className="h-3 w-3" />}
          OFFSET {offset} OF {total} ROWS
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={loading || offset === 0}
            onClick={() => setOffset((o) => Math.max(0, o - PAGE))}
            className="inline-flex items-center gap-1.5 rounded-lg border border-hairline bg-card/60 px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent/60 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Previous
          </button>
          <button
            type="button"
            disabled={loading || offset + PAGE >= total}
            onClick={() => setOffset((o) => o + PAGE)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-hairline bg-card/60 px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent/60 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading && items.length > 0 && <Spinner className="h-3.5 w-3.5" />}
            Next
          </button>
        </div>
      </div>
    </AppShell>
  );
}
