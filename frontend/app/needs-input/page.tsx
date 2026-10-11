import type { Metadata } from "next";
import { AppShell, PageTitle } from "@/components/AppShell";
import { pageMetadata } from "@/lib/seo";
import { NeedsInputList } from "./needs-input-list";

export const metadata: Metadata = pageMetadata({
  title: "Needs input",
  description: "Cases parked waiting on a human reply.",
  path: "/needs-input",
});

export default function NeedsInputPage() {
  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Needs input" }]}>
      <PageTitle title="Needs input" sub="Cases parked waiting on a human reply" />
      <NeedsInputList />
    </AppShell>
  );
}
