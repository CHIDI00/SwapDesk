"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Inbox, Boxes, Settings, Ticket, ChevronRight, Zap, LayoutDashboard, PanelLeftClose, PanelLeftOpen, MessageCircleQuestion } from "lucide-react";
import type { ReactNode } from "react";
import { API_BASE } from "@/lib/api";
import { ThemeToggle } from "@/components/ThemeToggle";

const nav = [
  { to: "/", label: "Mission Control", icon: LayoutDashboard },
  { to: "/inbox", label: "Inbox", icon: Inbox },
  { to: "/inventory", label: "Inventory", icon: Boxes },
  { to: "/needs-input", label: "Action Required", icon: MessageCircleQuestion },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

type BackendState = "checking" | "live" | "down";

function BackendStatus({ expanded }: { expanded: boolean }) {
  const [state, setState] = useState<BackendState>("checking");

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const res = await fetch(`${API_BASE}/v1/health`);
        if (!cancelled) setState(res.ok ? "live" : "down");
      } catch {
        if (!cancelled) setState("down");
      }
    };
    void check();
    const timer = window.setInterval(() => void check(), 30000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const label = state === "live" ? "Online" : state === "down" ? "Offline" : "Checking";
  return (
    <div
      className={`grid h-10 place-items-center rounded-xl border border-hairline text-xs text-muted-foreground ${expanded ? "w-full grid-cols-none px-3" : "w-10"}`}
      title={label}
      role="status"
      aria-label={label}
    >
      <span className="flex items-center gap-2">
        <span
          className={`h-2 w-2 rounded-full ${state === "live" ? "bg-success pulse-dot" : state === "down" ? "bg-danger" : "bg-muted-foreground/50"}`}
        />
        {expanded && <span className="truncate text-[11px]">{label}</span>}
        <span className="sr-only">{label}</span>
      </span>
    </div>
  );
}

export function AppShell({ crumbs, children }: { crumbs: { label: string; to?: string }[]; children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [expanded, setExpanded] = useState(false);

  const isActive = (to: string) => pathname === to;

  const handleSimulateTicket = () => {
    router.push("/simulate");
  };

  return (
    <div className="flex min-h-screen w-full">
      {/* Desktop sidebar */}
      <aside className={`glass fixed inset-y-0 left-0 z-40 hidden h-screen shrink-0 flex-col items-center gap-2 border-y-0 border-l-0 py-6 md:flex ${expanded ? "w-56 items-stretch px-4" : "w-20"}`}>
        <Link href="/" aria-label="SwapDesk Mission Control" className={`mb-6 flex items-center ${expanded ? "gap-3 px-2" : "justify-center"}`}>
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary glow-success">
            <Ticket className="h-5 w-5" />
          </span>
          {expanded && <span className="truncate text-sm font-semibold">SwapDesk</span>}
        </Link>
        {nav.map(({ to, label, icon: Icon }) => (
          <Link
            key={label}
            href={to}
            aria-current={isActive(to) ? "page" : undefined}
            title={label}
            className={`group flex items-center rounded-xl px-3 py-2.5 text-sm transition-colors hover:bg-accent/60 hover:text-foreground ${isActive(to) ? "bg-accent/80 text-foreground" : "text-muted-foreground"} ${expanded ? "w-full gap-3" : "w-12 justify-center"}`}
          >
            <Icon className="h-[18px] w-[18px] shrink-0" />
            {expanded ? (
              <span className="truncate">{label}</span>
            ) : (
              <span className="sr-only">{label}</span>
            )}
          </Link>
        ))}
        <div className="mt-auto flex flex-col items-center gap-2">
          <ThemeToggle expanded={expanded} />
          <BackendStatus expanded={expanded} />
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            aria-label={expanded ? "Collapse sidebar" : "Expand sidebar"}
            title={expanded ? "Collapse sidebar" : "Expand sidebar"}
            className="grid h-10 w-10 place-items-center rounded-xl border border-hairline text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
          >
            {expanded ? <PanelLeftClose className="h-[18px] w-[18px]" /> : <PanelLeftOpen className="h-[18px] w-[18px]" />}
          </button>
        </div>
      </aside>

      <div className={`flex min-w-0 flex-1 flex-col pb-[calc(5rem+env(safe-area-inset-bottom))] md:pb-0 ${expanded ? "md:ml-56" : "md:ml-20"}`}>
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
                title="Submit a ticket to the agent backend"
              >
                <Zap className="h-3.5 w-3.5 text-success" />
                New Ticket
              </button>
            </div>
          </div>
        </header>
        <main className="mx-auto min-w-0 w-full max-w-[1600px] flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>

      {/* Mobile bottom nav */}
      <nav
        aria-label="Main navigation"
        className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-6 border-t border-hairline bg-[var(--nav-bg)] px-3 pb-[calc(env(safe-area-inset-bottom)+0.6rem)] pt-2.5 shadow-[0_-16px_40px_-24px_rgba(0,0,0,0.95)] md:hidden"
      >
        {nav.map(({ to, label, icon: Icon }) => {
          const active = isActive(to);
          return (
            <Link
              key={label}
              href={to}
              aria-current={active ? "page" : undefined}
              className="group flex flex-col items-center gap-1 py-1 transition-transform duration-150 active:scale-90"
            >
              <span
                className={`grid h-8 w-[4.25rem] place-items-center rounded-full transition-all duration-200 ${active
                    ? "bg-primary/[0.12] text-primary shadow-[inset_0_0_0_1px_rgba(91,255,159,0.22),0_0_18px_-4px_rgba(91,255,159,0.35)]"
                    : "text-muted-foreground group-hover:text-foreground group-active:bg-[var(--surface-hover)]"
                  }`}
              >
                <Icon className="h-5 w-5" />
              </span>
              <span
                className={`truncate max-w-full text-[10px] font-medium transition-colors ${active ? "text-primary" : "text-muted-foreground"
                  }`}
              >
                {label.split(" ")[0]}
              </span>
            </Link>
          );
        })}
      </nav>
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
