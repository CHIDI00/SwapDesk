"use client";

import { Fragment, Suspense, useMemo, useState, type FormEvent, type ReactNode } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useCaseDetail } from "@/lib/use-case";
import { useSwapDesk } from "@/store/swapdesk";
import { Skeleton } from "@/components/ui/skeleton";
import type { CaseDetail, TimelineEvent } from "@/lib/api";

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

const SENT_KEY = (caseId: string) => `swapdesk:sent:${caseId}`;

type SentMessage = { text: string; consent: string | null; sentAt: number };

function readSentMessages(caseId: string): SentMessage[] {
  try {
    const raw = window.localStorage.getItem(SENT_KEY(caseId));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (m): m is SentMessage =>
        typeof m === "object" && m !== null && typeof (m as SentMessage).text === "string",
    );
  } catch {
    return [];
  }
}

function appendSentMessage(caseId: string, entry: SentMessage) {
  try {
    const current = readSentMessages(caseId);
    window.localStorage.setItem(SENT_KEY(caseId), JSON.stringify([...current, entry]));
  } catch {
    /* private mode or quota: thread still works, history just won't persist */
  }
}

function ContinueForm({ caseId, mode, onSent }: { caseId: string; mode: "answer" | "retry"; onSent: () => void }) {
  const { sendContinue, sending } = useCaseDetail(caseId);
  const { submit } = useSwapDesk();
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const heading = mode === "answer" ? "Answer as the customer" : "Retry the run";
  const sub =
    mode === "answer"
      ? "The agent is waiting on the customer. Anything sent here goes to the agent as the customer's words (demo)."
      : "Queues a fresh run with the same request. Nothing is retried automatically.";

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (sending) return;
    const trimmedMessage = message.trim();
    if (!trimmedMessage) {
      setFormError("Write a message first.");
      return;
    }
    setFormError(null);
    try {
      await sendContinue({
        message: trimmedMessage,
        consent_size: null,
      });
      appendSentMessage(caseId, {
        text: trimmedMessage,
        consent: null,
        sentAt: Date.now(),
      });
      onSent();
      setMessage("");
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Continuation failed");
    }
  };

  const handleNewTicket = async () => {
    const trimmedMessage = message.trim();
    if (!trimmedMessage || starting) return;
    setFormError(null);
    setStarting(true);
    try {
      const accepted = await submit({ message: trimmedMessage });
      router.push(`/ticket/${accepted.case_id}`);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "New ticket failed");
      setStarting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="panel space-y-4 p-4 sm:p-5">
      <h2 className="text-lg font-semibold">{heading}</h2>
      <p className="text-sm text-muted-foreground">{sub}</p>
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
      {formError && <p className="text-sm text-warning">{formError}</p>}
      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          disabled={sending}
          className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-70"
        >
          {sending ? "Sending…" : "Send reply"}
        </button>
        <button
          type="button"
          disabled={sending || starting || message.trim().length === 0}
          onClick={() => void handleNewTicket()}
          title="Open this text as a brand-new ticket instead of replying here"
          className="inline-flex items-center gap-2 rounded-xl border border-hairline bg-card/60 px-4 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-accent/60 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {starting ? "Opening…" : "New ticket from this text"}
        </button>
      </div>
    </form>
  );
}

function CustomerBubble({ message, caseId }: { message: string | null | undefined; caseId: string }) {
  const text = (message ?? "").trim();
  if (!text) {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] text-right font-mono text-[11px] text-muted-foreground sm:max-w-[75%]">
          No customer message was saved for {caseId}.
        </p>
      </div>
    );
  }
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-3 text-sm leading-relaxed text-primary-foreground sm:max-w-[75%]">
        <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.18em] opacity-70">
          Customer · {caseId}
        </p>
        <p>{text}</p>
      </div>
    </div>
  );
}

function AgentBubble({
  title,
  children,
  tone = "default",
}: {
  title: string;
  children: ReactNode;
  tone?: "default" | "warning" | "success";
}) {
  const border =
    tone === "warning"
      ? "border-warning/20"
      : tone === "success"
        ? "border-success/20"
        : "border-hairline";
  return (
    <div className="flex justify-start">
      <div className={`max-w-[85%] rounded-2xl rounded-bl-md border bg-card/60 px-4 py-3 sm:max-w-[75%] ${border}`}>
        <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
          SwapDesk agent · {title}
        </p>
        <div className="text-sm leading-relaxed text-foreground/90">{children}</div>
      </div>
    </div>
  );
}

