import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import { IntegrationsPage } from "./integrations-page";

export const metadata: Metadata = pageMetadata({
  title: "Integrations",
  description: "Connect your helpdesk to route inbound support tickets to SwapDesk AI.",
  path: "/integrations",
});

export default function IntegrationsRoute() {
  return <IntegrationsPage />;
}
