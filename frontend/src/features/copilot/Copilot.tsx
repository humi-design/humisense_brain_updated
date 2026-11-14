/** Copilot — conversational intelligence over company context. */

import { PlannedArea } from "../PlannedArea";
import { Bot } from "../../components/ui/icons";

export default function Copilot() {
  return (
    <PlannedArea
      title="Copilot"
      description="Ask questions, direct work and get answers grounded in your organization's own systems."
      icon={Bot}
      layer="the Brain reasoning and retrieval layer"
      summary="Copilot will answer questions using your connected applications and company memory, and cite where each answer came from. It is not a general-purpose chatbot: it is grounded in your organization's data, with permissions applied per user."
      capabilities={[
        {
          title: "Grounded answers with citations",
          description:
            "Every answer references the source record it came from, so it can be checked.",
        },
        {
          title: "Respects permissions",
          description:
            "You can only be told what you are already allowed to see in the source system.",
        },
        {
          title: "Takes action through the Brain",
          description:
            "Questions can turn into prepared work or missions rather than stopping at an answer.",
        },
        {
          title: "Conversation history",
          description: "Conversations are saved and searchable across the organization.",
        },
      ]}
    />
  );
}
