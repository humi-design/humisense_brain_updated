/** Governance — approvals, policy and audit. */

import { PlannedArea } from "../PlannedArea";
import { Shield } from "../../components/ui/icons";

export default function Governance() {
  return (
    <PlannedArea
      title="Governance"
      description="Decide what the Brain may do on its own, what needs approval, and prove what happened."
      icon={Shield}
      layer="the governance and approval layer"
      summary="Humisense acts on real business systems, so authority has to be explicit. Governance defines the boundary between autonomous action and human approval, and keeps the record that makes it auditable."
      capabilities={[
        {
          title: "Approval policies",
          description:
            "Rules for what may proceed automatically and what must wait for a person.",
        },
        {
          title: "Approval queue",
          description:
            "Prepared work presented with its evidence, ready to approve or reject.",
        },
        {
          title: "Complete audit trail",
          description:
            "Who or what acted, on which system, with what authority and result.",
        },
        {
          title: "Autonomy controls",
          description:
            "Raise or lower what agents may do without asking, per system.",
        },
      ]}
    />
  );
}
