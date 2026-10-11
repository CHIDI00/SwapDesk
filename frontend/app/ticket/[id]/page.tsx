"use client";

import { Suspense, useState, type FormEvent } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Clock3, ShieldAlert, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useCaseDetail } from "@/lib/use-case";
import { isTerminalExecution } from "@/lib/api";
import { Spinner } from "@/components/ui/spinner";
import { Skeleton } from "@/components/ui/skeleton";

function ExecutionBadge({ status, label }: { status: string; label: string }) {
  const escalated = label.toLowerCase().includes("escalat");
  const waiting =
    status === "waiting_input" || label.toLowerCase().includes("clarif");
  const active = status === "queued" || status === "running";
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1.5 text-[10px] font-medium ${escalated ? "border-warning/20 bg-warning/[0.06] text-warning" : active || waiting ? "border-primary/20 bg-primary/[0.06] text-primary" : "border-success/20 bg-success/[0.06] text-success"}`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${escalated ? "bg-warning" : active ? "bg-primary pulse-dot" : waiting ? "bg-primary" : "bg-success"}`}
      />
      {label}
    </span>
  );
}

function ContinueForm({ caseId }: { caseId: string }) {
  const { sendContinue, sending } = useCaseDetail(caseId);
  const [message, setMessage] = useState("");
  const [consentSize, setConsentSize] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (sending) return;
    const trimmedMessage = message.trim();
    const trimmedConsent = consentSize.trim();
    if (!trimmedMessage && !trimmedConsent) {
      setFormError("Write a message or a consented size first.");
      return;
    }
    setFormError(null);
    try {
      await sendContinue({
        message: trimmedMessage || null,
        consent_size: trimmedConsent || null,
      });
      setMessage("");
      setConsentSize("");
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Continuation failed");
    }
  };

  return (
    <form onSubmit={handleSubmit} className="panel space-y-4 p-4 sm:p-5">
      <h2 className="text-lg font-semibold">Reply to the agent</h2>
      <div className="space-y-2">
        <label htmlFor="continue-message" className="block text-sm font-medium">
          Message
        </label>
        <textarea
          id="continue-message"
          rows={3}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="Answer the agent's question…"
          disabled={sending}
          className="w-full resize-none rounded-xl border border-hairline bg-background/60 p-3 text-sm outline-none placeholder:text-muted-foreground/70 focus:border-success/40 disabled:opacity-60"
        />
      </div>
      <div className="space-y-2">
        <label htmlFor="continue-consent" className="block text-sm font-medium">
          Consented size <span className="font-normal text-muted-foreground">(optional)</span>
        </label>
        <input
          id="continue-consent"
          value={consentSize}
          onChange={(event) => setConsentSize(event.target.value)}
          placeholder="e.g. 42"
          disabled={sending}
          className="w-full rounded-xl border border-hairline bg-background/60 p-3 text-sm outline-none placeholder:text-muted-foreground/70 focus:border-success/40 disabled:opacity-60"
        />
      </div>
      {formError && <p className="text-sm text-warning">{formError}</p>}
      <button
        type="submit"
        disabled={sending}
        className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-70"
      >
        {sending ? (
          <>
            <Spinner className="h-4 w-4" />
            Sending…
          </>
        ) : (
          "Send reply"
        )}
      </button>
    </form>
  );
}

