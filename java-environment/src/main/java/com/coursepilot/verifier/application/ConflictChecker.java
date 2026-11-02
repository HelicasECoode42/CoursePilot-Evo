package com.coursepilot.verifier.application;

import com.coursepilot.verifier.domain.ConflictResult;
import com.coursepilot.verifier.domain.MeetingTime;
import com.coursepilot.verifier.persistence.entity.CourseOffering;
import com.coursepilot.verifier.persistence.repo.CourseOfferingRepository;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class ConflictChecker {

    private final CourseOfferingRepository offeringRepo;
    private final TimeParser timeParser;

    public ConflictChecker(CourseOfferingRepository offeringRepo, TimeParser timeParser) {
        this.offeringRepo = offeringRepo;
        this.timeParser = timeParser;
    }

    /** 一对相撞的班次，按入参顺序（左在前）。 */
    public record ConflictPair(String leftId, String rightId) {}

    /**
     * 一次分析得到的全部事实：班次快照、时间解析结果、相撞的班次对。
     * check() 与计划核验（PlanValidationService）共用它，所以时间只经 TimeParser 解析一次，
     * 冲突判断也只写在这一处。
     */
    public static final class Analysis {
        private final Map<String, CourseOffering> offeringsById;
        private final List<String> missingIds;
        private final Map<String, List<MeetingTime>> meetingsById;
        private final Map<String, String> unparseableReasons;
        private final List<ConflictPair> conflicts;

        Analysis(Map<String, CourseOffering> offeringsById, List<String> missingIds,
                 Map<String, List<MeetingTime>> meetingsById, Map<String, String> unparseableReasons,
                 List<ConflictPair> conflicts) {
            this.offeringsById = offeringsById;
            this.missingIds = missingIds;
            this.meetingsById = meetingsById;
            this.unparseableReasons = unparseableReasons;
            this.conflicts = conflicts;
        }

        /** 库里找到的班次，键为 offeringId。 */
        public Map<String, CourseOffering> offeringsById() { return offeringsById; }
        /** 入参中库里不存在的班次 ID。 */
        public List<String> missingIds() { return missingIds; }
        /** 只含解析成功的班次。时间解析失败的班次不在这里出现。 */
        public Map<String, List<MeetingTime>> meetingsById() { return meetingsById; }
        /** 解析失败的班次 -> 原因。这些班次既不能判冲突，也不能当作「无冲突」。 */
        public Map<String, String> unparseableReasons() { return unparseableReasons; }
        public List<ConflictPair> conflicts() { return conflicts; }
    }

    /**
     * 分析入参班次的时间与冲突明细。去重并保留输入顺序；不做数量判断，
     * 数量与「班次不存在」的文案由 check() 决定，计划核验按自己的规则处理。
     */
    public Analysis analyze(List<String> offeringIds) {
        List<String> ids = offeringIds == null
            ? List.of()
            : new ArrayList<>(new LinkedHashSet<>(offeringIds));

        Map<String, CourseOffering> byId = offeringRepo.findAllById(ids).stream()
            .collect(Collectors.toMap(CourseOffering::getOfferingId, Function.identity()));
        List<String> missing = ids.stream().filter(id -> !byId.containsKey(id)).toList();

        // 按 ids 的顺序建表。早先是按 findAllById 的返回顺序建时间列表，
        // 却用 offeringIds.get(i) 取名字；两个顺序不一致时就会点错班次。
        Map<String, List<MeetingTime>> meetingsById = new LinkedHashMap<>();
        Map<String, String> unparseable = new LinkedHashMap<>();
        for (String id : ids) {
            CourseOffering offering = byId.get(id);
            if (offering == null) continue;
            TimeParser.ParseOutcome outcome = timeParser.parse(offering.getMeetingTextRaw());
            if (outcome.isOk()) {
                meetingsById.put(id, outcome.getMeetings());
            } else {
                // 解析不出来就是未知，不能当成「这门课没有时间所以不冲突」。
                unparseable.put(id, outcome.getReason());
            }
        }

        List<ConflictPair> conflicts = new ArrayList<>();
        for (int i = 0; i < ids.size(); i++) {
            for (int j = i + 1; j < ids.size(); j++) {
                List<MeetingTime> left = meetingsById.get(ids.get(i));
                List<MeetingTime> right = meetingsById.get(ids.get(j));
                // 一对只记一次，哪怕它们有多个时间段同时相撞。
                if (left != null && right != null && overlaps(left, right)) {
                    conflicts.add(new ConflictPair(ids.get(i), ids.get(j)));
                }
            }
        }
        return new Analysis(byId, missing, meetingsById, unparseable, conflicts);
    }

    public ConflictResult check(List<String> offeringIds) {
        if (offeringIds == null || offeringIds.size() < 2) {
            return new ConflictResult(false, true, "至少需要两个班次才能检查冲突");
        }

        // 去重并保留输入顺序。同一个班次传两次不是「班次不存在」——
        // findAllById 会把重复的 ID 合并，早先用 size 比对就会误报成缺数据。
        List<String> ids = new ArrayList<>(new LinkedHashSet<>(offeringIds));
        if (ids.size() < 2) {
            return new ConflictResult(false, true, "去重后不足两个班次，无法检查冲突");
        }

        Analysis analysis = analyze(ids);
        if (!analysis.missingIds().isEmpty()) {
            return new ConflictResult(false, true,
                "班次不存在，无法完整核验：" + String.join("、", analysis.missingIds()));
        }

        List<String> unknownReasons = analysis.unparseableReasons().entrySet().stream()
            .map(e -> "班次 " + e.getKey() + " 时间无法解析：" + e.getValue())
            .toList();
        List<String> conflictTexts = analysis.conflicts().stream()
            .map(p -> "班次 " + p.leftId() + " 与 " + p.rightId() + " 时间冲突")
            .toList();

        if (!conflictTexts.isEmpty()) {
            return new ConflictResult(true, !unknownReasons.isEmpty(),
                String.join("；", conflictTexts));
        }
        if (!unknownReasons.isEmpty()) {
            return new ConflictResult(false, true, String.join("；", unknownReasons));
        }
        return new ConflictResult(false, false, "所有班次时间已知且无冲突");
    }

    private boolean overlaps(List<MeetingTime> left, List<MeetingTime> right) {
        for (MeetingTime a : left) {
            for (MeetingTime b : right) {
                if (a.conflictsWith(b)) return true;
            }
        }
        return false;
    }
}
