package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * 开课快照人工抽样核验的审计记录（只增不改）。
 *
 * 记录谁核验、谁上传、抽样多少、错多少、样本文件哈希与结论。同一快照可以有多条记录；
 * 快照当前的 sourceValidation 只取最近一条的结论（见 CurriculumSnapshot.applyVerification）。
 * 名字只作为审计字段保存，不写入日志。
 */
@Entity
@Table(name = "offering_verification_audit")
public class OfferingVerificationAudit {

    @Id
    @Column(length = 120)
    private String verificationId;

    @Column(nullable = false, length = 120)
    private String snapshotId;

    @Column(nullable = false, length = 120)
    private String verifierName;

    @Column(nullable = false, length = 120)
    private String uploaderName;

    @Column(nullable = false)
    private int sampleSize;

    @Column(nullable = false)
    private int errorCount;

    @Column(nullable = false, length = 64)
    private String sampleFileSha256;

    /** VERIFIED 或 REJECTED。 */
    @Column(nullable = false, length = 16)
    private String outcome;

    @Column(length = 500)
    private String note;

    @Column(nullable = false, length = 120)
    private String requestId;

    @Column(nullable = false)
    private Instant verifiedAt;

    protected OfferingVerificationAudit() {}

    public OfferingVerificationAudit(String verificationId, String snapshotId, String verifierName,
                                     String uploaderName, int sampleSize, int errorCount,
                                     String sampleFileSha256, String outcome, String note,
                                     String requestId, Instant verifiedAt) {
        this.verificationId = verificationId;
        this.snapshotId = snapshotId;
        this.verifierName = verifierName;
        this.uploaderName = uploaderName;
        this.sampleSize = sampleSize;
        this.errorCount = errorCount;
        this.sampleFileSha256 = sampleFileSha256;
        this.outcome = outcome;
        this.note = note;
        this.requestId = requestId;
        this.verifiedAt = verifiedAt;
    }

    public String getVerificationId() { return verificationId; }
    public String getSnapshotId() { return snapshotId; }
    public String getVerifierName() { return verifierName; }
    public String getUploaderName() { return uploaderName; }
    public int getSampleSize() { return sampleSize; }
    public int getErrorCount() { return errorCount; }
    public String getSampleFileSha256() { return sampleFileSha256; }
    public String getOutcome() { return outcome; }
    public String getNote() { return note; }
    public String getRequestId() { return requestId; }
    public Instant getVerifiedAt() { return verifiedAt; }
}
