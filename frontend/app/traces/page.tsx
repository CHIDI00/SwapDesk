import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { AppShell } from "@/components/AppShell";

export const metadata = {
  title: "neatlogs Trace 7f3a-9042 — SwapDesk",
  description: "Raw neatlogs execution trace for ticket TCK-9042.",
  openGraph: {
    title: "neatlogs Trace — SwapDesk",
    description: "Raw operation-level execution trace.",
  },
};

const lines: [string, "info" | "ok" | "warn", string][] = [
  ["14:02:09.880", "info", "[INGEST] ticket=TCK-9042 intent=exchange size_from=42 size_to=43"],
  ["14:02:10.102", "info", "[POLICY] query Orders WHERE id='SD-48213' → delivered, 6d"],
  ["14:02:10.188", "ok", "[POLICY] Return_Policy window=30d swap_allowed=true → ELIGIBLE"],
  ["14:02:11.204", "ok", "[OP_RES_STOCK_01] reserve_replacement sku=AJ4-MIL-43 → RSV-55128 (84ms)"],
  ["14:02:11.391", "info", "[OP_GEN_LABEL_02] create_label idempotency_key=OP_GEN_LABEL_02"],
  ["14:02:19.391", "warn", "[OP_GEN_LABEL_02] ETIMEDOUT after 8000ms — retry suppressed"],
  ["14:02:19.402", "info", "[OP_CHK_STATUS_03] SELECT shipping_labels WHERE op_id='OP_GEN_LABEL_02'"],
  ["14:02:19.433", "ok", "[OP_CHK_STATUS_03] found LBL-77310 status=CREATED → reuse, no duplicate"],
  ["14:02:19.611", "ok", "[OP_FINAL_VERIFY] 3/3 assertions passed · db_state == planned_reply"],
  ["14:02:19.640", "ok", "[RESOLVE] ticket=TCK-9042 status=RESOLVED_AUTONOMOUS cost=$0.24 tokens=4,812"],
];

export default function TracePage() {
  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Active Traces", to: "/" }, { label: "7f3a-9042" }]}>
      <div className="mx-auto w-full max-w-6xl space-y-6">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">neatlogs trace</h1>
            <p className="mt-1 text-sm text-muted-foreground">trace_id 7f3a-9042-c1e8 · 10 events · 9.76s</p>
          </div>
          <Link href="/" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" /> Back to TCK-9042
          </Link>
        </header>
        <div className="panel overflow-x-auto p-4 font-mono text-xs leading-7 sm:p-6 sm:text-[13px]">
          {lines.map(([t, k, m]) => (
            <div key={t + m} className="flex gap-4 whitespace-nowrap">
              <span className="text-muted-foreground/60">{t}</span>
              <span className={k === "ok" ? "text-success" : k === "warn" ? "text-warning" : "text-foreground/80"}>{m}</span>
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
