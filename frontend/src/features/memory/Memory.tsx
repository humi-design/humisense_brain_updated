/** Memory — the unified company knowledge layer. */

import { PlannedArea } from "../PlannedArea";
import { BookOpen } from "../../components/ui/icons";

export default function Memory() {
  return (
    <PlannedArea
      title="Memory"
      description="One connected record of what the organization knows, and how it relates."
      icon={BookOpen}
      layer="the context graph and memory layer"
      summary="Memory is what makes the Brain useful over time: the relationships between people, projects, documents, machines and events. It is built from what Layer 1 already connects, and it respects the same permissions."
      capabilities={[
        {
          title: "Relationship-aware",
          description:
            "Understands that a customer, a ticket and a production line are connected.",
        },
        {
          title: "Built from connected systems",
          description:
            "Populated from the applications and sources already integrated in Apps.",
        },
        {
          title: "Permission-respecting",
          description:
            "Memory never surfaces something a user is not entitled to see.",
        },
        {
          title: "Correctable",
          description:
            "People can correct or remove what the Brain has recorded.",
        },
      ]}
    />
  );
}
