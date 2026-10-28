package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.entity.Requirement;
import com.coursepilot.verifier.persistence.entity.Transcript;
import com.coursepilot.verifier.persistence.entity.Course;
import com.coursepilot.verifier.persistence.entity.CurriculumCourse;
import com.coursepilot.verifier.persistence.repo.CurriculumCourseRepository;
import com.coursepilot.verifier.persistence.repo.RequirementRepository;
import com.coursepilot.verifier.persistence.repo.TranscriptRepository;
import com.coursepilot.verifier.web.SnapshotMismatch;
import com.coursepilot.verifier.web.dto.AuditDtos;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 把学业核对结果摆成契约的 AuditResult。
 *
 * 数据源是学业记录聚合 Transcript（经 AcademicLedger 折算），算法与 AuditEvaluator 共用。
 * 本类只负责按契约摆形状，逐条产出 AuditItem。C 模块按 contracts/java.openapi.json
 * 调用 POST /api/v1/requirements/audit，拿到的就是这个结构。
 *
 * 仍然未知、统一记进 unknowns，不猜也不填假值：
 *   - Requirement 没有 courseCodes 与 sourceRefIds，courseCodes 只由已修记录反推，sourceRefIds 指向培养快照；
 *   - 学业记录未声明完整（transcriptComplete = false）时，记 TRANSCRIPT_COMPLETENESS_UNKNOWN，
 *     未满足的要求判 UNKNOWN；
 *   - 没有学业记录时，所有要求判 UNKNOWN，recordRevision 按契约最小值 1 占位，并记 ACADEMIC_RECORD_EMPTY；
 *   - UNKNOWN 的要求 gapCredits 为 null（契约允许），不给确定缺口数字。
 */
@Service
public class AuditResultAssembler {

    private final RequirementRepository requirementRepo;
    private final TranscriptRepository transcriptRepo;
    private final CurriculumCourseRepository curriculumCourses;

    public AuditResultAssembler(RequirementRepository requirementRepo,
                                TranscriptRepository transcriptRepo,
                                CurriculumCourseRepository curriculumCourses) {
        this.requirementRepo = requirementRepo;
        this.transcriptRepo = transcriptRepo;
        this.curriculumCourses = curriculumCourses;
    }

