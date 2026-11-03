package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.*;

/**
 * 班次（contracts: CourseOffering）。
 *
 * offeringId 同时是契约里的 classId（计划项 classId 直接引用它），全库唯一。
 * snapshotId 指向所属开课快照（curriculum_snapshot 中 kind=OFFERING 的行）。
 * 种子班次与历史行的 snapshotId 可能为空，读取时不假定它一定有值。
 *
 * meetingTextRaw 是唯一时间真源；parseStatus 只是导入时 Java 重新解析的结果，
 * 读取路径仍会再解析一次，不信任任何外部给的 parseStatus。
 */
@Entity
@Table(name = "course_offering")
public class CourseOffering {
    @Id
    @Column(length = 120)
    private String offeringId;

    @Column(nullable = false, length = 120)
    private String courseCode;

    private String teacher;

    @Column(length = 1000)
    private String meetingTextRaw;   // 唯一时间真源

    @Column(length = 32)
    private String sourceKind;

    /** 所属开课快照 id；导入班次必填，种子班次挂在 OFFER_2025_FALL。 */
    @Column(length = 120)
    private String snapshotId;

    /** 导入时 Java 解析 meetingTextRaw 的结果：PARSED / UNPARSED / INVALID。 */
    @Column(length = 16)
    private String parseStatus;

    @Column(length = 120)
    private String teacherKey;

    @Column(length = 120)
    private String sourceRefId;

    private Double credits;

    private Integer capacity;

    public CourseOffering() {}

    public CourseOffering(String offeringId, String courseCode, String teacher,
                          String meetingTextRaw, String sourceKind) {
        this.offeringId = offeringId;
        this.courseCode = courseCode;
        this.teacher = teacher;
        this.meetingTextRaw = meetingTextRaw;
        this.sourceKind = sourceKind;
    }

    public CourseOffering(String offeringId, String courseCode, String teacher,
                          String meetingTextRaw, String sourceKind, String snapshotId,
                          String parseStatus, String teacherKey, String sourceRefId,
                          Double credits, Integer capacity) {
        this(offeringId, courseCode, teacher, meetingTextRaw, sourceKind);
        this.snapshotId = snapshotId;
        this.parseStatus = parseStatus;
        this.teacherKey = teacherKey;
        this.sourceRefId = sourceRefId;
        this.credits = credits;
        this.capacity = capacity;
    }

    public String getOfferingId() { return offeringId; }
    public String getCourseCode() { return courseCode; }
    public String getTeacher() { return teacher; }
    public String getMeetingTextRaw() { return meetingTextRaw; }
    public String getSourceKind() { return sourceKind; }
    public String getSnapshotId() { return snapshotId; }
    public String getParseStatus() { return parseStatus; }
    public String getTeacherKey() { return teacherKey; }
    public String getSourceRefId() { return sourceRefId; }
    public Double getCredits() { return credits; }
    public Integer getCapacity() { return capacity; }
}
