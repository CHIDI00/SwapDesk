"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Clock3, ShieldAlert, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useSwapDesk } from "@/store/swapdesk";

const steps = [
  {
    t: "14:02:11.204",
    kind: "ok" as const,
    label: "Reserve Inventory",
    detail: "reserve_replacement → RSV-55128 (84ms)",
  },
  {
    t: "14:02:19.391",
    kind: "warn" as const,
    label: "Create Label Timeout",
    detail: "create_label ETIMEDOUT after 8000ms — retry suppressed",
  },
  {
    t: "14:02:19.433",
    kind: "ok" as const,
    label: "Recovery",
    detail: "found LBL-77310 status=CREATED → reuse, no duplicate",
  },
  {
    t: "14:02:19.611",
    kind: "ok" as const,
    label: "State Verification",
    detail: "3/3 assertions passed · db_state == planned_reply",
  },
];

function TicketDetailContent() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const { getTicket } = useSwapDesk();
  const ticket = id ? getTicket(id) : undefined;

  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Mission Control", to: "/" }, { label: id ?? "Unknown" }]}>
      <div className="mx-auto w-full max-w-6xl space-y-6">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">
              {ticket ? ticket.message : "Ticket not found"}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {id} {ticket ? `· ${ticket.statusLabel}` : "· no matching ticket in the queue"}
            </p>
          </div>
          <Link
            href="/"
            className="inline-flex items-center gap-2 rounded-lg border border-hairline bg-card/60 px-3 py-2 text-sm text-foreground transition-colors hover:bg-accent/60"
          >
            <ArrowLeft className="h-4 w-4" /> Back to Mission Control
          </Link>
        </header>

        {ticket ? (
          <>
            <section className="grid gap-3 sm:grid-cols-3">
              <div className="panel flex items-center gap-3 p-4">
                <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl border ${ticket.status === "escalated" ? "border-warning/15 bg-warning/[0.07] text-warning" : ticket.status === "processing" ? "border-primary/15 bg-primary/[0.07] text-primary" : "border-success/15 bg-success/[0.07] text-success"}`}>
                  {ticket.status === "escalated" ? <ShieldAlert className="h-4 w-4" /> : ticket.status === "processing" ? <Clock3 className="h-4 w-4" /> : <ShieldCheck className="h-4 w-4" />}
                </span>
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">Status</p>
                  <p className="truncate text-sm font-semibold">{ticket.statusLabel}</p>
                </div>
              </div>
              <div className="panel flex items-center gap-3 p-4">
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">SKU</p>
                  <p className="truncate font-mono text-sm">{ticket.sku}</p>
                </div>
              </div>
              <div className="panel flex items-center gap-3 p-4">
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">Actions</p>
                  <p className="truncate font-mono text-sm">{ticket.actions.join(" · ")}</p>
                </div>
              </div>
            </section>

            <section>
              <h2 className="mb-3 text-lg font-semibold">Execution Timeline</h2>
              <div className="panel overflow-x-auto p-4 font-mono text-xs leading-7 sm:p-6 sm:text-[13px]">
                {steps.map((step) => (
                  <div key={step.label} className="flex gap-4 whitespace-nowrap">
                    <span className="text-muted-foreground/60">{step.t}</span>
                    <span className={`w-44 shrink-0 ${step.kind === "warn" ? "text-warning" : "text-success"}`}>
                      {step.label}
                    </span>
                    <span className="text-foreground/80">{step.detail}</span>
                  </div>
                ))}
              </div>
            </section>
          </>
        ) : (
          <div className="panel p-6">
            <p className="text-sm text-muted-foreground">
              This ticket is not in the queue. It may have been cleared with “Reset Sample Data”. Submit a new ticket to see the
              execution view.
            </p>
          </div>
        )}
      </div>
    </AppShell>
  );
}

function TicketDetailFallback() {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
      <div className="panel flex items-center gap-3 p-6">
        <span className="h-2 w-2 rounded-full bg-success pulse-dot" />
        <p className="text-sm text-muted-foreground">Loading ticket…</p>
      </div>
    </div>
  );
}

export default function TicketDetailPage() {
  return (
    <Suspense fallback={<TicketDetailFallback />}>
      <TicketDetailContent />
    </Suspense>
  );
}
