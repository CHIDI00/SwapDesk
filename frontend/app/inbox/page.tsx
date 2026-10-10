import type { Metadata } from "next";
import Link from "next/link";
import { AppShell, PageTitle, StatusPill } from "@/components/AppShell";

export const metadata: Metadata = {
  title: "Inbox — SwapDesk",
  description: "Incoming exchange and return tickets handled by the SwapDesk agent.",
  openGraph: {
    title: "Inbox — SwapDesk",
    description: "Incoming exchange and return tickets.",
  },
};

const tickets = [
  { id: "TCK-9042", who: "Maya Koenig", msg: "The Jordan 4s arrived but are too tight. Need to exchange for a size 43.", s: "success", t: "2m" },
  { id: "TCK-9041", who: "Liam Ortega", msg: "Refund my Samba OGs, the sole is peeling.", s: "warning", t: "6m" },
  { id: "TCK-9040", who: "Aiko Tanaka", msg: "Swap New Balance 550 white for grey, size 39.", s: "success", t: "11m" },
  { id: "TCK-9039", who: "Noah Fischer", msg: "Ordered two pairs by mistake, cancel one.", s: "idle", t: "14m" },
  { id: "TCK-9038", who: "Sara Lindqvist", msg: "Where's my return label for the Gel-Kayano?", s: "danger", t: "22m" },
] as const;

export default function InboxPage() {
  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Inbox" }]}>
      <PageTitle title="Inbox" sub="128 tickets today · 96% resolved autonomously" />
      <div className="panel divide-y divide-hairline overflow-hidden">
        {tickets.map((t) => (
          <Link
            key={t.id}
            href="/"
            className="flex flex-col gap-2 p-4 transition-colors hover:bg-accent/40 sm:flex-row sm:items-center sm:gap-4 sm:p-5"
          >
            <div className="flex items-center justify-between gap-3 sm:w-40 sm:shrink-0 sm:flex-col sm:items-start sm:gap-1">
              <span className="font-mono text-xs text-muted-foreground">{t.id}</span>
              <span className="truncate text-sm font-semibold">{t.who}</span>
            </div>
            <p className="min-w-0 flex-1 text-sm leading-relaxed text-muted-foreground">{t.msg}</p>
            <div className="flex items-center gap-3">
              <StatusPill status={t.s} />
              <span className="font-mono text-xs text-muted-foreground">{t.t} ago</span>
            </div>
          </Link>
        ))}
      </div>
    </AppShell>
  );
}
