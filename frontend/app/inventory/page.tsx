"use client";

import { RotateCcw } from "lucide-react";
import { AppShell, PageTitle } from "@/components/AppShell";
import { useSwapDesk } from "@/store/swapdesk";

export default function InventoryPage() {
  const { inventory, resetMockData } = useSwapDesk();

  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Inventory" }]}>
      <PageTitle
        title="Inventory"
        sub="Reservations made by the agent are locked until the exchange ships."
        right={
          <button
            type="button"
            onClick={resetMockData}
            className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-hairline bg-card/60 px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent/60"
            title="Clear the ticket queue and restore inventory defaults"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Reset Sample Data
            </button>
        }
      />
      <div className="panel overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr className="border-b border-hairline">
              {["SKU", "Product", "Size", "Available", "Reserved", "Warehouse"].map((h) => (
                <th key={h} className="px-5 py-3 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {inventory.map((i) => (
              <tr key={i.sku} className="hover:bg-accent/30">
                <td className="px-5 py-3 font-mono text-xs">{i.sku}</td>
                <td className="px-5 py-3">{i.name}</td>
                <td className="num px-5 py-3">{i.size}</td>
                <td className={`num px-5 py-3 ${i.stock === 0 ? "text-danger" : ""}`}>{i.stock}</td>
                <td className={`num px-5 py-3 ${i.res ? "text-success" : "text-muted-foreground"}`}>{i.res}</td>
                <td className="px-5 py-3 font-mono text-xs text-muted-foreground">{i.wh}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}
