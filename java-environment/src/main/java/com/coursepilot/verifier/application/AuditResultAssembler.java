package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.entity.Requirement;
import com.coursepilot.verifier.persistence.entity.Transcript;
import com.coursepilot.verifier.persistence.repo.CourseRepository;
import com.coursepilot.verifier.persistence.repo.RequirementRepository;
import com.coursepilot.verifier.persistence.repo.TranscriptRepository;
import com.coursepilot.verifier.web.dto.AuditDtos;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

/**
 * 把学业核对结果摆成契约的 AuditResult。
 *
 * 数据源是学业记录聚合 Transcript（经 AcademicLedger 折算），算法与 AuditEvaluator 共用。
 * 本类只负责按契约摆形状，逐条产出 AuditItem。C 模块按 contracts/java.openapi.json
 * 调用 POST /api/v1/requirements/audit，拿到的就是这个结构。
 *
 * 仍然未知、统一记进 unknowns，不猜也不填假值：
 *   - Requirement 没有 courseCodes 与 sourceRefIds，courseCodes 只由已修记录反推，sourceRefIds 指向培养快照；
 *   - 学业记录未声明完整（transcriptComplete = false）时，记 TRANSCRIPT_COMPLETENESS_UNKNOWN；
 *   - 没有学业记录时，recordRevision 按契约最小值 1 占位，并记 ACADEMIC_RECORD_EMPTY。
 */
@Service
public class AuditResultAssembler {

    private final RequirementRepository requirementRepo;
    private final TranscriptRepository transcriptRepo;
    private final CourseRepository courseRepo;

    public AuditResultAssembler(RequirementRepository requirementRepo,
                                TranscriptRepository transcriptRepo,
                                CourseRepository courseRepo) {
        this.requirementRepo = requirementRepo;
        this.transcriptRepo = transcriptRepo;
        this.courseRepo = courseRepo;
    }

    public AuditDtos.AuditResult assemble(String curriculumSnapshotId, String academicRecordId) {
        Transcript transcript = transcriptRepo.findByStudentId(academicRecordId).orElse(null);
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

        AcademicLedger ledger = AcademicLedger.of(transcript, courseRepo::findById);
        unknowns.addAll(ledger.issues());

        if (transcript == null) {
            unknowns.add(new AuditDtos.Issue("ACADEMIC_RECORD_EMPTY",
                "学业记录 " + academicRecordId + " 尚不存在，没有任何已修课程，recordRevision 为占位值 1",
                "academicRecordId", false));
        } else if (!ledger.hasPassed()) {
            unknowns.add(new AuditDtos.Issue("ACADEMIC_RECORD_EMPTY",
                "学业记录 " + academicRecordId + " 没有已通过的课程，缺口无法计算",
                "academicRecordId", false));
        }

        List<AuditDtos.AuditItem> items = new ArrayList<>();
        for (Requirement req : requirements) {
            items.add(new AuditDtos.AuditItem(
                requirementId(req),
                ledger.courseCodes(req.getCategory()),
                req.getRequiredCredits(),
                ledger.earned(req.getCategory()),
                Math.max(0.0, req.getRequiredCredits() - ledger.earned(req.getCategory())),
                ledger.stateFor(req),
                sourceRefIds(curriculumSnapshotId)));
        }

        if (!transcriptComplete) {
            unknowns.add(new AuditDtos.Issue("TRANSCRIPT_COMPLETENESS_UNKNOWN",
                "学业记录未声明完整，课程清单可能不全，缺口只按已登记课程计算",
                "transcriptComplete", false));
        }
        unknowns.add(new AuditDtos.Issue("REQUIREMENT_SOURCE_REFS_MISSING",
            "当前 Requirement 没有记录课程清单与来源引用，courseCodes 仅由已修记录反推，sourceRefIds 为快照级引用",
            "requirements", false));

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
    private List<String> sourceRefIds(String curriculumSnapshotId) {
        return List.of("curriculum:" + curriculumSnapshotId);
    }
}
