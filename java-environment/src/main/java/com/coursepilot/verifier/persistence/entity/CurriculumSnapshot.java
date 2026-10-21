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
    public enum SourceKind { CURRICULUM_FILE, BROWSER_SNAPSHOT, SYNTHETIC }

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
}
