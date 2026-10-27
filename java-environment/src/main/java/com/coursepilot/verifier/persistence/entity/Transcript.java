package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;
import java.util.List;

@Entity
@Table(name = "transcript")
public class Transcript {
    @Id
    private String academicRecordId; // 契约要求的主键
    private String studentId;        // 归属字段，仅服务端使用
    private String curriculumSnapshotId;
    private boolean transcriptComplete;
    private String sourceKind;
    private int revision;
    private LocalDateTime createdAt;

    @OneToMany(cascade = CascadeType.ALL, fetch = FetchType.EAGER)
    @JoinColumn(name = "academic_record_id")
    private List<CompletedCourse> completedCourses;

    // Getters and Setters (Alt+Insert 生成)
    public String getAcademicRecordId() { return academicRecordId; }
    public void setAcademicRecordId(String academicRecordId) { this.academicRecordId = academicRecordId; }
    public String getStudentId() { return studentId; }
    public void setStudentId(String studentId) { this.studentId = studentId; }
    public String getCurriculumSnapshotId() { return curriculumSnapshotId; }
    public void setCurriculumSnapshotId(String curriculumSnapshotId) { this.curriculumSnapshotId = curriculumSnapshotId; }
    public boolean isTranscriptComplete() { return transcriptComplete; }
    public void setTranscriptComplete(boolean transcriptComplete) { this.transcriptComplete = transcriptComplete; }
    public String getSourceKind() { return sourceKind; }
    public void setSourceKind(String sourceKind) { this.sourceKind = sourceKind; }
    public int getRevision() { return revision; }
    public void setRevision(int revision) { this.revision = revision; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
    public List<CompletedCourse> getCompletedCourses() { return completedCourses; }
    public void setCompletedCourses(List<CompletedCourse> completedCourses) { this.completedCourses = completedCourses; }
}
