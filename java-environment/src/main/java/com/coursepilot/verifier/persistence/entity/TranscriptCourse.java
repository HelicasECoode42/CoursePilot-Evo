package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.*;

import java.math.BigDecimal;

/**
 * 学业记录明细（contracts: CompletedCourse）。一行是一次修读。
 *
 * attemptNo 不在契约输出里，只在库里：AuditResultAssembler 的重修去重依赖它。
 */
@Entity
@Table(name = "transcript_course")
public class TranscriptCourse {

    /** contracts: CompletedCourse.outcome */
    public enum Outcome { PASSED, FAILED, IN_PROGRESS, UNKNOWN }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(optional = false, fetch = FetchType.LAZY)
    @JoinColumn(name = "academic_record_id", nullable = false)
    private Transcript transcript;

    @Column(nullable = false)
    private int position;

    @Column(nullable = false, length = 120)
    private String courseCode;

    /** 同一课程的第几次修读，从 1 起。 */
    @Column(nullable = false)
    private int attemptNo;

    /** 可空：学分未知时不能当 0 处理。 */
    @Column(precision = 6, scale = 2)
    private BigDecimal earnedCredits;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private Outcome outcome;

    @Column(length = 120)
    private String completedTerm;

    protected TranscriptCourse() {}

    public TranscriptCourse(String courseCode, int attemptNo, BigDecimal earnedCredits,
                            Outcome outcome, String completedTerm) {
        this.courseCode = courseCode;
        this.attemptNo = attemptNo;
        this.earnedCredits = earnedCredits;
        this.outcome = outcome;
        this.completedTerm = completedTerm;
    }

    void attach(Transcript transcript, int position) {
        this.transcript = transcript;
        this.position = position;
    }

    public Long getId() { return id; }
    public int getPosition() { return position; }
    public String getCourseCode() { return courseCode; }
    public int getAttemptNo() { return attemptNo; }
    public BigDecimal getEarnedCredits() { return earnedCredits; }
    public Outcome getOutcome() { return outcome; }
    public String getCompletedTerm() { return completedTerm; }
}
