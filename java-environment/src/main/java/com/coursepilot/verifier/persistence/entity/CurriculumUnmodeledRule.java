package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.*;

/**
 * 培养方案快照里一条未建模规则或待核问题（工作簿「备注」区段），原文保留。
 *
 * 不参与核验：系统还没有对应的执行规则。它存在的意义是被显式记录，并在学业核对与方案核验里
 * 作为 unknown 带出，让消费方看见「这份方案有哪些规则没有被系统算进去」。
 * EXCLUDED 表示原表课程行，已由负责人要求排除，只为追溯保留。
 */
@Entity
@Table(name = "curriculum_unmodeled_rule")
public class CurriculumUnmodeledRule {

    /** 与 ImportModels.UnmodeledRule.Disposition 一一对应。 */
    public enum Disposition { UNMODELED, EXCLUDED }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "curriculum_snapshot_id", nullable = false)
    private CurriculumSnapshot snapshot;

    @Column(nullable = false, length = 40)
    private String sheet;

    @Column(nullable = false)
    private int sourceRow;

    @Column(length = 200)
    private String sourceLocator;

    @Column(length = 500)
    private String subject;

    @Column(length = 2000)
    private String originalNote;

    @Column(length = 1000)
    private String currentStatus;

    @Column(length = 100)
    private String sourceType;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private Disposition disposition;

    protected CurriculumUnmodeledRule() {}

    public CurriculumUnmodeledRule(CurriculumSnapshot snapshot, String sheet, int sourceRow,
                                   String sourceLocator, String subject, String originalNote,
                                   String currentStatus, String sourceType, Disposition disposition) {
        this.snapshot = snapshot;
        this.sheet = sheet;
        this.sourceRow = sourceRow;
        this.sourceLocator = sourceLocator;
        this.subject = subject;
        this.originalNote = originalNote;
        this.currentStatus = currentStatus;
        this.sourceType = sourceType;
        this.disposition = disposition;
    }

    public Long getId() { return id; }
    public CurriculumSnapshot getSnapshot() { return snapshot; }
    public String getSheet() { return sheet; }
    public int getSourceRow() { return sourceRow; }
    public String getSourceLocator() { return sourceLocator; }
    public String getSubject() { return subject; }
    public String getOriginalNote() { return originalNote; }
    public String getCurrentStatus() { return currentStatus; }
    public String getSourceType() { return sourceType; }
    public Disposition getDisposition() { return disposition; }
}
