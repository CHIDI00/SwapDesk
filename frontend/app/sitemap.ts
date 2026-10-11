import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/seo";

const routes: Array<{ path: string; priority: number }> = [
  { path: "", priority: 1 },
  { path: "/inbox", priority: 0.8 },
  { path: "/inventory", priority: 0.7 },
  { path: "/integrations", priority: 0.7 },
  { path: "/simulate", priority: 0.6 },
  { path: "/needs-input", priority: 0.6 },
  { path: "/settings", priority: 0.5 },
];

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();
  return routes.map(({ path, priority }) => ({
    url: `${SITE_URL}${path}`,
    lastModified,
    changeFrequency: "weekly",
    priority,
  }));
}
