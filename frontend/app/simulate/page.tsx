import type { Metadata } from "next";
import { AppShell, PageTitle } from "@/components/AppShell";
import { CustomerSimulationWidget } from "@/components/CustomerSimulationWidget";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Customer Simulation",
  description: "Inject a customer complaint and route it to the SwapDesk autonomous agent.",
  path: "/simulate",
});

export default function SimulatePage() {
  return (
    <AppShell crumbs={[{ label: "SwapDesk", to: "/" }, { label: "Customer Simulation" }]} metrics={false}>
      <div className="mx-auto w-full max-w-2xl">
        <PageTitle
          title="Customer Simulation"
          sub="Type a customer complaint and route it to the autonomous agent. No backend required."
        />
        <CustomerSimulationWidget />
      </div>
    </AppShell>
  );
}
