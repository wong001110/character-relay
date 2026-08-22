import { describe, expect, it } from "vitest";

import {
  componentCatalogCanonicalTotal,
  componentCatalogLayers,
  componentCatalogTotal
} from "./componentCatalog";

describe("component library inventory", () => {
  it("counts the canonical library and reusable utilities from exports", () => {
    expect(componentCatalogCanonicalTotal).toBe(42);
    expect(componentCatalogTotal).toBe(48);
    expect(
      Object.fromEntries(
        componentCatalogLayers.map((layer) => [layer.id, layer.components.length])
      )
    ).toEqual({ ui: 36, domain: 6, utility: 6 });
  });

  it("keeps compatibility components visible in the migration inventory", () => {
    const utilityLayer = componentCatalogLayers.find((layer) => layer.id === "utility");
    expect(utilityLayer?.components).toEqual([
      "NotebookField",
      "NotebookInput",
      "NotebookSection",
      "NotebookSelect",
      "NotebookTextarea",
      "Pagination"
    ]);
  });
});
