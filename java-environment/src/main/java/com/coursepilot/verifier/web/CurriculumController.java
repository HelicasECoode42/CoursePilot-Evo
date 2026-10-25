package com.coursepilot.verifier.web;

import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot;
import com.coursepilot.verifier.persistence.repo.CurriculumSnapshotRepository;
import com.coursepilot.verifier.web.dto.SnapshotDtos;
import org.springframework.data.domain.Limit;
import org.springframework.data.domain.Sort;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 契约端点 listCurricula：GET /api/v1/curriculum-snapshots。
 *
 * 这是网关第一屏要的东西——没有它，Web 连培养方案都选不出来，后面的
 * 核对和排课都无从开始（contracts/java.openapi.json、c-agent.md 的网关查询）。
 *
 * 只返回 kind=CURRICULUM 且 state=PUBLISHED。契约 operation summary 是
 * 「列出已发布培养快照」，REJECTED 的快照不能出现在第一屏的可选列表里。
 * 开课快照同表存放但走 listOfferings，混在一起会让调用方误把开课快照当培养方案用。
 *
 * 这里不做任何「看起来可用」的加工：通过过滤的快照的 sourceValidation 原样返回，
 * 由调用方决定要不要用。UNVERIFIED 的快照仍会列出（它是已发布的），但不会
 * 被改写成 VERIFIED（AGENTS.md：unknown 不能通过，也不能自动核验）。
 */
@RestController
@RequestMapping("/api/v1")
public class CurriculumController {

    /** 契约 listCurricula 的 data.items maxItems=200。 */
    private static final int MAX_ITEMS = 200;

    private final CurriculumSnapshotRepository snapshotRepo;
    private final SubjectGuard subjects;

    public CurriculumController(CurriculumSnapshotRepository snapshotRepo, SubjectGuard subjects) {
        this.snapshotRepo = snapshotRepo;
        this.subjects = subjects;
    }

    @GetMapping("/curriculum-snapshots")
    public Envelope<SnapshotDtos.SnapshotList> curricula(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader(value = "X-Subject-Id", required = false) String subjectId) {
        subjects.require(subjectId);

        List<SnapshotDtos.SnapshotSummary> items =
            snapshotRepo.findByKindAndState(CurriculumSnapshot.Kind.CURRICULUM,
                    CurriculumSnapshot.State.PUBLISHED,
                    Sort.by(Sort.Direction.DESC, "createdAt"), Limit.of(MAX_ITEMS))
                .stream().map(SnapshotDtos::of).toList();

        // items 为空是正常业务状态（还没导入任何培养方案），不是错误也不是未知。
        return Envelope.ok(requestId, new SnapshotDtos.SnapshotList(items));
    }
}
