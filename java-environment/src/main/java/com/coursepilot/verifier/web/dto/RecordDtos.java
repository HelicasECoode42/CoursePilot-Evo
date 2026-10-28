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
 * 实体映射见 application.AcademicRecordMapper；attemptNo 只在库里，不在这里。
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

    /**
     * contracts: AcademicRecordInput。schemaVersion 必须为 "1.0"，其余字段的范围与
     * 格式由 AcademicRecordService 校验。transcriptComplete 用包装类型，缺省时能被识别为缺失。
     */
    public record AcademicRecordInput(
        String schemaVersion,
        String curriculumSnapshotId,
        List<CompletedCourse> completedCourses,
        Boolean transcriptComplete,
        String sourceKind) {}
}
