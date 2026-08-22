import * as sharedComponents from "./components/shared";
import * as uiComponents from "./components/ui";
import * as notebookComponents from "./NotebookUI";
import * as paginationComponents from "./Pagination";

export interface ComponentCatalogLayer {
  id: "ui" | "domain" | "utility";
  label: string;
  description: string;
  components: string[];
}

function exportedComponentNames(module: object): string[] {
  return Object.keys(module).sort((left, right) => left.localeCompare(right));
}

const uiComponentNames = exportedComponentNames(uiComponents);
const uiComponentNameSet = new Set(uiComponentNames);
const utilityComponentNames = [
  ...exportedComponentNames(notebookComponents).filter(
    (component) => !uiComponentNameSet.has(component)
  ),
  ...exportedComponentNames(paginationComponents)
].sort((left, right) => left.localeCompare(right));

export const componentCatalogLayers: ComponentCatalogLayer[] = [
  {
    id: "ui",
    label: "UI primitives & scrapbook objects",
    description:
      "Business-agnostic controls, feedback, overlays, icons, and stationery objects.",
    components: uiComponentNames
  },
  {
    id: "domain",
    label: "Character Relay compositions",
    description:
      "Product-aware provider, credential, context, and participant compositions.",
    components: exportedComponentNames(sharedComponents)
  },
  {
    id: "utility",
    label: "Notebook & navigation utilities",
    description:
      "Production-reused notebook controls and pagination that are not yet in the canonical barrels.",
    components: utilityComponentNames
  }
];

export const componentCatalogCanonicalTotal = componentCatalogLayers
  .filter((layer) => layer.id !== "utility")
  .reduce((total, layer) => total + layer.components.length, 0);

export const componentCatalogTotal = componentCatalogLayers.reduce(
  (total, layer) => total + layer.components.length,
  0
);
