export * from "./ScrapbookUI";

// Bridge existing shared overlays into the new UI namespace without forcing a migration.
export { PaperDrawer, PaperModal } from "../../NotebookUI";
