package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.*;

import java.time.Instant;

/**
 * 培养/开课快照登记（contracts: SnapshotSummary）。
 *
 * 四个取值范围由 domain.schema.json 定死，这里用 Java 枚举挡住写入，
 * 避免库里出现契约不认的字符串。
 *
 * 要点（AGENTS.md 真实性与数据）：sourceValidation 与 sourceKind 是两件事。
 * 上传者自称 BROWSER_SNAPSHOT 不能让 sourceValidation 自动变 VERIFIED——
 * 核验是另一步的结论。所以这是两个独立字段，谁都不能由对方推导。
 */
@Entity
@Table(name = "curriculum_snapshot")
public class CurriculumSnapshot {

    /** contracts: SnapshotSummary.kind */
    public enum Kind { CURRICULUM, OFFERING }

    /** contracts: SnapshotSummary.state */
    public enum State { PUBLISHED, REJECTED }

    /** contracts: SnapshotSummary.sourceKind */
    /** OFFICIAL_DOCUMENT：官方公开文件（如教务课表 PDF）转换所得，仍需人工抽样核验后才能 VERIFIED。 */
    public enum SourceKind { CURRICULUM_FILE, BROWSER_SNAPSHOT, OFFICIAL_DOCUMENT, SYNTHETIC }

    /** contracts: SnapshotSummary.sourceValidation */
    public enum SourceValidation { VERIFIED, UNVERIFIED, SYNTHETIC }

    /** 契约 ^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$，最长 120。 */
    @Id
    @Column(length = 120)
    private String snapshotId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private Kind kind;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private State state;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 32)
    private SourceKind sourceKind;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private SourceValidation sourceValidation;

    /** 培养方案快照可以没有学期；契约允许 null。 */
    @Column(length = 120)
    private String termId;

    @Column(nullable = false)
    private Instant createdAt;

    /** 以下三项只对 OFFERING 快照有值：抓取时间与日历形状（契约 OfferingImport）。 */
    private Instant capturedAt;
    private Integer calendarWeeks;
    private Integer sectionsPerDay;

    public CurriculumSnapshot() {}

    public CurriculumSnapshot(String snapshotId, Kind kind, State state, SourceKind sourceKind,
                              SourceValidation sourceValidation, String termId, Instant createdAt) {
        this.snapshotId = snapshotId;
        this.kind = kind;
        this.state = state;
        this.sourceKind = sourceKind;
        this.sourceValidation = sourceValidation;
        this.termId = termId;
        this.createdAt = createdAt;
    }

    public String getSnapshotId() { return snapshotId; }
    public Kind getKind() { return kind; }
    public State getState() { return state; }
    public SourceKind getSourceKind() { return sourceKind; }
    public SourceValidation getSourceValidation() { return sourceValidation; }
    public String getTermId() { return termId; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getCapturedAt() { return capturedAt; }
    public Integer getCalendarWeeks() { return calendarWeeks; }
    public Integer getSectionsPerDay() { return sectionsPerDay; }

    /** 记录开课快照的抓取时间与日历形状。只在导入发布时调用一次。 */
    public void recordOfferingFacts(Instant capturedAt, int calendarWeeks, int sectionsPerDay) {
        this.capturedAt = capturedAt;
        this.calendarWeeks = calendarWeeks;
        this.sectionsPerDay = sectionsPerDay;
    }

    /**
     * 人工核验结论的落地：VERIFIED 或 REJECTED。只由 OfferingVerificationService 调用。
     * 以最近一次核验为准：通过则 VERIFIED，否则回到 UNVERIFIED。SYNTHETIC 快照不接受核验。
     */
    public void applyVerification(boolean passed) {
        if (this.sourceValidation == SourceValidation.SYNTHETIC) {
            throw new IllegalStateException("SYNTHETIC 快照不可核验");
        }
        this.sourceValidation = passed ? SourceValidation.VERIFIED : SourceValidation.UNVERIFIED;
    }
}
