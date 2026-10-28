package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.*;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * 课程/教师评价证据（contracts: ReviewNote 的存储形态）。
 *
 * teacherKey 为 null 表示这条评价没能匹配到具体教师（只能说明课程层面）。
 * matchStatus 不存库：由 TeacherReviewAssembler 按「是否有教师、是否命中绑定」现算，
 * 避免库里出现「teacherKey 为空却标了已匹配」这种互相矛盾的状态。
 *
 * dimensions 把考勤、给分、作业量、授课等维度分开存，不能用一个总分代替。
 */
@Entity
@Table(name = "review_note")
public class ReviewNote {

    /** 与契约 ReviewNote.sourceKind 取值一致。 */
    public enum SourceKind { OFFICIAL_SYLLABUS, USER_IMPORT, EXTERNAL_LINK, SYNTHETIC }

    /** 与契约 ReviewNote.dimensions 的 items 枚举一致。 */
    public enum Dimension { GRADING, ATTENDANCE, WORKLOAD, EXAM, GROUP_WORK, PRESENTATION, TEACHING, OVERALL }

    @Id
    @Column(length = 120)
    private String reviewNoteId;

    @Column(nullable = false, length = 120)
    private String courseCode;

    @Column(length = 120)
    private String teacherKey;

    @Column(length = 120)
    private String termId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 32)
    private SourceKind sourceKind;

    private Instant publishedAt;

    @Column(length = 1000)
    private String sourceUrl;

    @Column(nullable = false, length = 1500)
    private String excerpt;

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(name = "review_note_dimension", joinColumns = @JoinColumn(name = "review_note_id"))
    @Enumerated(EnumType.STRING)
    @Column(name = "dimension", nullable = false, length = 32)
    private List<Dimension> dimensions = new ArrayList<>();

    public ReviewNote() {}

    public ReviewNote(String reviewNoteId, String courseCode, String teacherKey, String termId,
                      SourceKind sourceKind, Instant publishedAt, String sourceUrl,
                      String excerpt, List<Dimension> dimensions) {
        this.reviewNoteId = reviewNoteId;
        this.courseCode = courseCode;
        this.teacherKey = teacherKey;
        this.termId = termId;
        this.sourceKind = sourceKind;
        this.publishedAt = publishedAt;
        this.sourceUrl = sourceUrl;
        this.excerpt = excerpt;
        this.dimensions = new ArrayList<>(dimensions);
    }

    public String getReviewNoteId() { return reviewNoteId; }
    public String getCourseCode() { return courseCode; }
    public String getTeacherKey() { return teacherKey; }
    public String getTermId() { return termId; }
    public SourceKind getSourceKind() { return sourceKind; }
    public Instant getPublishedAt() { return publishedAt; }
    public String getSourceUrl() { return sourceUrl; }
    public String getExcerpt() { return excerpt; }
    public List<Dimension> getDimensions() { return dimensions; }
}
