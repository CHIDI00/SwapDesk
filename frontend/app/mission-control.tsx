"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowUpRight, Check, ChevronDown, Clock3, ShieldAlert } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useSwapDesk } from "@/store/swapdesk";
import { Spinner } from "@/components/ui/spinner";
import { TableRowsSkeleton } from "@/components/ui/loading";
import type { AgentCase } from "@/lib/api";

type Filter = "all" | "active" | "needs-input" | "done" | "failed";

function matchesFilter(ticket: AgentCase, filter: Filter): boolean {
  if (filter === "all") return true;
  if (filter === "active")
    return ticket.execution_status === "queued" || ticket.execution_status === "running";
  if (filter === "needs-input") return ticket.execution_status === "waiting_input";
  if (filter === "done") return ticket.execution_status === "completed";
  return ticket.execution_status === "failed";
}

function outcomeTone(outcome: string | null): string {
  if (outcome === "arranged") return "bg-success";
  if (outcome === "denial" || outcome === "escalation") return "bg-warning";
  if (outcome === "clarification") return "bg-primary";
  return "bg-muted-foreground/40";
}

function executionTone(status: string): string {
  if (status === "failed") return "text-warning";
  if (status === "completed") return "text-success";
  return "text-primary";
}

export function MissionControl() {
  const {
    cases,
    summary,
    total,
    loading,
    refreshing,
    loadingMore,
    error,
    health,
    ready,
    refreshStatus,
    executionFilter,
    setExecutionFilter,
    hasMore,
    loadMore,
    reload,
  } = useSwapDesk();
  const [filter, setFilter] = useState<Filter>("all");
  const visibleTickets = cases.filter((ticket) => matchesFilter(ticket, filter));

  const queuedDepth = ready?.queued_depth ?? 0;
  const backendLabel =
    health === "online" ? "Online" : health === "offline" ? "Offline" : "Checking…";

  const execCounts = summary?.execution_status ?? {};
  const outcomeCounts = summary?.outcome ?? {};
  const arrangedCount = outcomeCounts.arranged ?? 0;
  const failedCount = execCounts.failed ?? 0;
  const activeCount =
    (execCounts.queued ?? 0) + (execCounts.running ?? 0) + (execCounts.waiting_input ?? 0);
  const completionRate = summary?.completion?.rate ?? "N/A";

  const kpis = [
    { label: "Total cases", value: `${total}`, detail: "Saved in this view", icon: Check },
    { label: "Arranged rate", value: completionRate, detail: `${arrangedCount} arranged`, icon: Check },
    { label: "Active", value: `${activeCount}`, detail: "Queued, running, or waiting", icon: Clock3 },
    { label: "Failed", value: `${failedCount}`, detail: "Ended in error", icon: ShieldAlert },
  ];

  const outcomeRows: Array<{ label: string; count: number; tone: string }> = [
    { label: "Arranged", count: outcomeCounts.arranged ?? 0, tone: "bg-success" },
    { label: "Clarification", count: outcomeCounts.clarification ?? 0, tone: "bg-primary" },
    { label: "Denial", count: outcomeCounts.denial ?? 0, tone: "bg-warning" },
    { label: "Escalation", count: outcomeCounts.escalation ?? 0, tone: "bg-warning" },
    { label: "Pending", count: outcomeCounts.pending ?? 0, tone: "bg-muted-foreground/40" },
  ];
  const outcomeMax = Math.max(1, ...outcomeRows.map((r) => r.count));

  const execRows: Array<{ label: string; count: number }> = [
    { label: "Queued", count: execCounts.queued ?? 0 },
    { label: "Running", count: execCounts.running ?? 0 },
    { label: "Waiting input", count: execCounts.waiting_input ?? 0 },
    { label: "Completed", count: execCounts.completed ?? 0 },
    { label: "Failed", count: execCounts.failed ?? 0 },
  ];
  const execMax = Math.max(1, ...execRows.map((r) => r.count));

  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Mission Control" }]} metrics={false}>
      <div className="space-y-6 pb-8">
        <section className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
              Operations overview <span className="text-success/70">/</span> saved cases
            </p>
            <h1 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">Mission Control</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Case volume, outcomes, and execution health from the saved case list.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs ${
                health === "offline"
                  ? "border-warning/25 bg-warning/[0.06] text-warning"
                  : "border-success/20 bg-success/[0.06] text-success"
              }`}
              title={ready?.note ?? backendLabel}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  health === "online"
                    ? "bg-success pulse-dot"
                    : health === "offline"
                      ? "bg-warning"
                      : "bg-muted-foreground"
                }`}
              />
              {backendLabel}
              {health === "online" && (
                <span className="font-mono text-[10px] text-muted-foreground">
                  Queue {queuedDepth}
                </span>
              )}
            </span>
            <select
              aria-label="Filter by execution status"
              className="cursor-pointer appearance-none rounded-lg border border-hairline bg-card/80 px-3 py-2 text-xs text-foreground outline-none"
              value={executionFilter}
              onChange={(event) => setExecutionFilter(event.target.value)}
            >
              <option value="">All executions</option>
              <option value="queued">Queued</option>
              <option value="running">Running</option>
              <option value="waiting_input">Waiting input</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
            </select>
            <button
              type="button"
              onClick={() => {
                void reload();
                void refreshStatus();
              }}
              disabled={refreshing}
              className="inline-flex items-center gap-2 rounded-lg border border-hairline bg-card/65 px-3 py-2 text-xs text-muted-foreground transition-colors hover:bg-accent/60 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {refreshing ? <Spinner className="h-3.5 w-3.5" /> : <Clock3 className="h-3.5 w-3.5" />}
              {refreshing ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        </section>

        {error && (
          <div className="panel border-warning/20 p-4">
            <p className="text-sm text-warning">{error}</p>
          </div>
        )}

        <section aria-label="Key indicators" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {kpis.map(({ label, value, detail, icon: Icon }, index) => (
            <article key={label} className="panel rise relative overflow-hidden p-5" style={{ animationDelay: `${index * 60}ms` }}>
              <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/[0.12] to-transparent" />
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-medium text-muted-foreground">{label}</p>
                  <p className="num mt-4 text-4xl font-semibold tracking-tight">{value}</p>
                </div>
                  <span className="grid h-9 w-9 place-items-center rounded-xl border border-hairline bg-[var(--surface)] text-muted-foreground">
                  <Icon className="h-4 w-4" />
                </span>
              </div>
              <p className="mt-3 text-xs text-foreground/75">{detail}</p>
            </article>
          ))}
        </section>

        <section className="grid gap-3 xl:grid-cols-2" aria-label="Distributions">
          <div className="panel space-y-4 p-5">
            <div className="flex items-baseline justify-between">
              <h2 className="font-display text-lg font-semibold tracking-tight">Outcomes</h2>
              <span className="font-mono text-[10px] text-muted-foreground/80">{total} CASES</span>
            </div>
            {outcomeRows.map((row) => (
              <div key={row.label}>
                <div className="mb-1.5 flex items-baseline justify-between text-xs">
                  <span className="text-foreground/85">{row.label}</span>
                  <span className="num font-mono text-muted-foreground">{row.count}</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-[var(--surface-strong)]">
                  <div className={`h-full rounded-full ${row.tone}`} style={{ width: `${Math.round((row.count / outcomeMax) * 100)}%` }} />
                </div>
              </div>
            ))}
          </div>
          <div className="panel space-y-4 p-5">
            <div className="flex items-baseline justify-between">
              <h2 className="font-display text-lg font-semibold tracking-tight">Execution states</h2>
              <span className="font-mono text-[10px] text-muted-foreground/80">{total} CASES</span>
            </div>
            {execRows.map((row) => (
              <div key={row.label}>
                <div className="mb-1.5 flex items-baseline justify-between text-xs">
                  <span className="text-foreground/85">{row.label}</span>
                  <span className="num font-mono text-muted-foreground">{row.count}</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-[var(--surface-strong)]">
                  <div className="h-full rounded-full bg-primary/70" style={{ width: `${Math.round((row.count / execMax) * 100)}%` }} />
                </div>
              </div>
            ))}
          </div>
        </section>

        <section aria-labelledby="executions-title">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
            <h2 id="executions-title" className="font-display text-xl font-semibold tracking-tight sm:text-2xl">
              Recent cases
            </h2>
            <label className="relative flex items-center gap-2 rounded-lg border border-hairline bg-card/80 py-2 pl-3 pr-9 text-xs text-muted-foreground transition-colors focus-within:border-success/40">
              <span className="text-[11px]">Filter</span>
              <select
                aria-label="Filter support executions"
                className="cursor-pointer appearance-none bg-transparent font-medium text-foreground outline-none"
                value={filter}
                onChange={(event) => setFilter(event.target.value as Filter)}
              >
                <option value="all">All</option>
                <option value="active">Active</option>
                <option value="needs-input">Action Required</option>
                <option value="done">Done</option>
                <option value="failed">Failed</option>
              </select>
              <ChevronDown className="pointer-events-none absolute right-3 h-3.5 w-3.5" />
            </label>
          </div>

          <div className="panel overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr className="border-b border-hairline">
                  {["Case", "Request", "Execution", "Outcome", "Run", ""].map((h) => (
                    <th key={h} className="px-5 py-3 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {loading && visibleTickets.length === 0 && (
                  <TableRowsSkeleton rows={5} cols={6} />
                )}
                {!loading && visibleTickets.length === 0 && !error && (
                  <tr>
                    <td colSpan={6} className="px-5 py-4 text-sm text-muted-foreground">
                      No cases yet. Submit one from Customer Simulation.
                    </td>
                  </tr>
                )}
                {visibleTickets.map((ticket) => (
                  <tr key={ticket.case_id} className="hover:bg-accent/30">
                    <td className="whitespace-nowrap px-5 py-3 font-mono text-xs">
                      <Link href={`/ticket/${ticket.case_id}`} className="transition-colors hover:text-foreground">
                        {ticket.case_id}
                      </Link>
                    </td>
                    <td className="max-w-[320px] truncate px-5 py-3">{ticket.message}</td>
                    <td className={`whitespace-nowrap px-5 py-3 font-mono text-xs ${executionTone(ticket.execution_status)}`}>
                      {ticket.execution_status}
                    </td>
                    <td className="whitespace-nowrap px-5 py-3">
                      <span className="mr-2 inline-block h-1.5 w-1.5 rounded-full align-middle">
                        <span className={`block h-full w-full rounded-full ${outcomeTone(ticket.outcome)}`} />
                      </span>
                      <span className="font-mono text-xs">{ticket.outcome ?? "pending"}</span>
                    </td>
                    <td className="whitespace-nowrap px-5 py-3 font-mono text-xs text-muted-foreground">
                      {ticket.current_run_id}
                    </td>
                    <td className="whitespace-nowrap px-5 py-3 text-right">
                      <Link
                        href={`/ticket/${ticket.case_id}`}
                        className="text-xs text-muted-foreground transition hover:text-foreground"
                        aria-label={`Open ${ticket.case_id}`}
                      >
                        <ArrowUpRight className="inline h-4 w-4" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex items-center justify-between border-t border-hairline pt-4">
            <span className="font-mono text-[10px] text-muted-foreground/75">
              SHOWING {visibleTickets.length.toString().padStart(2, "0")} OF {total.toString().padStart(2, "0")} CASES
            </span>
            <div className="flex items-center gap-3">
              {hasMore && (
                <button
                  type="button"
                  onClick={() => void loadMore()}
                  disabled={loadingMore}
                  className="inline-flex items-center gap-1.5 text-xs text-muted-foreground transition hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {loadingMore && <Spinner className="h-3.5 w-3.5" />}
                  {loadingMore ? "Loading…" : "Load more"}
                </button>
              )}
              <Link href="/inbox" className="group inline-flex items-center gap-1.5 text-xs text-muted-foreground transition hover:text-foreground">
                Open full inbox
                <ArrowUpRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
              </Link>
            </div>
          </div>
        </section>
      </div>
    </AppShell>
  );
}
