package com.coursepilot.verifier.web;

/** 幂等键重复但内容不同，或并发写入冲突（契约 409）。 */
public class RecordConflict extends RuntimeException {
    public RecordConflict(String message) {
        super(message);
    }
}
