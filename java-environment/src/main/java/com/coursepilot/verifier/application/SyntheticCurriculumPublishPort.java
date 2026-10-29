package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.entity.Course;
import com.coursepilot.verifier.persistence.entity.CurriculumCourse;
import com.coursepilot.verifier.persistence.entity.CurriculumImportReceipt;
import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot;
import com.coursepilot.verifier.persistence.entity.CurriculumUnmodeledRule;
import com.coursepilot.verifier.persistence.repo.CurriculumUnmodeledRuleRepository;
import com.coursepilot.verifier.persistence.entity.Requirement;
import com.coursepilot.verifier.persistence.entity.SourceReference;
import com.coursepilot.verifier.persistence.repo.CourseRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumCourseRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumImportReceiptRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumSnapshotRepository;
import com.coursepilot.verifier.persistence.repo.RequirementRepository;
import edu.coursepilot.importer.ImportModels.CategoryRequirement;
import edu.coursepilot.importer.ImportModels.CurriculumDraft;
import edu.coursepilot.importer.ImportModels.CurriculumEntry;
import edu.coursepilot.importer.ImportModels.PublishPort;
import edu.coursepilot.importer.ImportModels.PublishResult;
import java.time.Instant;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Explicit synthetic-only persistence adapter used to exercise importer publication locally.
 * It is not a real-source publishing path; VERIFIED requires an independently checked baseline.
 */
@Service
public class SyntheticCurriculumPublishPort implements PublishPort {
    private static final String SNAPSHOT_PREFIX = "SYN_";

    private final CurriculumImportReceiptRepository receipts;
    private final CurriculumSnapshotRepository snapshots;
    private final CourseRepository courses;
    private final CurriculumCourseRepository memberships;
    private final RequirementRepository requirements;
    private final CurriculumUnmodeledRuleRepository unmodeledRules;

    public SyntheticCurriculumPublishPort(
        CurriculumImportReceiptRepository receipts,
        CurriculumSnapshotRepository snapshots,
        CourseRepository courses,
        CurriculumCourseRepository memberships,
        RequirementRepository requirements,
        CurriculumUnmodeledRuleRepository unmodeledRules) {
        this.unmodeledRules = unmodeledRules;
        this.receipts = receipts;
        this.snapshots = snapshots;
        this.courses = courses;
        this.memberships = memberships;
        this.requirements = requirements;
    }

    @Override
    @Transactional
    public PublishResult publish(CurriculumDraft draft) {
        if (!draft.publishable()) {
            throw new IllegalStateException("Rejected draft cannot be published");
        }
        Optional<CurriculumImportReceipt> previous = receipts.findById(draft.idempotencyKey());
        if (previous.isPresent()) {
            CurriculumImportReceipt receipt = previous.get();
            if (!receipt.getTrackId().equals(draft.trackId())) {
                throw new IllegalStateException("Importer key is bound to another track");
            }
            return new PublishResult(receipt.getSnapshotId(), true);
        }

        // Requirement.plan_id is limited to 64 characters. The key is a SHA-256
        // hex digest; retaining 60 hex characters after the namespace prefix gives
        // a 240-bit deterministic identifier within that persistence limit.
        String snapshotId = SNAPSHOT_PREFIX + draft.idempotencyKey().substring(0, 60);
        if (snapshots.existsById(snapshotId)) {
            // Do not adopt an existing snapshot that has no importer-owned idempotency receipt.
            throw new IllegalStateException("Snapshot ID already exists without import receipt");
        }
        CurriculumSnapshot snapshot = snapshots.save(new CurriculumSnapshot(
            snapshotId,
            CurriculumSnapshot.Kind.CURRICULUM,
            CurriculumSnapshot.State.PUBLISHED,
            CurriculumSnapshot.SourceKind.SYNTHETIC,
            CurriculumSnapshot.SourceValidation.SYNTHETIC,
            null,
            Instant.now()));

        for (CurriculumEntry entry : draft.entries()) {
            Course identity = courses.findById(entry.courseCode()).orElseGet(() ->
                // Course is a legacy global identity row. Snapshot-specific metadata belongs
                // only on CurriculumCourse; do not copy or overwrite imported facts here.
                courses.save(new Course(entry.courseCode(), entry.courseCode(), null, null)));
            var source = entry.source();
            memberships.save(new CurriculumCourse(
                snapshot,
                identity,
                entry.name(),
                // 连号课程组展开后的成员学分为未知（null），不能当 0 入库。
                entry.credits() == null ? null : entry.credits().doubleValue(),
                entry.category(),
                "SYNTHETIC",
                source.refId(),
                locator(draft, source.sheet(), source.row(), source.column()),
                source.capturedAt()));
        }

        for (CategoryRequirement requirement : draft.requirements()) {
            var source = requirement.source();
            SourceReference reference = new SourceReference(
                source.refId(),
                "SYNTHETIC",
                snapshotId,
                locator(draft, source.sheet(), source.row(), source.column()),
                source.capturedAt());
            requirements.save(new Requirement(
                snapshotId,
                requirement.category(),
                requirement.requiredCredits().doubleValue(),
                reference));
        }

        for (var rule : draft.unmodeledRules()) {
            unmodeledRules.save(new CurriculumUnmodeledRule(
                snapshot,
                rule.sheet(),
                rule.row(),
                rule.sourceLocator(),
                rule.subject(),
                rule.originalNote(),
                rule.currentStatus(),
                rule.sourceType(),
                CurriculumUnmodeledRule.Disposition.valueOf(rule.disposition().name())));
        }

        receipts.save(new CurriculumImportReceipt(
            draft.idempotencyKey(), snapshotId, draft.trackId(), draft.workbookHash(), Instant.now()));
        return new PublishResult(snapshotId, false);
    }

    private String locator(CurriculumDraft draft, String sheet, int row, int column) {
        return "sha256=" + draft.workbookHash() + "; " + sheet + "!R" + row + "C" + column;
    }
}
