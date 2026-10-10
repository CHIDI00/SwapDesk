import type { Metadata } from "next";
import { AppShell, PageTitle } from "@/components/AppShell";
import { CustomerSimulationWidget } from "@/components/CustomerSimulationWidget";

export const metadata: Metadata = {
  title: "Customer Simulation — SwapDesk",
  description: "Inject a customer complaint and route it to the autonomous agent.",
  openGraph: {
    title: "Customer Simulation — SwapDesk",
    description: "Route a simulated customer ticket to the autonomous agent.",
  },
};

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
