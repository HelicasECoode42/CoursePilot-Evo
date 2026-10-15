import { describe, expect, it, vi } from "vitest";
import type { PlanningRequest } from "../contracts";
import { keyForRequest, requestDigest } from "./idempotency";

function request(overrides: Partial<PlanningRequest> = {}): PlanningRequest {
  return {
    schemaVersion: "1.0",
    curriculumSnapshotId: "curriculum-1",
    offeringSnapshotId: null,
    academicRecordId: "record-1",
    mode: "REAL",
    promptText: "",
    intent: {
      motives: ["GPA"],
      priorityOrder: ["GPA"],
      hardConstraints: [],
      softPreferences: [],
      pinnedTeacherCoursePairs: [],
      interestTags: [],
      careerDirectionIds: [],
    },
    previousPlanId: null,
    ...overrides,
  };
}

describe("keyForRequest", () => {
  it("creates a key on the first submission", () => {
    const create = vi.fn(() => "key-1");
    expect(keyForRequest(null, request(), create)).toEqual({
      digest: requestDigest(request()),
      key: "key-1",
    });
    expect(create).toHaveBeenCalledTimes(1);
  });

  it("reuses the key when retrying the exact same request", () => {
    const create = vi.fn(() => "key-1");
    const first = keyForRequest(null, request(), create);
    const retry = keyForRequest(first, request(), create);
    expect(retry.key).toBe("key-1");
    expect(create).toHaveBeenCalledTimes(1);
  });

  it("issues a new key once the student changes a condition", () => {
    const create = vi
      .fn()
      .mockReturnValueOnce("key-1")
      .mockReturnValueOnce("key-2");
    const first = keyForRequest(null, request(), create);
    const changed = keyForRequest(
      first,
      request({ promptText: "改成少作业" }),
      create,
    );
    expect(changed.key).toBe("key-2");
    expect(create).toHaveBeenCalledTimes(2);
  });

  it("detects a change hidden inside the intent", () => {
    const create = vi
      .fn()
      .mockReturnValueOnce("key-1")
      .mockReturnValueOnce("key-2");
    const first = keyForRequest(null, request(), create);
    const base = request();
    const changed = keyForRequest(
      first,
      { ...base, intent: { ...base.intent, motives: ["GPA", "LOW_WORKLOAD"] } },
      create,
    );
    expect(changed.key).toBe("key-2");
  });
});
