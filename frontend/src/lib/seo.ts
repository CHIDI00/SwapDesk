import type { Metadata } from "next";

export const SITE_NAME = "SwapDesk";

export const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, "") ?? "https://swapdesk.vercel.app";

export const SITE_TAGLINE = "Autonomous Support Middleware";

export const SITE_DESCRIPTION =
  "SwapDesk is autonomous middleware between your helpdesk and your commerce stack. It resolves exchanges, returns, and refunds safely — idempotent by design and policy-aware.";

export const SITE_KEYWORDS = [
  "SwapDesk",
  "autonomous support",
  "AI customer support",
  "exchange automation",
  "return automation",
  "refund automation",
  "helpdesk middleware",
  "agentic AI",
  "Zendesk integration",
  "ecommerce operations",
];

export const SITE_TITLE = `${SITE_NAME} — ${SITE_TAGLINE}`;

type PageMetadataInput = {
  title: string;
  description: string;
  path?: string;
  keywords?: string[];
};

export function pageMetadata({
  title,
  description,
  path,
  keywords,
}: PageMetadataInput): Metadata {
  return {
    title,
    description,
    keywords,
    ...(path ? { alternates: { canonical: path } } : {}),
    openGraph: {
      title,
      description,
      siteName: SITE_NAME,
      type: "website",
      locale: "en_US",
      ...(path ? { url: path } : {}),
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
    },
  };
}
