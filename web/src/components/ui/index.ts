export * from "./ScrapbookUI";
export * from "./FeedbackUI";

// Bridge existing shared overlays into the new UI namespace without forcing a migration.
export { PaperDrawer, PaperModal } from "../../NotebookUI";
