import { openDesign } from "@canva/design";
import { findFonts } from "@canva/asset";
import type { FontRef } from "@canva/asset";
import type { DesignEditing } from "@canva/design";

// Addresses describe this snapshot only. They are not persistent IDs for mutation.
export function inspectElement(e: DesignEditing.AbsoluteElement, address: string): Record<string, unknown> {
  const base = { address, type: e.type, locked: e.locked,
    bboxInParent: [e.left, e.top, e.width, e.height], rotation: e.rotation, transparency: e.transparency };
  if (e.type === "text") return { ...base, classification: "native_text", text: e.text.readPlaintext(),
    textRegions: e.text.readTextRegions(), sourceTextVerification: "NOT_TESTED" };
  if (e.type === "group") return { ...base, classification: "group", children: e.contents.toArray().map((child, i) => inspectElement(child, `${address}/${i}`)) };
  if (e.type === "rect") {
    const media = e.fill.mediaContainer.ref;
    return { ...base, classification: media?.type === "image" ? "raster_image" : media ? "media" : "native_shape",
      mediaType: media?.type, color: e.fill.colorContainer.ref };
  }
  if (e.type === "shape") {
    const paths = e.paths.toArray().map((path) => ({ d: path.d, color: path.fill.colorContainer.ref,
      mediaType: path.fill.mediaContainer.ref?.type, isMediaEditable: path.fill.isMediaEditable }));
    return { ...base, classification: paths.some((p) => p.mediaType) ? "media_filled_shape" : "native_shape", paths, viewBox: e.viewBox };
  }
  return { ...base, classification: "manual_review_required" };
}

export async function inspectCurrentPage() {
  let report: Record<string, unknown> | undefined;
  await openDesign({ type: "current_page" }, async (session) => {
    if (session.page.type !== "absolute") throw new Error("Unsupported page: inspect manually in Canva");
    if (session.page.locked) throw new Error("Locked page: inspect an unlocked candidate copy");
    const elements = session.page.elements.toArray().map((e, i) => inspectElement(e, String(i)));
    const breakdown: Record<string, number> = {};
    const count = (items: Record<string, unknown>[]) => items.forEach((item) => {
      const key = String(item.classification);
      breakdown[key] = (breakdown[key] ?? 0) + 1;
      if (Array.isArray(item.children)) count(item.children);
    });
    count(elements);
    const fontRefs = new Set<string>();
    const collectFonts = (items: Record<string, unknown>[]) => items.forEach((item) => {
      const regions = (item.textRegions ?? []) as { formatting?: { fontRef?: string } }[];
      regions.forEach((region) => { if (region.formatting?.fontRef) fontRefs.add(region.formatting.fontRef); });
      if (Array.isArray(item.children)) collectFonts(item.children);
    });
    collectFonts(elements);
    const fontData = fontRefs.size ? (await findFonts({ fontRefs: [...fontRefs] as FontRef[] })).fonts : [];
    report = { version: 1, stage: "magic_layers_candidate", observedAt: new Date().toISOString(),
      scope: "current_page", addressing: "sibling order; group bounds relative to parent; IDs are snapshot-local",
      elements, breakdown,
      fonts: fontData.map((font) => ({ ref: font.ref, name: font.name, weights: font.weights })),
      background: { color: session.page.background?.colorContainer.ref, mediaType: session.page.background?.mediaContainer.ref?.type },
      qa: { structure: { verdict: "NOT_TESTED" }, fidelity: { verdict: "NOT_TESTED" }, buyer: { verdict: "NOT_TESTED" } },
      manualGates: ["Match elements to source pixels and semantic manifest", "Verify source wording and fonts",
        "Review unsupported elements, gradients, occlusions and stacking", "Compare aligned actual Canva export",
        "Test promised buyer edits in a separate buyer-test copy"] };
    // No mutations and no sync(): original design remains unchanged.
  });
  if (!report) throw new Error("Canva returned no readable page");
  return report;
}
