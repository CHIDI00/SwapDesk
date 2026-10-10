import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Integrations — SwapDesk",
  description: "Connect your existing helpdesk to route tickets to the SwapDesk AI.",
  openGraph: {
    title: "Integrations — SwapDesk",
    description: "Inbound webhook triggers for your existing helpdesk.",
  },
};

export default function IntegrationsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
