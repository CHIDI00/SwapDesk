"use client";

import Link from "next/link";
import { StatusPill } from "@/components/AppShell";
import { useSwapDesk } from "@/store/swapdesk";
import type { AgentCase } from "@/lib/api";

function pillFor(c: AgentCase): "success" | "warning" | "danger" | "idle" {
  if (c.execution_status === "failed") return "danger";
  if (c.execution_status === "waiting_input") return "warning";
  if (c.outcome === "escalation") return "warning";
  if (c.outcome === "denial") return "danger";
  if (c.outcome === "arranged") return "success";
  return "idle";
}

export function InboxList() {
  const { cases, total, loading, error, hasMore, loadMore, refresh } = useSwapDesk();

  return (
    <>
      {error && (
        <div className="panel mb-4 border-warning/20 p-4">
          <p className="text-sm text-warning">{error}</p>
          <button
            type="button"
            onClick={() => void refresh()}
            className="mt-2 text-xs font-medium text-foreground underline"
          >
            Retry
          </button>
        </div>
      )}
      <div className="panel divide-y divide-hairline overflow-hidden">
        {loading && cases.length === 0 && (
          <p className="p-5 text-sm text-muted-foreground">Loading saved cases…</p>
        )}
        {!loading && cases.length === 0 && !error && (
          <p className="p-5 text-sm text-muted-foreground">
            No cases yet. Submit one from Customer Simulation.
          </p>
        )}
        {cases.map((t) => (
          <Link
            key={t.case_id}
            href={`/ticket/${t.case_id}`}
            className="flex flex-col gap-2 p-4 transition-colors hover:bg-accent/40 sm:flex-row sm:items-center sm:gap-4 sm:p-5"
          >
            <div className="flex items-center justify-between gap-3 sm:w-40 sm:shrink-0 sm:flex-col sm:items-start sm:gap-1">
              <span className="font-mono text-xs text-muted-foreground">{t.case_id}</span>
              <span className="truncate text-sm font-semibold">
                {t.outcome ?? t.execution_status}
              </span>
            </div>
            <p className="min-w-0 flex-1 text-sm leading-relaxed text-muted-foreground">{t.message}</p>
            <div className="flex items-center gap-3">
              <StatusPill status={pillFor(t)} />
              <span className="font-mono text-xs text-muted-foreground">{t.current_run_id}</span>
            </div>
          </Link>
        ))}
      </div>
      {hasMore && (
        <button
          type="button"
          onClick={() => void loadMore()}
          className="mt-4 rounded-lg border border-hairline bg-card/60 px-4 py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent/60"
        >
          Load more
        </button>
      )}
      <p className="mt-3 font-mono text-[10px] text-muted-foreground/75">
        SHOWING {cases.length.toString().padStart(2, "0")} OF {total.toString().padStart(2, "0")} CASES
      </p>
    </>
  );
}
