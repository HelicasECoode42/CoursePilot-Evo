package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.*;

import java.time.Instant;

/**
 * 写入幂等记录。作用域是 (主体, 幂等键)，内容摘要相同则原样回放 responseJson，
 * 摘要不同则 409（docs/04 第 3 节）。responseJson 是本次写入返回的记录本身，
 * 只存在本库，不进日志。
 */
@Entity
@Table(name = "idempotency_entry",
    uniqueConstraints = @UniqueConstraint(name = "uk_idem_student_key", columnNames = {"student_id", "idem_key"}))
public class IdempotencyEntry {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "student_id", nullable = false, length = 120)
    private String studentId;

    @Column(name = "idem_key", nullable = false, length = 120)
    private String idemKey;

    @Column(nullable = false, length = 64)
    private String requestDigest;

    @Lob
    @Column(nullable = false)
    private String responseJson;

    @Column(nullable = false)
    private Instant createdAt;

    protected IdempotencyEntry() {}

    public IdempotencyEntry(String studentId, String idemKey, String requestDigest,
                            String responseJson, Instant createdAt) {
        this.studentId = studentId;
        this.idemKey = idemKey;
        this.requestDigest = requestDigest;
        this.responseJson = responseJson;
        this.createdAt = createdAt;
    }

    public String getRequestDigest() { return requestDigest; }
    public String getResponseJson() { return responseJson; }
}
