package com.coursepilot.verifier.web.dto;

import com.coursepilot.verifier.web.Envelope;
import java.util.List;

/** Response DTOs for the existing curriculum import contract. */
public final class ImportDtos {
    private ImportDtos() {}

    public record ImportResult(
        String snapshotId, String state, boolean reused, List<Envelope.Issue> issues) {}
}
