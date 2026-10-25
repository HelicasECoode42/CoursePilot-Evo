package com.coursepilot.verifier.web.dto;

import java.util.List;

public class PlanValidationDto {
    // 接收前端发来的整个课表数据
    public record PlanValidationRequest(
        String term,              // 学期
        String snapshotId,        // 快照ID
        List<PlanItem> planItems, // 选中的所有课
        List<String> hardConstraints // 硬性限制（比如不能排周五）
    ) {}

    // 课表里的每一门课
    public record PlanItem(String courseCode, String classId, String meetingTextRaw) {}

    // 返回的核验结果
    public record PlanValidationResult(String verdict, List<String> reasons, List<ConflictItem> conflicts) {}

    // 发生冲突的详情
    public record ConflictItem(String classId, String conflictWith, String timeSlot) {}
}
