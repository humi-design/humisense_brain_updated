/** Workforce — the specialized AI workers and what they are doing. */

import { PlannedArea } from "../PlannedArea";
import { LayoutGrid } from "../../components/ui/icons";

export default function Workforce() {
  return (
    <PlannedArea
      title="Workforce"
      description="Specialized AI workers with defined responsibilities, permissions and oversight."
      icon={LayoutGrid}
      layer="the agent orchestration layer"
      summary="Rather than one general assistant, Humisense runs specialized workers — each scoped to particular systems, with explicit permissions and a record of everything they did. This page will show them and their activity."
      capabilities={[
        {
          title: "Named, scoped workers",
          description:
            "Each worker has a defined role and a bounded set of systems it may touch.",
        },
        {
          title: "Live activity",
          description: "What each worker is doing now, and what it did recently.",
        },
        {
          title: "Permission boundaries",
          description:
            "What a worker may do without asking, and what always needs a human.",
        },
        {
          title: "Performance and outcomes",
          description:
            "Whether a worker's output is actually being accepted, and where it fails.",
        },
      ]}
    />
  );
}
