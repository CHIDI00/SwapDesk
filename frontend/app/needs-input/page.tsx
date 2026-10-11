import type { Metadata } from "next";
import { AppShell, PageTitle } from "@/components/AppShell";
import { pageMetadata } from "@/lib/seo";
import { NeedsInputList } from "./needs-input-list";

export const metadata: Metadata = pageMetadata({
  title: "Action Required",
  description: "Cases parked waiting on a human reply.",
  path: "/needs-input",
});

export default function NeedsInputPage() {
  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Action Required" }]}>
      <PageTitle title="Action Required" sub="Cases parked waiting on a human reply" />
      <NeedsInputList />
    </AppShell>
  );
}