function TicketDetailContent() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const { detail, timeline, loading, missing, error } = useCaseDetail(id);

  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Mission Control", to: "/" }, { label: id ?? "Unknown" }]}>
      <div className="mx-auto w-full max-w-6xl space-y-6">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">
              {detail ? detail.message : loading ? "Loading ticket…" : "Ticket not found"}
            </h1>
            <p className="mt-1 font-mono text-sm text-muted-foreground">
              {id}
              {detail ? ` · ${detail.execution_status}${detail.outcome ? ` · ${detail.outcome}` : ""}` : ""}
            </p>
          </div>
          <Link
            href="/"
            className="inline-flex items-center gap-2 rounded-lg border border-hairline bg-card/60 px-3 py-2 text-sm text-foreground transition-colors hover:bg-accent/60"
          >
            <ArrowLeft className="h-4 w-4" /> Back to Mission Control
          </Link>
        </header>

        {loading && !detail && (
          <div className="space-y-6" aria-hidden="true">
            <div className="grid gap-3 sm:grid-cols-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="panel flex items-center gap-3 p-4">
                  <Skeleton className="h-9 w-9 rounded-xl" />
                  <div className="min-w-0 flex-1 space-y-2">
                    <Skeleton className="h-3 w-16" />
                    <Skeleton className="h-4 w-28" />
                  </div>
                </div>
              ))}
            </div>
            <div className="panel space-y-3 p-5">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3.5 w-full" />
              <Skeleton className="h-3.5 w-4/5" />
            </div>
          </div>
        )}

        {error && (
          <div className="panel border-warning/20 p-6">
            <p className="text-sm text-warning">{error}</p>
          </div>
        )}

        {missing && (
          <div className="panel p-6">
            <p className="text-sm text-muted-foreground">
              No saved case with this id. Check the id or submit a new ticket.
            </p>
          </div>
        )}

        {detail && (
          <>
            <section className="grid gap-3 sm:grid-cols-3">
              <div className="panel flex items-center gap-3 p-4">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-hairline bg-[var(--surface)] text-muted-foreground">
                  {detail.execution_status === "failed" ? (
                    <ShieldAlert className="h-4 w-4" />
                  ) : isTerminalExecution(detail.execution_status) ? (
                    <ShieldCheck className="h-4 w-4" />
                  ) : (
                    <Clock3 className="h-4 w-4" />
                  )}
                </span>
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">Status</p>
                  <div className="mt-1">
                    <ExecutionBadge
                      status={detail.execution_status}
                      label={detail.outcome ?? detail.execution_status}
                    />
                  </div>
                </div>
              </div>
              <div className="panel flex items-center gap-3 p-4">
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">Exchange</p>
                  <p className="truncate font-mono text-sm">{detail.exchange_id ?? "—"}</p>
                </div>
              </div>
              <div className="panel flex items-center gap-3 p-4">
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">Run</p>
                  <p className="truncate font-mono text-sm">
                    {detail.current_run_id}
                    {detail.requests_spent !== null && detail.requests_spent !== undefined
                      ? ` · ${detail.requests_spent} requests`
                      : ""}
                  </p>
                </div>
              </div>
            </section>

            {detail.reply && (
              <section className="panel space-y-2 p-4 sm:p-5">
                <h2 className="text-lg font-semibold">Saved reply</h2>
                <p className="text-sm leading-relaxed text-foreground/90">{detail.reply}</p>
              </section>
            )}

            {detail.outcome === "clarification" && detail.clarification && (
              <section className="panel space-y-2 border-primary/20 p-4 sm:p-5">
                <h2 className="text-lg font-semibold">Agent question</h2>
                <p className="text-sm leading-relaxed text-foreground/90">{detail.clarification}</p>
              </section>
            )}

            {detail.error && (
              <section className="panel space-y-2 border-warning/20 p-4 sm:p-5">
                <h2 className="text-lg font-semibold">Run failed</h2>
                <p className="text-sm leading-relaxed text-foreground/90">{detail.error}</p>
              </section>
            )}

            {(detail.execution_status === "waiting_input" ||
              detail.execution_status === "failed") && (
              <ContinueForm caseId={detail.case_id} />
            )}

            <section>
              <h2 className="mb-3 text-lg font-semibold">Execution Timeline</h2>
              {timeline.length === 0 ? (
                <div className="panel p-6">
                  <p className="text-sm text-muted-foreground">
                    No business actions journaled yet. A completed escalation with no
                    exchange ends here legitimately — nothing was committed, so
                    there is nothing to list.
                  </p>
                </div>
              ) : (
                <div className="panel overflow-x-auto p-4 font-mono text-xs leading-7 sm:p-6 sm:text-[13px]">
                  {timeline.map((step) => (
                    <div key={step.op_key} className="flex gap-4 whitespace-nowrap">
                      <span className="text-muted-foreground/60">{step.created_at}</span>
                      <span className="w-44 shrink-0 text-success">{step.op_type}</span>
                      <span className="text-foreground/80">
                        {step.event} · {step.status} · {step.run_id}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </>
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
