import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";
import { MissionControl } from "./mission-control";

export const metadata: Metadata = pageMetadata({
  title: "Mission Control",
  description:
    "Monitor autonomous support performance, policy safety, and live SwapDesk agent executions in real time.",
  path: "/",
});

export default function MissionControlPage() {
  return <MissionControl />;
}
