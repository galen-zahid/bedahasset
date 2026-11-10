import { openDesign } from "@canva/design";
import type { DesignEditing } from "@canva/design";

export type NativeRepairPlan = {
  format: "cusbe-native-repair";
  source_sha256: string;
  width: number;
  height: number;
  targets: {
    role: string;
    expected_bbox: number[];
    replacement: DesignEditing.CreateShapeElementOpts;
  }[];
};

export function validatePlan(value: unknown): NativeRepairPlan {
  const p = value as NativeRepairPlan;
  if (p?.format !== "cusbe-native-repair" || !/^[a-f0-9]{64}$/.test(p.source_sha256) ||
      !Number.isFinite(p.width) || !Number.isFinite(p.height) || p.width <= 0 || p.height <= 0 ||
      !Array.isArray(p.targets) || p.targets.length < 1 || p.targets.length > 20) throw new Error("Invalid repair plan");
  const used = new Set<string>();
  for (const t of p.targets) {
    if (t.expected_bbox.length !== 4 || !t.expected_bbox.every(Number.isFinite) ||
        used.has(JSON.stringify(t.expected_bbox))) throw new Error("Ambiguous target bounds");
    used.add(JSON.stringify(t.expected_bbox));
    const r = t.replacement;
    if (![r.left, r.top, r.width, r.height, r.viewBox.left, r.viewBox.top, r.viewBox.width, r.viewBox.height].every(Number.isFinite) ||
        r.width <= 0 || r.height <= 0 || r.viewBox.width <= 0 || r.viewBox.height <= 0 ||
        !Array.isArray(r.paths) || !r.paths.length || r.paths.length > 30 ||
        r.paths.reduce((n, x) => n + x.d.length, 0) > 2000 ||
        r.paths.some((x) => !/^M[^MQT]*Z$/i.test(x.d) || x.fill?.mediaContainer ||
          x.fill?.colorContainer?.type !== "solid" || !/^#[a-f0-9]{6}$/.test(x.fill.colorContainer.color))) {
      throw new Error("Repair requires bounded solid native paths; gradients/media require manual review");
    }
  }
  return p;
}

export function matchesRaster(e: DesignEditing.AbsoluteElement, bounds: number[]) {
  return e.type === "rect" && !e.locked && e.rotation === 0 &&
    e.fill.mediaContainer.ref?.type === "image" &&
    [e.left, e.top, e.width, e.height].every((v, i) => Math.abs(v - (bounds[i] ?? Infinity)) <= 0.5);
}

export async function applyNativeRepair(plan: NativeRepairPlan) {
  validatePlan(plan);
  await openDesign({ type: "current_page" }, async (session) => {
    const page = session.page;
    if (page.type !== "absolute" || page.locked || page.dimensions?.width !== plan.width ||
        page.dimensions.height !== plan.height) throw new Error("Wrong, locked or unsupported candidate page");
    const elements = page.elements.toArray();
    // Resolve every target before changing the snapshot. Ambiguous or stale plans fail closed.
    const targets = plan.targets.map((t) => {
      const hits = elements.filter((e) => matchesRaster(e, t.expected_bbox));
      if (hits.length !== 1 || !hits[0]) throw new Error(`Target changed/ambiguous: ${t.role}`);
      return hits[0];
    });
    const states = plan.targets.map((t) => session.helpers.elementStateBuilder.createShapeElement(t.replacement));
    states.forEach((state, i) => {
      const target = targets[i];
      if (!target) throw new Error("Missing validated target");
      page.elements.insertBefore(target, state);
      page.elements.delete(target);
    });
    // One write; Canva undo or the separate candidate copy supplies rollback.
    await session.sync();
  });
  return { source_sha256: plan.source_sha256, replaced: plan.targets.map((t) => t.role),
    approximation: "SOLID_FILL: source gradients/textures removed only on replaced accents",
    structure: "NOT_TESTED", fidelity: "NOT_TESTED", buyer: "NOT_TESTED" };
}
