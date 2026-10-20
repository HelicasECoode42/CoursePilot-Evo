package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.*;

@Entity
@Table(name = "course_offering")
public class CourseOffering {
    @Id
    @Column(length = 64)
    private String offeringId;

    @Column(nullable = false, length = 32)
    private String courseCode;

    private String teacher;

    @Column(length = 256)
    private String meetingTextRaw;   // 唯一时间真源

    @Column(length = 32)
    private String sourceKind;

    public CourseOffering() {}
    public CourseOffering(String offeringId, String courseCode, String teacher,
                          String meetingTextRaw, String sourceKind) {
        this.offeringId = offeringId;
        this.courseCode = courseCode;
        this.teacher = teacher;
        this.meetingTextRaw = meetingTextRaw;
        this.sourceKind = sourceKind;
    }

    public String getOfferingId() { return offeringId; }
    public String getCourseCode() { return courseCode; }
    public String getTeacher() { return teacher; }
    public String getMeetingTextRaw() { return meetingTextRaw; }
    public String getSourceKind() { return sourceKind; }
}