function describeStep(step: TimelineEvent): string {
  const result = step.result as Record<string, unknown> | undefined;
  const exchangeId =
    typeof result?.exchange_id === "string" ? result.exchange_id : null;
  switch (step.op_type) {
    case "reserve_replacement":
      return exchangeId
        ? `Reserved a replacement (${exchangeId}).`
        : "Reserved a replacement.";
    case "create_return":
      return "Created the return.";
    case "create_label":
      return "Created the shipping label.";
    case "finalize_arranged":
      return "Verified everything and arranged the exchange.";
    case "release_reservation":
      return "Released the held stock.";
    case "cancel_exchange":
      return "Cancelled the exchange.";
    case "escalate_case":
    case "record_escalation":
      return "Handed this to a human.";
    case "record_denial":
      return "Recorded a policy denial.";
    case "record_clarification":
      return "Asked for more information.";
    default:
      return `${step.op_type} · ${step.event} · ${step.status}`;
  }
}

function EndState({ detail }: { detail: CaseDetail }) {
  const titles = {
    arranged: "exchange arranged",
    denial: "request denied",
    clarification: "question for you",
    escalation: "handed to a human",
  } as const;
  const title =
    detail.outcome !== null && detail.outcome in titles
      ? titles[detail.outcome as keyof typeof titles]
      : "working";
  const tone = detail.outcome === "denial" || detail.outcome === "escalation" ? "warning" : "default";
  const text =
    detail.outcome === "clarification"
      ? (detail.clarification ?? detail.reply)
      : detail.reply;
  const escalationNote =
    detail.outcome === "escalation" && text
      ? "Connecting you to a human agent who can see this conversation."
      : null;
  return (
    <AgentBubble title={title} tone={tone as "default" | "warning"}>
      {escalationNote && <p>{escalationNote}</p>}
      {text ? (
        <p className={escalationNote ? "mt-2 border-l-2 border-warning/30 pl-3 text-muted-foreground" : ""}>{text}</p>
      ) : (
        !escalationNote && (
          <p>
            {detail.execution_status === "failed"
              ? (detail.error ?? "The run failed.")
              : "The agent is still working on this. New steps appear here as they happen."}
          </p>
        )
      )}
    </AgentBubble>
  );
}

function TicketDetailContent() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const { detail, timeline, loading, missing, error } = useCaseDetail(id);
  const [sentVersion, setSentVersion] = useState(0);
  const sent = useMemo(
    () => (detail ? readSentMessages(detail.case_id) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [detail?.case_id, sentVersion],
  );

  type ThreadItem =
    | { kind: "step"; at: number; key: string; node: ReactNode }
    | { kind: "sent"; at: number; key: string; node: ReactNode };

  const thread: ThreadItem[] = [
    ...timeline.map((step) => ({
      kind: "step" as const,
      at: Date.parse(step.created_at) || 0,
      key: step.op_key,
      node: (
        <AgentBubble title={step.op_type}>
          <p>{describeStep(step)}</p>
          <p className="mt-1 font-mono text-[11px] text-muted-foreground">
            {step.event} · {step.status} · {step.run_id}
          </p>
        </AgentBubble>
      ),
    })),
    ...sent.map((msg, i) => ({
      kind: "sent" as const,
      at: msg.sentAt,
      key: `sent-${msg.sentAt}-${i}`,
      node: (
        <CustomerBubble
          message={`${msg.text}${msg.consent ? ` (consents to size ${msg.consent})` : ""}`}
          caseId={detail?.case_id ?? ""}
        />
      ),
    })),
  ].sort((a, b) => a.at - b.at);

  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Mission Control", to: "/" }, { label: id ?? "Unknown" }]}>
      <div className="mx-auto w-full max-w-3xl space-y-4 pb-8">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h1 className="font-mono text-lg font-semibold">{id}</h1>
            {detail && (
              <ExecutionBadge
                status={detail.execution_status}
                label={detail.outcome ?? detail.execution_status}
              />
            )}
          </div>
          <Link
            href="/"
            className="inline-flex items-center gap-2 rounded-lg border border-hairline bg-card/60 px-3 py-2 text-sm text-foreground transition-colors hover:bg-accent/60"
          >
            <ArrowLeft className="h-4 w-4" /> Back to Mission Control
          </Link>
        </header>

        {loading && !detail && (
          <div className="space-y-4" aria-hidden="true">
            {[0, 1, 2].map((i) => (
              <div key={i} className={`flex ${i % 2 === 0 ? "justify-end" : "justify-start"}`}>
                <Skeleton className={`h-16 rounded-2xl ${i % 2 === 0 ? "w-2/3" : "w-3/4"}`} />
              </div>
            ))}
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
            <CustomerBubble message={detail.message} caseId={detail.case_id} />

            {thread.map((item) => (
              <Fragment key={item.key}>{item.node}</Fragment>
            ))}

            <EndState detail={detail} />

            {(detail.execution_status === "waiting_input" ||
              detail.execution_status === "failed") && (
              <ContinueForm
                caseId={detail.case_id}
                mode={detail.execution_status === "failed" ? "retry" : "answer"}
                onSent={() => setSentVersion((v) => v + 1)}
              />
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}

function TicketDetailFallback() {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 lg:px-8">
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
