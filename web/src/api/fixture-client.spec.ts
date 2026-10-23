import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import { beforeAll, describe, expect, it } from "vitest";

import domainSchema from "../../../contracts/schemas/domain.schema.json";
import { FIXTURE_PREVIOUS_PLAN_ID, FixtureApiClient } from "./fixture-client";

/**
 * fixture 必须和契约同形。
 *
 * 演示数据漂出契约是这个项目反复踩的坑：字段名看着对、联调才炸。B 那边
 * requirementId 混了中文、sourceRefIds 返回空数组，两边都以为自己是对的，
 * 直到真打一次才发现。fixture 没有联调这一步兜底，所以必须在这里钉死——
 * 否则我们会照着一份不合契约的假数据把页面做出来。
 */
const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
ajv.addSchema(domainSchema, "domain");

function expectValid(definition: string, instance: unknown): void {
  const validate = ajv.getSchema(`domain#/$defs/${definition}`);
  expect(validate, `契约里没有 ${definition} 这个定义`).toBeTruthy();
  const ok = validate!(instance);
  expect(ok ? [] : (validate!.errors ?? [])).toEqual([]);
}

describe("fixture 数据符合 domain.schema.json", () => {
  const client = new FixtureApiClient();

  // fixture 客户端和真实客户端一样，没有会话就拒绝调用业务端点。
  beforeAll(async () => {
    await client.createSession();
  });

  it("学业记录与核对结果同形", async () => {
    const records = await client.listSessionRecords();
    for (const record of records.items) expectValid("AcademicRecord", record);
    if (records.items.length > 0) {
      const audit = await client.auditRequirements(
        (await client.listCurricula()).items[0]!.snapshotId,
        records.items[0]!.academicRecordId,
      );
      expectValid("AuditResult", audit);
    }
  });

  it("培养快照同形", async () => {
    for (const item of (await client.listCurricula()).items) {
      expectValid("SnapshotSummary", item);
    }
  });

  it("班次搜索结果同形", async () => {
    const found = await client.searchSessionOfferings(
      FIXTURE_PREVIOUS_PLAN_ID,
      "CS103",
    );
    expect(found.items.length).toBeGreaterThan(0);
    for (const offering of found.items) expectValid("CourseOffering", offering);
  });

  it("查不到班次时给空数组，不是错误", async () => {
    const none = await client.searchSessionOfferings(
      FIXTURE_PREVIOUS_PLAN_ID,
      "NOT-A-COURSE",
    );
    expect(none.items).toEqual([]);
  });

  it("三个演示班次覆盖冲突、可选、时间未知三种状态", async () => {
    // 页面要分别展示这三种，fixture 少一种就演示不出来。
    const { items } = await client.searchSessionOfferings(
      FIXTURE_PREVIOUS_PLAN_ID,
      "CS103",
    );
    const verdicts: string[] = [];
    for (const offering of items) {
      const replaced = await client.replaceSessionPlanItem(
        {
          previousPlanId: FIXTURE_PREVIOUS_PLAN_ID,
          courseCode: "CS103",
          selectedClassId: offering.classId,
        },
        `idem-${offering.classId}`,
      );
      expectValid("PlanValidation", replaced.verification);
      for (const item of replaced.items) expectValid("PlanItem", item);
      for (const constraint of replaced.hardConstraints)
        expectValid("Constraint", constraint);
      verdicts.push(replaced.verification.verdict);
    }
    expect(new Set(verdicts)).toEqual(new Set(["VALID", "INVALID", "UNKNOWN"]));
  });

  it("替换后产生新的方案版本，旧方案 id 保留", async () => {
    // 旧方案要留着给学生返回对照，所以新旧 id 不能相同。
    const replaced = await client.replaceSessionPlanItem(
      {
        previousPlanId: FIXTURE_PREVIOUS_PLAN_ID,
        courseCode: "CS103",
        selectedClassId: "CS103-02",
      },
      "idem-new-version",
    );
    expect(replaced.previousPlanId).toBe(FIXTURE_PREVIOUS_PLAN_ID);
    expect(replaced.planId).not.toBe(FIXTURE_PREVIOUS_PLAN_ID);
  });

  it("演示判决一律是 SIMULATION，不冒充真实课表", async () => {
    // AGENTS.md：REAL 不能用 synthetic。演示数据标成 REAL_TIMETABLE
    // 会让「缺班次不给绿色通过」那道门禁失效。
    const replaced = await client.replaceSessionPlanItem(
      {
        previousPlanId: FIXTURE_PREVIOUS_PLAN_ID,
        courseCode: "CS103",
        selectedClassId: "CS103-02",
      },
      "idem-scope",
    );
    expect(replaced.verification.scope).toBe("SIMULATION");
  });

  it("教师选项与评价同形，且至少一条评价依据有限", async () => {
    const curriculumId = (await client.listCurricula()).items[0]!.snapshotId;
    const options = await client.listTeacherCourseOptions(curriculumId, null);
    expect(options.length).toBeGreaterThan(0);
    for (const option of options) expectValid("TeacherCourseOption", option);

    const reviews = await client.searchReviews("CS103", null);
    // 空数组会让下面的校验循环空转通过，所以先确认真有数据。
    expect(reviews.length).toBeGreaterThan(0);
    for (const review of reviews) expectValid("ReviewNote", review);
    // 页面要能演示「依据有限」，所以不能全是课程+教师都对上的评价。
    // matchStatus 三档是 COURSE_TEACHER_MATCHED / COURSE_ONLY / UNVERIFIED，
    // 后两档都表示这条证据不足以支撑「这位老师这门课」的结论。
    expect(
      reviews.some((review) => review.matchStatus !== "COURSE_TEACHER_MATCHED"),
    ).toBe(true);
  });

  it("运行报告同形", async () => {
    expectValid("RunReport", await client.getRunReport("fixture-run"));
  });
});
