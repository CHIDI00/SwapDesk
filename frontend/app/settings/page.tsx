"use client";

import { useState } from "react";
import { toast } from "sonner";
import { AppShell, PageTitle } from "@/components/AppShell";

const opts = [
  { k: "auto", l: "Autonomous resolution", d: "Resolve eligible tickets without human approval." },
  { k: "idem", l: "Idempotency check before retry", d: "Query DB state after any timeout before re-calling a tool." },
  { k: "verify", l: "Deterministic final verification", d: "Block resolution unless DB state matches planned reply." },
  { k: "refund", l: "Allow refunds over $200", d: "Escalate high-value refunds to a human when off." },
];

export default function SettingsPage() {
  const [on, setOn] = useState<Record<string, boolean>>({ auto: true, idem: true, verify: true, refund: false });
  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Settings" }]}>
      <PageTitle title="Settings" sub="Guardrails for swapdesk-agent v2.4.1" />
      <div className="panel divide-y divide-hairline">
        {opts.map((o) => (
          <div key={o.k} className="flex items-center justify-between gap-4 p-5">
            <div className="min-w-0">
              <p className="text-sm font-semibold">{o.l}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">{o.d}</p>
            </div>
            <button
              role="switch"
              aria-checked={on[o.k]}
              aria-label={o.l}
              onClick={() => {
                setOn({ ...on, [o.k]: !on[o.k] });
                toast(`${o.l} ${on[o.k] ? "disabled" : "enabled"}`);
              }}
              className={`relative h-6 w-11 shrink-0 rounded-full border border-hairline transition-colors ${on[o.k] ? "bg-primary" : "bg-muted"}`}
            >
              <span
                className={`absolute top-0.5 h-[18px] w-[18px] rounded-full bg-foreground transition-all ${on[o.k] ? "left-[22px]" : "left-0.5"}`}
              />
            </button>
          </div>
        ))}
      </div>
    </AppShell>
  );
}
