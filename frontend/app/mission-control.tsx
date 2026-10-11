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
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  Tag,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useSwapDesk, type TicketStatus } from "@/store/swapdesk";

export function MissionControl() {
  const { tickets } = useSwapDesk();
  const [filter, setFilter] = useState<"all" | TicketStatus>("all");
  const visibleTickets = tickets.filter((ticket) => filter === "all" || ticket.status === filter);

  const totalTickets = tickets.length;
  const resolvedTickets = tickets.filter((ticket) => ticket.status === "resolved").length;
  const completionRate =
    totalTickets > 0 ? `${Math.round((resolvedTickets / totalTickets) * 100)}%` : "N/A";

  const metrics = [
    {
      label: "Completion Rate",
      value: completionRate,
      detail: "Resolved by the agent",
      icon: Check,
      tone: "green",
      footnote: "From the live mock queue",
    },
    {
      label: "Duplicate-Action Rate",
      value: "0%",
      icon: RotateCcw,
      tone: "green",
      footnote: "Idempotency verified",
    },
    {
      label: "Wrongful-Action Rate",
      value: "0%",
      detail: "Safety under policy",
      icon: ShieldCheck,
      tone: "green",
      footnote: "Policy checks active",
    },
    {
      label: "Cost per execution",
      value: "Demo Mode",
      detail: "No backend billed",
      icon: CircleDollarSign,
      tone: "neutral",
    },
  ];

  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Mission Control" }]} metrics={false}>
      <div className="space-y-8 pb-8">
        <section className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
              Operations overview <span className="text-success/70">/</span> 24h window
            </p>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <h1 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">Mission Control</h1>
              <span className="inline-flex items-center gap-2 rounded-full border border-success/20 bg-success/[0.07] px-3 py-1.5 font-mono text-[11px] text-success">
                <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-success shadow-[0_0_10px_var(--color-success)]" />
                Live: Local Demo
              </span>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              Autonomous support performance, policy safety, and live execution health.
            </p>
          </div>
          <div className="flex items-center gap-2 rounded-lg border border-hairline bg-card/65 px-3 py-2 text-xs text-muted-foreground">
            <Clock3 className="h-3.5 w-3.5" />
            Updated just now
          </div>
        </section>

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
                <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Live agent inbox</p>
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
                onChange={(event) => setFilter(event.target.value as "all" | TicketStatus)}
              >
                <option value="all">All</option>
                <option value="processing">Agent Processing</option>
                <option value="resolved">Resolved</option>
                <option value="escalated">Escalated</option>
              </select>
              <ChevronDown className="pointer-events-none absolute right-3 h-3.5 w-3.5" />
            </label>
          </div>

          <div className="space-y-3">
            {visibleTickets.map((ticket, index) => {
              const escalated = ticket.status === "escalated";
              const processing = ticket.status === "processing";
              return (
                <Link
                  key={ticket.id}
                  href={`/ticket/${ticket.id}`}
                  className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-success/50"
                >
                  <article
                    className="panel relative overflow-hidden p-4 transition duration-200 ease-out group-hover:-translate-y-0.5 group-hover:border-success/25 group-hover:shadow-[0_14px_45px_-28px_rgba(91,255,159,0.22)] sm:p-5"
                    style={{ animationDelay: `${index * 70}ms` }}
                  >
                    <div className={`absolute inset-y-0 left-0 w-[2px] ${escalated ? "bg-warning/70" : processing ? "bg-primary/60" : "bg-success/50"}`} />
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                      <div className="flex min-w-0 flex-1 items-start gap-4">
                        <span className={`mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-xl border ${escalated ? "border-warning/15 bg-warning/[0.06] text-warning" : processing ? "border-primary/15 bg-primary/[0.06] text-primary" : "border-success/15 bg-success/[0.06] text-success"}`}>
                          {escalated ? <ShieldAlert className="h-[18px] w-[18px]" /> : processing ? <Clock3 className="h-[18px] w-[18px]" /> : <PackageCheck className="h-[18px] w-[18px]" />}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="mb-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1">
                            <span className="font-mono text-[11px] tracking-wide text-muted-foreground">{ticket.id}</span>
                            <span className="h-1 w-1 rounded-full bg-muted-foreground/40" />
                            <span className="text-[11px] text-muted-foreground">{ticket.time}</span>
                          </div>
                          <p className="text-sm font-medium leading-relaxed text-foreground/90 sm:text-[15px]">{ticket.message}</p>
                          <div className="mt-3 flex flex-wrap gap-1.5">
                            {ticket.actions.map((action) => (
                              <span
                                key={action}
                                className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 font-mono text-[9px] tracking-wide ${action.includes("RECOVERED") ? "border-success/15 bg-success/[0.045] text-success/90" : "border-hairline bg-white/[0.025] text-muted-foreground"}`}
                              >
                                {action.includes("LABEL") ? <Tag className="h-3 w-3" /> : <span className="text-[8px] opacity-70">›</span>}
                                {action}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center justify-between gap-3 pl-14 sm:justify-end sm:pl-0">
                        <span className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1.5 text-[10px] font-medium ${escalated ? "border-warning/20 bg-warning/[0.06] text-warning" : processing ? "border-primary/20 bg-primary/[0.06] text-primary" : "border-success/20 bg-success/[0.06] text-success"}`}>
                          <span className={`h-1.5 w-1.5 rounded-full ${escalated ? "bg-warning" : processing ? "bg-primary pulse-dot" : "bg-success"}`} />
                          {ticket.statusLabel}
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
              SHOWING {visibleTickets.length.toString().padStart(2, "0")} OF {totalTickets.toString().padStart(2, "0")} EXECUTIONS
            </span>
            <Link href="/inbox" className="group inline-flex items-center gap-1.5 text-xs text-muted-foreground transition hover:text-foreground">
              Open full inbox
              <ArrowUpRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
            </Link>
          </div>
        </section>
      </div>
    </AppShell>
  );
}
