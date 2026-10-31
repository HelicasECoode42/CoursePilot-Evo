package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.*;

/**
 * 教师与课程的绑定（一门课由哪位教师开，按培养快照登记）。
 *
 * AGENTS.md：教师绑定课程，评价按课程 + 教师 + 学期匹配。这张表就是「课程-教师」
 * 这一对的唯一来源；ReviewNote 只有同时命中这里的绑定才算 COURSE_TEACHER_MATCHED。
 *
 * currentTermId / sourceValidation 表示「当期是否开课」以及这条说法的来源是否经过核验。
 * 只有 sourceValidation=VERIFIED 且 currentTermId 非空，才可能得到 CURRENT_VERIFIED
 * （见 TeacherReviewAssembler.availability）。当前种子全部不是 VERIFIED。
 *
 * bindingId 是内部主键（快照|课程|教师），不进任何对外 DTO。
 */
@Entity
@Table(name = "teacher_course")
public class TeacherCourse {

    /** 与 CurriculumSnapshot.SourceValidation 取值一致，但独立声明，避免实体之间互相依赖。 */
    public enum SourceValidation { VERIFIED, UNVERIFIED, SYNTHETIC }

    @Id
    @Column(length = 400)
    private String bindingId;

    @Column(nullable = false, length = 120)
    private String curriculumSnapshotId;

    @Column(nullable = false, length = 120)
    private String courseCode;

    @Column(nullable = false, length = 120)
    private String teacherKey;

    @Column(nullable = false, length = 200)
    private String teacherDisplayName;

    /** 当期学期标识；null 表示没有当期开课的说法。 */
    @Column(length = 120)
    private String currentTermId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private SourceValidation sourceValidation;

    public TeacherCourse() {}

    public TeacherCourse(String curriculumSnapshotId, String courseCode, String teacherKey,
                         String teacherDisplayName, String currentTermId,
                         SourceValidation sourceValidation) {
        this.bindingId = curriculumSnapshotId + "|" + courseCode + "|" + teacherKey;
        this.curriculumSnapshotId = curriculumSnapshotId;
        this.courseCode = courseCode;
        this.teacherKey = teacherKey;
        this.teacherDisplayName = teacherDisplayName;
        this.currentTermId = currentTermId;
        this.sourceValidation = sourceValidation;
    }

    public String getBindingId() { return bindingId; }
    public String getCurriculumSnapshotId() { return curriculumSnapshotId; }
    public String getCourseCode() { return courseCode; }
    public String getTeacherKey() { return teacherKey; }
    public String getTeacherDisplayName() { return teacherDisplayName; }
    public String getCurrentTermId() { return currentTermId; }
    public SourceValidation getSourceValidation() { return sourceValidation; }
}
