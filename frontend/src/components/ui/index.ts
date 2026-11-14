/**
 * Design system entry point.
 *
 * Product code imports from `components/ui` rather than from individual files,
 * so the public surface of the component system stays explicit and stable.
 *
 * The domain badges are re-exported here because the Layer 1 integration
 * screens have always imported them from this path. Keeping that contract
 * avoids touching working screens just to move a file.
 */

export { Button, IconButton, ButtonRow } from "./Button";
export type { ButtonProps, ButtonVariant, ButtonSize } from "./Button";

export { Badge } from "./Badge";
export type { BadgeTone } from "./Badge";

export { Card, CardHeader, CardBody, CardFooter } from "./Card";

export { Field, Input, Textarea, Select } from "./Field";

export { Tabs } from "./Tabs";
export type { TabItem } from "./Tabs";

export { StateBadge, StatusBadge, HealthDot, Stat } from "./DomainBadges";

export { Banner, Empty, ErrorNote, Loading } from "./Feedback";

export { formatDate, relativeTime, initials, categoryLabel } from "../../lib/format";

export * from "./icons";
