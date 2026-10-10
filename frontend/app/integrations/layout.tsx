import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Integrations",
  description: "Connect your existing helpdesk to route tickets to the SwapDesk AI via inbound webhooks.",
  path: "/integrations",
});

export default function IntegrationsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
