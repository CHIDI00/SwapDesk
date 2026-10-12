import type { Metadata } from "next";
import { AppShell, PageTitle } from "@/components/AppShell";
import { CustomerSimulationWidget } from "@/components/CustomerSimulationWidget";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Customer Support",
  description: "Open a new customer ticket and route it to the SwapDesk autonomous agent.",
  path: "/simulate",
});

export default function SimulatePage() {
  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Customer Support" }]} metrics={false}>
      <div className="mx-auto w-full max-w-2xl">
        <PageTitle
          title="Customer Support"
          sub="Describe the exchange, return, or refund and route it to the autonomous agent."
        />
        <CustomerSimulationWidget />
      </div>
    </AppShell>
  );
}
