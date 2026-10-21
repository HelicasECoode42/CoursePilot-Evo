package com.coursepilot.verifier.web.dto;

import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot;

import java.time.format.DateTimeFormatter;
import java.util.List;

/**
 * 契约形状的快照出参（contracts/schemas/domain.schema.json 的 SnapshotSummary）。
 *
 * 和 RecordDtos 一样走 DTO 而不是直接序列化实体：SnapshotSummary 是
 * additionalProperties: false，实体以后加任何字段都会让响应不合契约。
 */
public final class SnapshotDtos {

    private SnapshotDtos() {}

    /** contracts: SnapshotSummary */
    public record SnapshotSummary(
        String snapshotId,
        String kind,
        String state,
        String sourceKind,
        String termId,
        String createdAt,
        String sourceValidation) {}

    /** listCurricula 的 data 是 { items: [...] }，不是裸数组。 */
    public record SnapshotList(List<SnapshotSummary> items) {}

    public static SnapshotSummary of(CurriculumSnapshot snapshot) {
        return new SnapshotSummary(
            snapshot.getSnapshotId(),
            snapshot.getKind().name(),
            snapshot.getState().name(),
            snapshot.getSourceKind().name(),
            snapshot.getTermId(),
            // 契约要求 format: date-time，固定按 UTC 的 ISO-8601 输出，
            // 不跟随运行机器的时区，否则同一条记录在不同机器上文本不同。
            DateTimeFormatter.ISO_INSTANT.format(snapshot.getCreatedAt()),
            snapshot.getSourceValidation().name());
    }
}
