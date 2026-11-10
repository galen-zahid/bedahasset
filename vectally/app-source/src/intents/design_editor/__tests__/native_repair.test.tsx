import { matchesRaster, applyNativeRepair, validatePlan } from "../native_repair";
import { openDesign } from "@canva/design";
import type { DesignEditing } from "@canva/design";

jest.mock("@canva/design", () => ({ openDesign: jest.fn() }));
const replacement: DesignEditing.CreateShapeElementOpts = { left: 0, top: 0, width: 10, height: 10,
  viewBox: { left: 0, top: 0, width: 10, height: 10 },
  paths: [{ d: "M0 0L10 0L10 10Z", fill: { colorContainer: { type: "solid", color: "#00ff00" } } }] };
const plan = { format: "cusbe-native-repair", source_sha256: "a".repeat(64), width: 100, height: 100,
  targets: [{ role: "accent", expected_bbox: [0, 0, 10, 10], replacement }] };

it("rejects duplicate targets before any SDK work", () => {
  expect(() => validatePlan({ ...plan, targets: [...plan.targets, ...plan.targets] })).toThrow("Ambiguous");
});
it("preserves already-native shapes even with matching bounds", () => {
  const native = { type: "shape", left: 0, top: 0, width: 10, height: 10 };
  expect(matchesRaster(native as unknown as DesignEditing.AbsoluteElement, [0, 0, 10, 10])).toBe(false);
});
it("does not sync a stale or ambiguous plan", async () => {
  const sync = jest.fn();
  jest.mocked(openDesign).mockImplementation(async (_options: unknown, callback: any) => {
    await callback({ page: { type: "absolute", dimensions: { width: 100, height: 100 }, elements: { toArray: () => [] } }, sync });
  });
  await expect(applyNativeRepair(validatePlan(plan))).rejects.toThrow("Target changed/ambiguous");
  expect(sync).not.toHaveBeenCalled();
});
