package com.coursepilot.verifier.web.dto;

import java.util.List;

/**
 * 契约形状的学业记录 DTO，逐条对照 contracts/schemas/domain.schema.json 的
 * AcademicRecord / CompletedCourse。
 *
 * 这一层不只是改名。契约的 AcademicRecord 是 additionalProperties: false，
 * 字段里**没有** studentId——实体上的 studentId 是服务端归属信息，只用于
 * 对象级授权（b-verifier.md B-F6），不能跟着响应出去。把实体直接序列化
 * 会既多字段又泄露归属，所以对外一律走这里。
 *
 * 当前实体还不足以填满这个形状：它是「一门已修课一行」，没有记录级的
 * curriculumSnapshotId、createdAt 与 revision，而契约这三项必填。缺的是
 * 聚合实体（B-F1），不是命名问题，所以不在这里编造默认值，由
 * QueryController 以 UNKNOWN 封套说明缺什么。
 */
public final class RecordDtos {

    private RecordDtos() {}

    /** contracts: CompletedCourse.outcome */
    public enum Outcome { PASSED, FAILED, IN_PROGRESS, UNKNOWN }

    /** contracts: CompletedCourse */
    public record CompletedCourse(
        String courseCode,
        Double earnedCredits,
        Outcome outcome,
        String completedTerm) {}

    /** contracts: AcademicRecord */
    public record AcademicRecord(
        String academicRecordId,
        int revision,
        String curriculumSnapshotId,
        List<CompletedCourse> completedCourses,
        boolean transcriptComplete,
        String sourceKind,
        String createdAt) {}

    /** listAcademicRecords 的 data 是 { items: [...] }，不是裸数组。 */
    public record RecordList(List<AcademicRecord> items) {}
}
