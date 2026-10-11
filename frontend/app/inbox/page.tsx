import type { Metadata } from "next";
import { AppShell, PageTitle } from "@/components/AppShell";
import { pageMetadata } from "@/lib/seo";
import { InboxList } from "./inbox-list";

export const metadata: Metadata = pageMetadata({
  title: "Inbox",
  description: "Saved SwapDesk cases from the agent backend.",
  path: "/inbox",
});

export default function InboxPage() {
  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Inbox" }]}>
      <PageTitle title="Inbox" sub="Saved cases from the agent backend" />
      <InboxList />
    </AppShell>
  );
}
