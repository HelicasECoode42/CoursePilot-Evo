import { describe, expect, it } from "vitest";
import type { Issue, PlanSection } from "../contracts";
import { explainUnknownIssue } from "./unknown-explain";
import {
  courseCodeOfIssue,
  groupIssues,
  isWideLayout,
  requirementTag,
  sectionBadges,
} from "./result-issues";

const issue = (code: string, message: string): Issue => ({
  code,
  message,
  field: null,
  retryable: false,
});

const explain = (item: Issue) =>
  explainUnknownIssue(item, { CS103: "数据结构" });

describe("courseCodeOfIssue", () => {
  it("reads the course from unplaced and pending messages", () => {
    expect(
      courseCodeOfIssue(
        issue("SECTION_NOT_ASSIGNED", "课程 CS103：与其他推荐课程的时间冲突"),
        [],
      ),
    ).toBe("CS103");
    expect(
      courseCodeOfIssue(
        issue(
          "PENDING_COURSE",
          "课程 CS103 在修或结果未知，学科基础课 类别的缺口不能确定",
        ),
        [],
      ),
    ).toBe("CS103");
  });

  it("matches whole course codes only, so CS10 does not match CS103", () => {
    expect(
      courseCodeOfIssue(issue("CLASS_NOT_FOUND", "CS103-01 不在资料中"), [
        "CS10",
      ]),
    ).toBeNull();
    expect(
      courseCodeOfIssue(issue("CLASS_NOT_FOUND", "CS103-01 不在资料中"), [
        "CS103",
      ]),
    ).toBe("CS103");
  });

  it("keeps a plan-level code plan-level even when its message names a course", () => {
    expect(
      courseCodeOfIssue(
        issue("FAKE_MODEL", "W2 FAKE_MODEL mode=REAL courseCodes=CS103"),
        ["CS103"],
      ),
    ).toBeNull();
  });

  it("returns null for plan-level messages that name no plan course", () => {
    expect(
      courseCodeOfIssue(issue("TIMETABLE_UNVERIFIED", "班次未核验"), ["CS103"]),
    ).toBeNull();
  });
});

describe("groupIssues", () => {
  it("merges Java and Python unplaced entries for one course into one line, keeping the specific reason", () => {
    const grouped = groupIssues(
      [],
      [
        issue(
          "SECTION_UNASSIGNED",
          "课程 CS103 未指定班次，无法核验其时间与班次归属",
        ),
        issue("SECTION_NOT_ASSIGNED", "课程 CS103：与其他推荐课程的时间冲突"),
      ],
      ["CS103"],
      explain,
    );
    expect(grouped.byCourse.CS103).toEqual([
      {
        key: "unplaced:CS103",
        kind: "unplaced",
        text: "未排进课表：与其他推荐课程的时间冲突",
      },
    ]);
    expect(grouped.planLevel).toEqual([]);
  });

  it("uses a plain phrase when only the generic Java reason is available", () => {
    const grouped = groupIssues(
      [],
      [
        issue(
          "SECTION_UNASSIGNED",
          "课程 CS103 未指定班次，无法核验其时间与班次归属",
        ),
      ],
      ["CS103"],
      explain,
    );
    expect(grouped.byCourse.CS103[0].text).toBe("未排进课表：还没有选定班次");
  });

  it("keeps plan-level unknowns out of course cards and deduplicates them", () => {
    const timetable = issue("TIMETABLE_UNVERIFIED", "班次时间未核验");
    const grouped = groupIssues(
      [],
      [timetable, { ...timetable }],
      ["CS103"],
      explain,
    );
    expect(grouped.byCourse).toEqual({});
    expect(grouped.planLevel).toHaveLength(1);
    expect(grouped.planLevel[0].text).toContain("还没有经过核验");
  });

  it("treats CLASS_NOT_SELECTED as unplaced, once per course", () => {
    const grouped = groupIssues(
      [],
      [
        issue(
          "CLASS_NOT_SELECTED",
          "CS103 尚未选定班次，上课时间无法确认（演示数据）。",
        ),
        issue(
          "CLASS_NOT_SELECTED",
          "CS103 尚未选定班次，上课时间无法确认（演示数据）。",
        ),
      ],
      ["CS102", "CS103"],
      explain,
    );
    expect(grouped.byCourse.CS103).toEqual([
      {
        key: "unplaced:CS103",
        kind: "unplaced",
        text: "未排进课表：还没有选定班次",
      },
    ]);
    expect(grouped.planLevel).toEqual([]);
  });

  it("never falls back to the generic sentence for an unmapped code", () => {
    const grouped = groupIssues(
      [],
      [issue("SOME_NEW_CODE", "服务端说明原文")],
      [],
      explain,
    );
    expect(grouped.planLevel[0].text).toBe("SOME_NEW_CODE：服务端说明原文");
    expect(grouped.planLevel[0].text).not.toContain("暂时无法确认");
  });

  it("attaches violations to the course they name and keeps their server wording", () => {
    const grouped = groupIssues(
      [
        issue(
          "TIME_CONFLICT",
          "CS103-02 与方案中的 CS102-01 在周一第 1-2 节时间重叠",
        ),
      ],
      [],
      ["CS102", "CS103"],
      explain,
    );
    expect(grouped.byCourse.CS103?.[0]).toMatchObject({
      kind: "violation",
      text: "CS103-02 与方案中的 CS102-01 在周一第 1-2 节时间重叠",
    });
  });
});

describe("sectionBadges", () => {
  const section = (partial: Partial<PlanSection>): PlanSection =>
    ({
      scope: "TIMETABLE",
      verdict: "UNKNOWN",
      violations: [],
      unknownChecks: [],
      ...partial,
    }) as PlanSection;

  it("labels an unknown timetable as under human verification for an official unverified snapshot", () => {
    const [badge] = sectionBadges([section({})], () => "pending", true);
    expect(badge.label).toBe("课表：无法确认 · 人工核验中");
    expect(badge.tone).toBe("pending");
  });

  it("counts distinct unknown checks for the curriculum badge", () => {
    const unknown = issue("UNMODELED_CURRICULUM_RULES", "有 6 条规则");
    const [badge] = sectionBadges(
      [
        section({
          scope: "CURRICULUM",
          unknownChecks: [unknown, { ...unknown }],
        }),
      ],
      () => "pending",
      false,
    );
    expect(badge.label).toBe("毕业要求：需人工确认 1 条");
  });

  it("only shows pass when the tone says so", () => {
    const [badge] = sectionBadges(
      [section({ verdict: "VALID" })],
      () => "pending",
      false,
    );
    expect(badge.label).toBe("课表：待确认");
  });
});

describe("small helpers", () => {
  it("tags only explicit required and elective categories", () => {
    expect(requirementTag("专业必修")).toBe("必修");
    expect(requirementTag("专业选修")).toBe("选修");
    expect(requirementTag("通识")).toBeNull();
    expect(requirementTag(null)).toBeNull();
  });

  it("switches to two columns at 1024px and above", () => {
    expect(isWideLayout(1440)).toBe(true);
    expect(isWideLayout(1024)).toBe(true);
    expect(isWideLayout(1023)).toBe(false);
    expect(isWideLayout(390)).toBe(false);
  });
});
