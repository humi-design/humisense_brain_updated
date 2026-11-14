/** Missions — goal-driven work executed end to end. */

import { PlannedArea } from "../PlannedArea";
import { Target } from "../../components/ui/icons";

export default function Missions() {
  return (
    <PlannedArea
      title="Missions"
      description="State an outcome. The Brain plans the work, executes what it may, and asks you only at the decisions that matter."
      icon={Target}
      layer="the Brain planning and orchestration layer"
      summary="A mission is a goal rather than a task. You describe the outcome; the Brain decomposes it, assigns steps to people or agents, executes the authorized parts, and stops for approval where policy requires it."
      capabilities={[
        {
          title: "Plan from an outcome",
          description:
            "Describe what finished looks like; the plan is derived, not hand-written.",
        },
        {
          title: "Execution with human checkpoints",
          description:
            "Steps run automatically up to the point where your authorization is required.",
        },
        {
          title: "Verification before completion",
          description:
            "A mission is not closed until the outcome has been checked against its goal.",
        },
        {
          title: "Full audit trail",
          description:
            "Every step, decision and approval is recorded and attributable.",
        },
      ]}
    />
  );
}
