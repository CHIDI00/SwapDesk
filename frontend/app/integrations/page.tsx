"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Check, Copy, LifeBuoy, MessagesSquare, ShoppingBag } from "lucide-react";
import { AppShell, PageTitle } from "@/components/AppShell";

const integrations = [
  {
    key: "zendesk",
    name: "Zendesk",
    desc: "Route new support tickets straight into the SwapDesk agent pipeline.",
    webhook: "https://api.swapdesk.io/webhook/zd-1a2b",
    lastPing: "2 mins ago",
    icon: LifeBuoy,
    tile: "border-success/15 bg-success/[0.06] text-success",
  },
  {
    key: "shopify",
    name: "Shopify Inbox",
    desc: "Turn storefront chats and exchange requests into routable tickets.",
    webhook: "https://api.swapdesk.io/webhook/sh-4f9c",
    lastPing: "—",
    icon: ShoppingBag,
    tile: "border-primary/15 bg-primary/[0.06] text-primary",
  },
  {
    key: "gorgias",
    name: "Gorgias",
    desc: "Forward ecommerce conversations to SwapDesk for autonomous handling.",
    webhook: "https://api.swapdesk.io/webhook/gg-7d3e",
    lastPing: "—",
    icon: MessagesSquare,
    tile: "border-warning/15 bg-warning/[0.06] text-warning",
  },
] as const;

export default function IntegrationsPage() {
  const [on, setOn] = useState<Record<string, boolean>>({ zendesk: true, shopify: false, gorgias: false });
  const [copied, setCopied] = useState<string | null>(null);

  const copy = (key: string, webhook: string) => {
    navigator.clipboard?.writeText(webhook).catch(() => {});
    setCopied(key);
    toast("Webhook URL copied to clipboard");
    window.setTimeout(() => setCopied((current) => (current === key ? null : current)), 1500);
  };

  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Integrations" }]} metrics={false}>
      <PageTitle
        title="Inbound Triggers (Webhooks)"
        sub="Connect your existing helpdesk to route tickets to the SwapDesk AI."
      />

      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {integrations.map((integration) => {
          const enabled = on[integration.key];
          const Icon = integration.icon;
          return (
            <article key={integration.key} className="panel flex flex-col p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="flex min-w-0 items-start gap-3">
                  <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl border ${integration.tile}`}>
                    <Icon className="h-5 w-5" />
                  </span>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold">{integration.name}</p>
                      {enabled && (
                        <span className="inline-flex items-center gap-1.5 rounded-full border border-success/20 bg-success/[0.06] px-2 py-0.5 font-mono text-[9px] uppercase tracking-wide text-success">
                          <span className="h-1.5 w-1.5 rounded-full bg-success pulse-dot" />
                          Live
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{integration.desc}</p>
                  </div>
                </div>

                <button
                  type="button"
                  role="switch"
                  aria-checked={enabled}
                  aria-label={`Toggle ${integration.name}`}
                  onClick={() => {
                    setOn((prev) => ({ ...prev, [integration.key]: !prev[integration.key] }));
                    toast(`${integration.name} ${enabled ? "disconnected" : "connected"}`);
                  }}
                  className={`relative h-6 w-11 shrink-0 rounded-full border border-hairline transition-colors ${enabled ? "bg-primary" : "bg-muted"}`}
                >
                  <span
                    className={`absolute top-0.5 h-[18px] w-[18px] rounded-full bg-foreground transition-all ${enabled ? "left-[22px]" : "left-0.5"}`}
                  />
                </button>
              </div>

              {enabled && (
                <div className="rise mt-5 space-y-3 border-t border-hairline pt-5">
                  <div className="space-y-1.5">
                    <label htmlFor={`webhook-${integration.key}`} className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                      Webhook URL
                    </label>
                    <div className="flex items-center gap-2">
                      <input
                        id={`webhook-${integration.key}`}
                        readOnly
                        value={integration.webhook}
                        onFocus={(event) => event.target.select()}
                        className="min-w-0 flex-1 rounded-lg border border-hairline bg-background/60 px-3 py-2 font-mono text-xs text-foreground/90 outline-none transition-colors focus:border-success/40"
                      />
                      <button
                        type="button"
                        onClick={() => copy(integration.key, integration.webhook)}
                        aria-label={`Copy ${integration.name} webhook URL`}
                        className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-hairline bg-card/60 text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
                      >
                        {copied === integration.key ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
                      </button>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 text-xs">
                    <span className="h-1.5 w-1.5 rounded-full bg-success pulse-dot" />
                    <span className="font-medium text-success">Connected</span>
                    <span className="text-muted-foreground">· Last Ping: {integration.lastPing}</span>
                  </div>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </AppShell>
  );
}