    public AuditDtos.AuditResult assemble(String curriculumSnapshotId, String academicRecordId) {
        Transcript transcript = transcriptRepo.findByStudentId(academicRecordId).orElse(null);
        if (transcript != null && !curriculumSnapshotId.equals(transcript.getCurriculumSnapshotId())) {
            throw new SnapshotMismatch(transcript.getCurriculumSnapshotId(), curriculumSnapshotId);
        }
        // 契约 recordRevision 最小为 1。没有学业记录时没有真实修订号，这里用 1 占位，
        // 并在 unknowns 里说明，消费方不能把它当成真实版本。
        int recordRevision = transcript == null ? 1 : transcript.getRevision();
        boolean transcriptComplete = transcript != null && transcript.isTranscriptComplete();

        List<AuditDtos.Issue> unknowns = new ArrayList<>();
        List<Requirement> requirements = requirementRepo.findByPlanId(curriculumSnapshotId);

        if (requirements.isEmpty()) {
            unknowns.add(new AuditDtos.Issue("CURRICULUM_NOT_FOUND",
                "培养方案 " + curriculumSnapshotId + " 没有类别要求，无法核对",
                "curriculumSnapshotId", false));
            return new AuditDtos.AuditResult(curriculumSnapshotId, academicRecordId,
                recordRevision, transcriptComplete, List.of(), List.of(), List.copyOf(unknowns));
        }

        Map<String, Course> snapshotCatalog = transcript == null ? Map.of()
            : curriculumCourses.findBySnapshot_SnapshotIdAndCourse_CourseCodeIn(
                    curriculumSnapshotId, transcript.getCompletedCourses().stream()
                        .map(c -> c.getCourseCode()).distinct().toList())
                .stream().filter(cc -> hasUsableFacts(cc, curriculumSnapshotId))
                .collect(java.util.stream.Collectors.toMap(
                    cc -> cc.getCourse().getCourseCode(),
                    cc -> new Course(cc.getCourse().getCourseCode(), cc.getName(), cc.getCredits(), cc.getCategory())));
        AcademicLedger ledger = AcademicLedger.of(transcript,
            code -> java.util.Optional.ofNullable(snapshotCatalog.get(code)));
        unknowns.addAll(ledger.issues());

        if (transcript == null) {
            unknowns.add(new AuditDtos.Issue("ACADEMIC_RECORD_EMPTY",
                "学业记录 " + academicRecordId + " 尚不存在，没有任何已修课程，各要求判 UNKNOWN、缺口不给值，"
                    + "recordRevision 为占位值 1",
                "academicRecordId", false));
        }

        List<AuditDtos.AuditItem> items = new ArrayList<>();
        for (Requirement req : requirements) {
            AuditDtos.State state = ledger.stateFor(req);
            // UNKNOWN 的要求不给确定缺口：null 表示无法确定（契约 gapCredits 可为 null）。
            Double gap = state == AuditDtos.State.UNKNOWN
                ? null
                : Math.max(0.0, req.getRequiredCredits() - ledger.earned(req.getCategory()));
            items.add(new AuditDtos.AuditItem(
                requirementId(req),
                ledger.courseCodes(req.getCategory()),
                req.getRequiredCredits(),
                ledger.earned(req.getCategory()),
                gap,
                state,
                sourceRefIds(req, curriculumSnapshotId)));
        }

        if (!transcriptComplete) {
            unknowns.add(new AuditDtos.Issue("TRANSCRIPT_COMPLETENESS_UNKNOWN",
                "学业记录未声明完整：已修学分只是下界，未满足的要求判 UNKNOWN、缺口不给确定值；已满足的要求不受影响",
                "transcriptComplete", false));
        }
        if (requirements.stream().anyMatch(req -> !hasRequirementSource(req, curriculumSnapshotId))) {
            unknowns.add(new AuditDtos.Issue("REQUIREMENT_SOURCE_REFS_MISSING",
                "部分类别要求没有绑定到当前培养快照的来源引用，courseCodes 仅由已修记录反推",
                "requirements", false));
        }

        return new AuditDtos.AuditResult(
            curriculumSnapshotId, academicRecordId, recordRevision, transcriptComplete,
            items, List.of(), List.copyOf(unknowns));
    }

    /**
     * requirementId 必须匹配契约的 ^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$，不能含中文。
     * 类别名是中文，所以用自增主键做稳定标识，类别放在 courseCodes 与消息里体现。
     */
    private String requirementId(Requirement req) {
        return "req-" + req.getId();
    }

    /**
     * 契约要求每条核对结论至少有一个来源引用（sourceRefIds minItems=1），
     * 即结论必须可追溯。当前判断完全来自该培养快照里的类别学分要求，
     * 所以引用快照本身；等 Requirement 记录了原表行号后换成更细的引用。
     */
    private List<String> sourceRefIds(Requirement requirement, String curriculumSnapshotId) {
        var source = requirement.getSourceReference();
        if (source != null && hasRequirementSource(requirement, curriculumSnapshotId)) {
            return List.of(source.getRefId());
        }
        // Legacy rows have no row-level provenance. Preserve the contract shape while adding
        // REQUIREMENT_SOURCE_REFS_MISSING to unknowns; do not treat this fallback as a source.
        return List.of("curriculum:" + curriculumSnapshotId);
    }

    private boolean hasRequirementSource(Requirement requirement, String curriculumSnapshotId) {
        var source = requirement.getSourceReference();
        return source != null
            && source.getRefId() != null
            && !source.getRefId().isBlank()
            && curriculumSnapshotId.equals(source.getSnapshotId())
            && ("CURRICULUM".equals(source.getKind()) || "SYNTHETIC".equals(source.getKind()))
            && source.getLocator() != null
            && !source.getLocator().isBlank();
    }

    private static boolean hasUsableFacts(CurriculumCourse cc, String snapshotId) {
        var source = cc.getSourceReference();
        return cc.getName() != null && !cc.getName().isBlank()
            && cc.getCategory() != null && !cc.getCategory().isBlank()
            && source != null && source.getRefId() != null && !source.getRefId().isBlank()
            && snapshotId.equals(source.getSnapshotId())
            && source.getLocator() != null && !source.getLocator().isBlank()
            && ("CURRICULUM".equals(source.getKind()) || "SYNTHETIC".equals(source.getKind()));
    }
}
