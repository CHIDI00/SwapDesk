"use client";

import { useState } from "react";
import { ArrowUpRight, Check, CircleHelp, LockKeyhole, Webhook } from "lucide-react";
import { AppShell, PageTitle } from "@/components/AppShell";

const integrations = [
  {
    id: "zendesk",
    name: "Zendesk",
    kind: "Customer service",
    description: "Route new tickets and replies from your Zendesk workspace.",
    initials: "Z",
    brand: "text-orange-300 bg-orange-400/10 ring-orange-300/15",
    url: "https://api.swapdesk.io/webhook/zd-1a2b",
    lastPing: "2 mins ago",
  },
  {
    id: "shopify",
    name: "Shopify Inbox",
    kind: "Commerce messaging",
    description: "Bring storefront conversations into your AI support workflow.",
    initials: "S",
    brand: "text-lime-300 bg-lime-400/10 ring-lime-300/15",
    url: "https://api.swapdesk.io/webhook/sh-inbox-7c9d",
    lastPing: "2 mins ago",
  },
  {
    id: "gorgias",
    name: "Gorgias",
    kind: "Helpdesk",
    description: "Connect ecommerce support tickets to SwapDesk in real time.",
    initials: "G",
    brand: "text-violet-300 bg-violet-400/10 ring-violet-300/15",
    url: "https://api.swapdesk.io/webhook/go-4f8e",
    lastPing: "2 mins ago",
  },
] as const;

type IntegrationId = (typeof integrations)[number]["id"];

