package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.*;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * 学业记录聚合（contracts: AcademicRecord）。记录级字段在这里：revision、
 * curriculumSnapshotId、transcriptComplete、sourceKind、createdAt；
 * 已修课程在 TranscriptCourse 子表。
 *
 * academicRecordId 目前等于主体标识：SubjectGuard 的假设是一个主体只有一份学业记录，
 * 所以 requireOwnRecord 直接比较二者。studentId 只服务端用于归属，不进对外 DTO。
 * 每次写入递增 revision，子表整体替换而不是累加。
 */
@Entity
@Table(name = "transcript")
public class Transcript {

    /** contracts: AcademicRecord.sourceKind */
    public enum SourceKind { USER_IMPORT, SYNTHETIC }

    @Id
    @Column(length = 120)
    private String academicRecordId;

    @Column(nullable = false, unique = true, length = 120)
    private String studentId;

    @Column(nullable = false)
    private int revision;

    @Column(nullable = false, length = 120)
    private String curriculumSnapshotId;

    @Column(nullable = false)
    private boolean transcriptComplete;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private SourceKind sourceKind;

    @Column(nullable = false)
    private Instant createdAt;

    /** 乐观锁：并发写同一主体时后到者失败，不静默覆盖前者的 revision。 */
    @Version
    private Long version;

    @OneToMany(mappedBy = "transcript", cascade = CascadeType.ALL, orphanRemoval = true, fetch = FetchType.EAGER)
    @OrderBy("position ASC")
    private List<TranscriptCourse> completedCourses = new ArrayList<>();

    protected Transcript() {}

    public Transcript(String studentId) {
        this.academicRecordId = studentId;
        this.studentId = studentId;
    }

    /** 写入一个新版本：revision 加一，子表整体替换。 */
    public void revise(String curriculumSnapshotId, boolean transcriptComplete,
                       SourceKind sourceKind, Instant createdAt, List<TranscriptCourse> courses) {
        this.revision += 1;
        this.curriculumSnapshotId = curriculumSnapshotId;
        this.transcriptComplete = transcriptComplete;
        this.sourceKind = sourceKind;
        this.createdAt = createdAt;
        this.completedCourses.clear();
        for (int i = 0; i < courses.size(); i++) {
            TranscriptCourse c = courses.get(i);
            c.attach(this, i);
            this.completedCourses.add(c);
        }
    }

    public String getAcademicRecordId() { return academicRecordId; }
    public String getStudentId() { return studentId; }
    public int getRevision() { return revision; }
    public String getCurriculumSnapshotId() { return curriculumSnapshotId; }
    public boolean isTranscriptComplete() { return transcriptComplete; }
    public SourceKind getSourceKind() { return sourceKind; }
    public Instant getCreatedAt() { return createdAt; }
    public List<TranscriptCourse> getCompletedCourses() { return completedCourses; }
}
