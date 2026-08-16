export * from "./ScrapbookUI";
export * from "./FeedbackUI";
export * from "./FunctionalIcon";
export * from "./OverlayUI";

// Bridge existing shared overlays into the new UI namespace without forcing a migration.
export { PaperDrawer, PaperModal } from "../../NotebookUI";
