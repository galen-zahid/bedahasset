import { inspectElement, inspectCurrentPage } from "../inspection";
import { openDesign } from "@canva/design";
import type { DesignEditing } from "@canva/design";

jest.mock("@canva/design", () => ({ openDesign: jest.fn() }));

describe("Canva inspection evidence", () => {
  it("does not classify an image-filled rectangle as a native vector", () => {
    const e = { type: "rect", fill: { mediaContainer: { ref: { type: "image" } }, colorContainer: {} } };
    expect(inspectElement(e as unknown as DesignEditing.AbsoluteElement, "0").classification).toBe("raster_image");
  });
  it("does not classify image-filled paths as native illustrations", () => {
    const e = { type: "shape", paths: { toArray: () => [{ d: "M0 0Z", fill: {
      mediaContainer: { ref: { type: "image" } }, colorContainer: {}, isMediaEditable: false,
    } }] } };
    expect(inspectElement(e as unknown as DesignEditing.AbsoluteElement, "0").classification).toBe("media_filled_shape");
  });
  it("reads without syncing and leaves all QA verdicts untested", async () => {
    const sync = jest.fn();
    jest.mocked(openDesign).mockImplementation(async (_options: unknown, callback: any) => {
      await callback({ page: { type: "absolute", locked: false, elements: { toArray: () => [] } }, sync });
    });
    const report = await inspectCurrentPage();
    expect(sync).not.toHaveBeenCalled();
    expect(report.qa).toEqual({ structure: { verdict: "NOT_TESTED" }, fidelity: { verdict: "NOT_TESTED" }, buyer: { verdict: "NOT_TESTED" } });
  });
});
