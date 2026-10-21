package com.coursepilot.verifier.domain;

import com.fasterxml.jackson.annotation.JsonProperty;

public class ConflictResult {

    private final boolean hasKnownConflict;
    private final boolean hasUnknownParticipant;
    private final String reason;

    public ConflictResult(boolean hasKnownConflict, boolean hasUnknownParticipant, String reason) {
        this.hasKnownConflict = hasKnownConflict;
        this.hasUnknownParticipant = hasUnknownParticipant;
        this.reason = reason;
    }

    @JsonProperty("hasKnownConflict")
    public boolean hasKnownConflict() { return hasKnownConflict; }

    @JsonProperty("hasUnknownParticipant")
    public boolean hasUnknownParticipant() { return hasUnknownParticipant; }

    public String getReason() { return reason; }
}
