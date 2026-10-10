"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Inbox, Activity, Boxes, Database, Settings, Plug, Ticket, ChevronRight, Zap } from "lucide-react";
import type { ReactNode } from "react";

const nav = [
  { to: "/", label: "Inbox", icon: Inbox },
  { to: "/traces", label: "Active Traces", icon: Activity },
  { to: "/inventory", label: "Inventory", icon: Boxes },
  { to: "/database", label: "Database", icon: Database },
  { to: "/integrations", label: "Integrations", icon: Plug },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

export function AppShell({ crumbs, children, metrics = true }: { crumbs: { label: string; to?: string }[]; children: ReactNode; metrics?: boolean }) {
  const pathname = usePathname();
  const router = useRouter();

  const isActive = (to: string) => pathname === to;

  const handleSimulateTicket = () => {
    router.push("/simulate");
  };

  return (
    <div className="flex min-h-screen w-full">
      {/* Desktop sidebar */}
      <aside className="glass fixed inset-y-0 left-0 z-40 hidden h-screen w-20 shrink-0 flex-col items-center gap-2 border-y-0 border-l-0 py-6 md:flex">
        <Link href="/" aria-label="SwapDesk Mission Control" className="mb-6 flex items-center justify-center">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary glow-success">
            <Ticket className="h-5 w-5" />
          </span>
        </Link>
        {nav.map(({ to, label, icon: Icon }) => (
          <Link
            key={label}
            href={to}
            aria-current={isActive(to) ? "page" : undefined}
            className={`group flex w-12 items-center justify-center rounded-xl px-3 py-2.5 text-sm transition-colors hover:bg-accent/60 hover:text-foreground ${isActive(to) ? "bg-accent/80 text-foreground" : "text-muted-foreground"}`}
            title={label}
          >
            <Icon className="h-[18px] w-[18px] shrink-0" />
            <span className="sr-only">{label}</span>
          </Link>
        ))}
        <div className="mt-auto grid h-10 w-10 place-items-center rounded-xl border border-hairline text-xs text-muted-foreground" title="Agent online">
          <span className="h-2 w-2 rounded-full bg-success pulse-dot" />
          <span className="sr-only">
            Agent online
            <span className="font-mono">swapdesk-agent v2.4.1</span>
          </span>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col pb-[calc(5rem+env(safe-area-inset-bottom))] md:ml-20 md:pb-0">
        <header className="glass sticky top-0 z-30 border-x-0 border-t-0">
          <div className="flex flex-col gap-3 px-4 py-3 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8 lg:py-4">
            <nav className="flex min-w-0 items-center gap-1.5 text-sm">
              {crumbs.map((c, i) => (
                <span key={c.label} className="flex min-w-0 items-center gap-1.5">
                  {i > 0 && <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60" />}
                  {c.to ? (
                    <Link href={c.to} className="truncate text-muted-foreground hover:text-foreground">
                      {c.label}
                    </Link>
                  ) : (
                    <span className="truncate font-mono text-foreground">{c.label}</span>
                  )}
                </span>
              ))}
            </nav>
            <div className="flex flex-wrap items-center gap-2 sm:gap-3">
              <button
                type="button"
                onClick={handleSimulateTicket}
                className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-hairline bg-card/60 px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent/60"
                title="Inject a mock ticket into the queue"
              >
                <Zap className="h-3.5 w-3.5 text-success" />
                Simulate Ticket
              </button>
              {metrics && (
                <div className="grid grid-cols-2 gap-2 sm:flex sm:gap-3">
                  <Metric label="Completion Rate" value="96%" tone="success" />
                  <Metric label="Cost per Case" value="$0.24" />
                </div>
              )}
            </div>
          </div>
        </header>
        <main className="mx-auto min-w-0 w-full max-w-[1600px] flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>

      {/* Mobile bottom nav */}
      <nav aria-label="Main navigation" className="glass fixed inset-x-0 bottom-0 z-40 grid grid-cols-6 border-x-0 border-b-0 pb-[env(safe-area-inset-bottom)] md:hidden">
        {nav.map(({ to, label, icon: Icon }) => (
          <Link
            key={label}
            href={to}
            aria-current={isActive(to) ? "page" : undefined}
            className={`flex flex-col items-center gap-1 py-2.5 text-[10px] ${isActive(to) ? "text-primary" : "text-muted-foreground"}`}
          >
            <Icon className="h-5 w-5" />
            <span className="truncate">{label.split(" ")[0]}</span>
          </Link>
        ))}
      </nav>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "success" }) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-3 rounded-xl border border-hairline bg-card/60 px-3 py-2 sm:justify-start">
      <span className="truncate text-xs text-muted-foreground">{label}</span>
      <span className={`num text-lg font-semibold ${tone === "success" ? "text-success" : "text-foreground"}`}>{value}</span>
    </div>
  );
}

export function PageTitle({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold sm:text-3xl">{title}</h1>
        {sub && <p className="mt-1 text-sm text-muted-foreground">{sub}</p>}
      </div>
      {right}
    </div>
  );
}

export function StatusPill({ status }: { status: "success" | "warning" | "danger" | "idle"; children?: ReactNode }) {
  const map = {
    success: "bg-success/10 text-success border-success/25",
    warning: "bg-warning/10 text-warning border-warning/25",
    danger: "bg-danger/10 text-danger border-danger/25",
    idle: "bg-muted text-muted-foreground border-hairline",
  } as const;
  const label = { success: "Resolved", warning: "Retrying", danger: "Failed", idle: "Queued" }[status];
  return (
    <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${map[status]}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {label}
    </span>
  );
}
