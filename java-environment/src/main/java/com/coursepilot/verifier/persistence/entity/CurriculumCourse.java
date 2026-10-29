package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.*;

import java.time.Instant;

/** Explicit membership of a catalog course in a curriculum snapshot. */
@Entity
// 唯一键包含 name：占位课程号（如 008532xx）在工作簿里对应体育1..6 等多门课，
// 同一快照下编号可以重复，名称不同即是不同的课。
@Table(name = "curriculum_course", uniqueConstraints = @UniqueConstraint(
    name = "uk_curriculum_course_snapshot_code_name",
    columnNames = {"curriculum_snapshot_id", "course_code", "name"}))
public class CurriculumCourse {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "curriculum_snapshot_id", nullable = false)
    private CurriculumSnapshot snapshot;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "course_code", nullable = false)
    private Course course;

    // Attributes belong to this curriculum edition, not to the global course identity.
    // Nullable for legacy rows: absence must remain UNKNOWN, never be backfilled from Course.
    @Column(length = 200)
    private String name;
    private Double credits;
    @Column(length = 100)
    private String category;
    @Column(length = 200)
    private String suggestedTerm;

    @ManyToOne(fetch = FetchType.LAZY, cascade = CascadeType.PERSIST)
    @JoinColumn(name = "source_ref_id")
    private SourceReference sourceReference;

    protected CurriculumCourse() {}

    public CurriculumCourse(CurriculumSnapshot snapshot, Course course) {
        this.snapshot = snapshot;
        this.course = course;
    }

    public CurriculumCourse(CurriculumSnapshot snapshot, Course course, String name,
                            Double credits, String category, String sourceKind,
                            String sourceRefId, String sourceLocator, Instant sourceCapturedAt) {
        this.snapshot = snapshot;
        this.course = course;
        this.name = name;
        this.credits = credits;
        this.category = category;
        this.sourceReference = new SourceReference(sourceRefId, sourceKind,
            snapshot.getSnapshotId(), sourceLocator, sourceCapturedAt);
    }

    public Long getId() { return id; }
    public CurriculumSnapshot getSnapshot() { return snapshot; }
    public Course getCourse() { return course; }
    public String getName() { return name; }
    public Double getCredits() { return credits; }
    public String getCategory() { return category; }
    public String getSuggestedTerm() { return suggestedTerm; }
    public void setSuggestedTerm(String suggestedTerm) { this.suggestedTerm = suggestedTerm; }
    public SourceReference getSourceReference() { return sourceReference; }
}
