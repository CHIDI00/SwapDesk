"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowUpRight,
  Check,
  ChevronDown,
  CircleDollarSign,
  Clock3,
  PackageCheck,
  ShieldAlert,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useSwapDesk } from "@/store/swapdesk";
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

function statusLabel(ticket: AgentCase): string {
  return ticket.outcome ?? ticket.execution_status;
}

export function MissionControl() {
  const {
    cases,
    summary,
    total,
    loading,
    error,
    executionFilter,
    setExecutionFilter,
    hasMore,
    loadMore,
    refresh,
  } = useSwapDesk();
  const [filter, setFilter] = useState<Filter>("all");
  const visibleTickets = cases.filter((ticket) => matchesFilter(ticket, filter));

  const execCounts = summary?.execution_status ?? {};
  const outcomeCounts = summary?.outcome ?? {};
  const activeCount =
    (execCounts.queued ?? 0) + (execCounts.running ?? 0) + (execCounts.waiting_input ?? 0);
  const arrangedCount = outcomeCounts.arranged ?? 0;
  const completionRate = total > 0 ? `${Math.round((arrangedCount / total) * 100)}%` : "N/A";

  const metrics = [
    {
      label: "Completion Rate",
      value: completionRate,
      detail: `${arrangedCount} arranged of ${total} cases`,
      icon: Check,
      tone: "green",
      footnote: "From the saved case list",
    },
    {
      label: "Active Cases",
      value: `${activeCount}`,
      detail: "Queued, running, or waiting",
      icon: Clock3,
      tone: "green",
      footnote: "Polls while active",
    },
    {
      label: "Needs Input",
      value: `${execCounts.waiting_input ?? 0}`,
      detail: "Waiting on a reply",
      icon: ShieldAlert,
      tone: "green",
      footnote: "Reply on the ticket page",
    },
    {
      label: "Cost per execution",
      value: "Demo Mode",
      detail: "No backend billed",
      icon: CircleDollarSign,
      tone: "neutral",
      footnote: "Requests counted per run",
    },
  ];

  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Mission Control" }]} metrics={false}>
      <div className="space-y-8 pb-8">
        <section className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
              Operations overview <span className="text-success/70">/</span> saved cases
            </p>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <h1 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">Mission Control</h1>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              Autonomous support performance, policy safety, and live execution health.
            </p>
          </div>
          <div className="flex items-center gap-2">
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
              onClick={() => void refresh()}
              className="inline-flex items-center gap-2 rounded-lg border border-hairline bg-card/65 px-3 py-2 text-xs text-muted-foreground transition-colors hover:bg-accent/60"
            >
              <Clock3 className="h-3.5 w-3.5" />
              Refresh
            </button>
          </div>
        </section>

        {error && (
          <div className="panel border-warning/20 p-4">
            <p className="text-sm text-warning">{error}</p>
          </div>
        )}

        <section aria-label="Agent performance metrics" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {metrics.map(({ label, value, detail, icon: Icon, tone, footnote }, index) => (
            <article
              key={label}
              className="panel rise relative overflow-hidden p-5"
              style={{ animationDelay: `${index * 60}ms` }}
            >
              <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/[0.12] to-transparent" />
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-medium text-muted-foreground">{label}</p>
                  <p className={`num mt-4 text-4xl font-semibold tracking-tight ${tone === "green" ? "text-success" : ""}`}>
                    {value}
                  </p>
                </div>
                <span className={`grid h-9 w-9 place-items-center rounded-xl border ${tone === "green" ? "border-success/15 bg-success/[0.07] text-success" : "border-hairline bg-white/[0.025] text-muted-foreground"}`}>
                  <Icon className="h-4 w-4" />
                </span>
              </div>
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs text-foreground/75">{detail}</span>
                <span className="font-mono text-[10px] text-muted-foreground/80">{footnote}</span>
              </div>
            </article>
          ))}
        </section>

        <section aria-labelledby="executions-title">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="mb-1.5 flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-success shadow-[0_0_10px_var(--color-success)]" />
                <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Saved agent cases</p>
              </div>
              <h2 id="executions-title" className="font-display text-xl font-semibold tracking-tight sm:text-2xl">
                Recent Support Executions
              </h2>
            </div>
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
                <option value="needs-input">Needs input</option>
                <option value="done">Done</option>
                <option value="failed">Failed</option>
              </select>
              <ChevronDown className="pointer-events-none absolute right-3 h-3.5 w-3.5" />
            </label>
          </div>

          <div className="space-y-3">
            {loading && visibleTickets.length === 0 && (
              <p className="text-sm text-muted-foreground">Loading saved cases…</p>
            )}
            {!loading && visibleTickets.length === 0 && !error && (
              <p className="text-sm text-muted-foreground">
                No cases yet. Submit one from Customer Simulation.
              </p>
            )}
            {visibleTickets.map((ticket, index) => {
              const failed = ticket.execution_status === "failed";
              const waiting =
                ticket.execution_status === "waiting_input" ||
                ticket.execution_status === "queued" ||
                ticket.execution_status === "running";
              return (
                <Link
                  key={ticket.case_id}
                  href={`/ticket/${ticket.case_id}`}
                  className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-success/50"
                >
                  <article
                    className="panel relative overflow-hidden p-4 transition duration-200 ease-out group-hover:-translate-y-0.5 group-hover:border-success/25 group-hover:shadow-[0_14px_45px_-28px_rgba(91,255,159,0.22)] sm:p-5"
                    style={{ animationDelay: `${index * 70}ms` }}
                  >
                    <div className={`absolute inset-y-0 left-0 w-[2px] ${failed ? "bg-warning/70" : waiting ? "bg-primary/60" : "bg-success/50"}`} />
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                      <div className="flex min-w-0 flex-1 items-start gap-4">
                        <span className={`mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-xl border ${failed ? "border-warning/15 bg-warning/[0.06] text-warning" : waiting ? "border-primary/15 bg-primary/[0.06] text-primary" : "border-success/15 bg-success/[0.06] text-success"}`}>
                          {failed ? <ShieldAlert className="h-[18px] w-[18px]" /> : waiting ? <Clock3 className="h-[18px] w-[18px]" /> : <PackageCheck className="h-[18px] w-[18px]" />}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="mb-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1">
                            <span className="font-mono text-[11px] tracking-wide text-muted-foreground">{ticket.case_id}</span>
                            <span className="h-1 w-1 rounded-full bg-muted-foreground/40" />
                            <span className="text-[11px] text-muted-foreground">{ticket.current_run_id}</span>
                          </div>
                          <p className="text-sm font-medium leading-relaxed text-foreground/90 sm:text-[15px]">{ticket.message}</p>
                          <div className="mt-3 flex flex-wrap gap-1.5">
                            <span className="inline-flex items-center gap-1.5 rounded-md border border-hairline bg-white/[0.025] px-2 py-1 font-mono text-[9px] tracking-wide text-muted-foreground">
                              {ticket.execution_status}
                            </span>
                            {ticket.outcome && (
                              <span className="inline-flex items-center gap-1.5 rounded-md border border-hairline bg-white/[0.025] px-2 py-1 font-mono text-[9px] tracking-wide text-muted-foreground">
                                {ticket.outcome}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center justify-between gap-3 pl-14 sm:justify-end sm:pl-0">
                        <span className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1.5 text-[10px] font-medium ${failed ? "border-warning/20 bg-warning/[0.06] text-warning" : waiting ? "border-primary/20 bg-primary/[0.06] text-primary" : "border-success/20 bg-success/[0.06] text-success"}`}>
                          <span className={`h-1.5 w-1.5 rounded-full ${failed ? "bg-warning" : waiting ? "bg-primary pulse-dot" : "bg-success"}`} />
                          {statusLabel(ticket)}
                        </span>
                        <ArrowUpRight className="h-4 w-4 shrink-0 text-muted-foreground/40 transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-foreground/80" />
                      </div>
                    </div>
                  </article>
                </Link>
              );
            })}
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
                  className="text-xs text-muted-foreground transition hover:text-foreground"
                >
                  Load more
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
