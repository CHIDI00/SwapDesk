"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, Loader2, Send } from "lucide-react";
import { useSwapDesk } from "@/store/swapdesk";

const DEFAULT_COMPLAINT = "My Jordan 4s arrived but are too tight. I need to exchange for a size 43.";

export function CustomerSimulationWidget() {
  const { submitCustomerTicket } = useSwapDesk();
  const [complaint, setComplaint] = useState("");
  const [status, setStatus] = useState<"idle" | "routing" | "done">("idle");
  const [routedId, setRoutedId] = useState<string | null>(null);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (status === "routing") return;

    setStatus("routing");
    window.setTimeout(() => {
      const ticket = submitCustomerTicket(complaint);
      setRoutedId(ticket.id);
      setStatus("done");
    }, 900);
  };

  return (
    <form onSubmit={handleSubmit} className="panel space-y-5 p-5 sm:p-6">
      <div className="space-y-2">
        <label htmlFor="complaint" className="block text-sm font-semibold">
          Customer complaint
        </label>
        <textarea
          id="complaint"
          name="complaint"
          rows={5}
          value={complaint}
          onChange={(event) => setComplaint(event.target.value)}
          placeholder={DEFAULT_COMPLAINT}
          disabled={status === "routing"}
          className="w-full resize-none rounded-xl border border-hairline bg-background/60 p-4 text-sm leading-relaxed text-foreground outline-none transition-colors placeholder:text-muted-foreground/70 focus:border-success/40 disabled:opacity-60"
        />
      </div>

      <button
        type="submit"
        disabled={status === "routing"}
        className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-70 sm:w-auto"
      >
        {status === "routing" ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Routing to Autonomous Agent...
          </>
        ) : (
          <>
            <Send className="h-4 w-4" />
            Submit to SwapDesk
          </>
        )}
      </button>

      {status === "done" && routedId && (
        <div className="rise flex flex-col gap-3 rounded-xl border border-success/20 bg-success/[0.06] p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
            <div>
              <p className="text-sm font-semibold text-foreground">Ticket {routedId} routed to the autonomous agent</p>
              <p className="text-xs text-muted-foreground">It should now appear in the Mission Control queue.</p>
            </div>
          </div>
          <Link
            href="/"
            className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-hairline bg-card/60 px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent/60"
          >
            View Mission Control
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      )}
    </form>
  );
}
