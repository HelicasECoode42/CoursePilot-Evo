package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.*;

@Entity
public class ReviewNote {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    private String courseCode;
    private String teacherName;
    private String semester;
    private Double gpaImpact;
    private String attendance;
    private String workload;
    private String teachingQuality;
    @Column(length = 1000)
    private String content;
    private String sourceId;
    private String identityRole;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getCourseCode() { return courseCode; }
    public void setCourseCode(String courseCode) { this.courseCode = courseCode; }
    public String getTeacherName() { return teacherName; }
    public void setTeacherName(String teacherName) { this.teacherName = teacherName; }
    public String getSemester() { return semester; }
    public void setSemester(String semester) { this.semester = semester; }
    public Double getGpaImpact() { return gpaImpact; }
    public void setGpaImpact(Double gpaImpact) { this.gpaImpact = gpaImpact; }
    public String getAttendance() { return attendance; }
    public void setAttendance(String attendance) { this.attendance = attendance; }
    public String getWorkload() { return workload; }
    public void setWorkload(String workload) { this.workload = workload; }
    public String getTeachingQuality() { return teachingQuality; }
    public void setTeachingQuality(String teachingQuality) { this.teachingQuality = teachingQuality; }
    public String getContent() { return content; }
    public void setContent(String content) { this.content = content; }
    public String getSourceId() { return sourceId; }
    public void setSourceId(String sourceId) { this.sourceId = sourceId; }
    public String getIdentityRole() { return identityRole; }
    public void setIdentityRole(String identityRole) { this.identityRole = identityRole; }
}