export function IntegrationsPage() {
  const [enabled, setEnabled] = useState<Record<IntegrationId, boolean>>({
    zendesk: true,
    shopify: false,
    gorgias: false,
  });
  const activeCount = Object.values(enabled).filter(Boolean).length;

  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Integrations" }]}>
      <div className="mb-8 flex flex-col gap-5 border-b border-hairline pb-7 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-primary/15 bg-primary/[0.06] px-3 py-1.5 text-[11px] font-medium tracking-wide text-primary">
            <Webhook className="h-3.5 w-3.5" />
            INBOUND TRIGGERS
          </div>
          <PageTitle
            title="Inbound Triggers (Webhooks)"
            sub="Connect your existing helpdesk to route tickets to the SwapDesk AI."
          />
        </div>
        <div className="inline-flex w-fit shrink-0 items-center gap-2 rounded-xl border border-hairline bg-card/60 px-3.5 py-2.5 text-xs text-muted-foreground">
          <span className="h-2 w-2 rounded-full bg-success shadow-[0_0_12px_rgba(91,255,159,0.65)]" />
          <span className="font-mono text-foreground">{activeCount} of 3</span>
          integrations active
        </div>
      </div>

      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-base font-semibold tracking-tight">Helpdesk connections</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Choose which platforms can send ticket events to SwapDesk.
          </p>
        </div>
        <div className="inline-flex items-center gap-2 text-[11px] text-muted-foreground">
          <CircleHelp className="h-3.5 w-3.5" />
          Configuration preview · Changes stay in this session
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        {integrations.map((integration, index) => {
          const isEnabled = enabled[integration.id];

          return (
            <article
              key={integration.id}
              className={`panel rise flex min-w-0 flex-col overflow-hidden transition-all duration-300 ${
                isEnabled ? "border-primary/20" : "hover:border-foreground/15"
              }`}
              style={{ animationDelay: `${index * 70}ms` }}
            >
              <div className="flex items-start justify-between gap-4 p-5 pb-4">
                <div className="flex min-w-0 items-center gap-3.5">
                  <div
                    className={`grid h-12 w-12 shrink-0 place-items-center rounded-2xl ring-1 ${integration.brand}`}
                    aria-hidden="true"
                  >
                    <span className="font-display text-lg font-bold">{integration.initials}</span>
                  </div>
                  <div className="min-w-0">
                    <h3 className="truncate text-sm font-semibold">{integration.name}</h3>
                    <p className="mt-1 truncate text-[11px] text-muted-foreground">{integration.kind}</p>
                  </div>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-2">
                  <button
                    type="button"
                    role="switch"
                    aria-checked={isEnabled}
                    aria-label={`${integration.name} webhook`}
                    onClick={() =>
                      setEnabled((current) => ({
                        ...current,
                        [integration.id]: !current[integration.id],
                      }))
                    }
                    className={`relative h-6 w-11 rounded-full border border-hairline transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background ${
                      isEnabled ? "bg-primary" : "bg-muted"
                    }`}
                  >
                    <span
                      className={`absolute top-0.5 h-[18px] w-[18px] rounded-full bg-foreground shadow-sm transition-all ${
                        isEnabled ? "left-[22px]" : "left-0.5"
                      }`}
                    />
                  </button>
                  <span
                    className={`text-[10px] font-semibold uppercase tracking-[0.14em] ${
                      isEnabled ? "text-primary" : "text-muted-foreground"
                    }`}
                  >
                    {isEnabled ? "On" : "Off"}
                  </span>
                </div>
              </div>

              <p className="min-h-10 px-5 text-xs leading-5 text-muted-foreground">
                {integration.description}
              </p>

              <div className="mt-5 border-t border-hairline px-5 py-4">
                {isEnabled ? (
                  <>
                    <label
                      htmlFor={`${integration.id}-webhook-url`}
                      className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground"
                    >
                      Webhook URL
                    </label>
                    <div className="flex min-w-0 items-center gap-2 rounded-lg border border-hairline bg-background/70 px-3 py-2.5">
                      <Webhook className="h-3.5 w-3.5 shrink-0 text-primary/80" />
                      <input
                        id={`${integration.id}-webhook-url`}
                        aria-label={`${integration.name} webhook URL`}
                        className="min-w-0 flex-1 truncate bg-transparent font-mono text-[10px] text-foreground/80 outline-none"
                        readOnly
                        value={integration.url}
                      />
                      <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60" />
                    </div>
                    <div className="mt-4 flex items-center justify-between gap-3">
                      <span className="inline-flex items-center gap-2 text-[11px] font-medium text-success">
                        <span className="relative flex h-2 w-2">
                          <span className="pulse-dot absolute inline-flex h-full w-full rounded-full bg-success opacity-60" />
                          <span className="relative inline-flex h-2 w-2 rounded-full bg-success" />
                        </span>
                        Connected
                      </span>
                      <span className="font-mono text-[10px] text-muted-foreground">
                        Last ping: {integration.lastPing}
                      </span>
                    </div>
                  </>
                ) : (
                  <div className="flex min-h-[105px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-hairline bg-foreground/[0.015] px-4 text-center">
                    <span className="grid h-7 w-7 place-items-center rounded-full bg-foreground/[0.04] text-muted-foreground">
                      <LockKeyhole className="h-3.5 w-3.5" />
                    </span>
                    <p className="text-[11px] text-muted-foreground">
                      Turn on to reveal your webhook endpoint
                    </p>
                  </div>
                )}
              </div>
              <div className="mt-auto border-t border-hairline bg-foreground/[0.015] px-5 py-3">
                <span className="inline-flex items-center gap-1.5 text-[10px] text-muted-foreground">
                  <Check className={`h-3 w-3 ${isEnabled ? "text-success" : "text-muted-foreground/50"}`} />
                  {isEnabled ? "Ready to receive events" : "Waiting for activation"}
                </span>
              </div>
            </article>
          );
        })}
      </div>

      <div className="panel mt-6 flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <div className="flex items-start gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-primary/[0.08] text-primary">
            <LockKeyhole className="h-4 w-4" />
          </span>
          <div>
            <p className="text-xs font-semibold">Your support stack, connected</p>
            <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
              Webhook endpoints are shown for demonstration. This preview does not deliver or process events.
            </p>
          </div>
        </div>
        <span className="shrink-0 rounded-lg border border-hairline bg-background/50 px-3 py-2 font-mono text-[10px] text-muted-foreground">
          SWAPDESK · MIDDLEWARE
        </span>
      </div>
    </AppShell>
  );
}
