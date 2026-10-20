package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.*;

@Entity
@Table(name = "academic_record")
public class AcademicRecord {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 64)
    private String studentId;

    @Column(nullable = false, length = 32)
    private String courseCode;

    @Column(nullable = false)
    private boolean passed;

    private Double creditsEarned;

    private int attemptNo = 1;

    public AcademicRecord() {}
    public AcademicRecord(String studentId, String courseCode, boolean passed,
                          Double creditsEarned, int attemptNo) {
        this.studentId = studentId;
        this.courseCode = courseCode;
        this.passed = passed;
        this.creditsEarned = creditsEarned;
        this.attemptNo = attemptNo;
    }

    public Long getId() { return id; }
    public String getStudentId() { return studentId; }
    public void setStudentId(String studentId) { this.studentId = studentId; }
    public String getCourseCode() { return courseCode; }
    public void setCourseCode(String courseCode) { this.courseCode = courseCode; }
    public boolean isPassed() { return passed; }
    public void setPassed(boolean passed) { this.passed = passed; }
    public Double getCreditsEarned() { return creditsEarned; }
    public void setCreditsEarned(Double creditsEarned) { this.creditsEarned = creditsEarned; }
    public int getAttemptNo() { return attemptNo; }
    public void setAttemptNo(int attemptNo) { this.attemptNo = attemptNo; }
}
