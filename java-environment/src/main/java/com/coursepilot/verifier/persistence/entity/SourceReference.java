package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.Instant;

/** Independently persisted provenance row for a fact imported into a snapshot. */
@Entity
@Table(name = "source_reference")
public class SourceReference {
    @Id
    @Column(length = 120)
    private String refId;

    @Column(nullable = false, length = 16)
    private String kind;

    @Column(length = 120)
    private String snapshotId;

    @Column(nullable = false, length = 300)
    private String locator;

    private Instant capturedAt;

    protected SourceReference() {}

    public SourceReference(String refId, String kind, String snapshotId, String locator, Instant capturedAt) {
        this.refId = refId;
        this.kind = kind;
        this.snapshotId = snapshotId;
        this.locator = locator;
        this.capturedAt = capturedAt;
    }

    public String getRefId() { return refId; }
    public String getKind() { return kind; }
    public String getSnapshotId() { return snapshotId; }
    public String getLocator() { return locator; }
    public Instant getCapturedAt() { return capturedAt; }
}
