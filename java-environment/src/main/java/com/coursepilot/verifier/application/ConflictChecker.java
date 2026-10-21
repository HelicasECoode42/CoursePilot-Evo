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

        Map<String, CourseOffering> byId = offeringRepo.findAllById(ids).stream()
            .collect(Collectors.toMap(CourseOffering::getOfferingId, Function.identity()));
        List<String> missing = ids.stream().filter(id -> !byId.containsKey(id)).toList();
        if (!missing.isEmpty()) {
            return new ConflictResult(false, true,
                "班次不存在，无法完整核验：" + String.join("、", missing));
        }

        // 按 ids 的顺序建表。早先是按 findAllById 的返回顺序建时间列表，
        // 却用 offeringIds.get(i) 取名字；两个顺序不一致时就会点错班次——
        // 实测把一个时间待定、根本不可能冲突的班次报成了冲突方。
        Map<String, List<MeetingTime>> meetingsById = new LinkedHashMap<>();
        List<String> unknownReasons = new ArrayList<>();
        for (String id : ids) {
            CourseOffering offering = byId.get(id);
            TimeParser.ParseOutcome outcome = timeParser.parse(offering.getMeetingTextRaw());
            if (outcome.isOk()) {
                meetingsById.put(id, outcome.getMeetings());
            } else {
                // 解析不出来就是未知，不能当成「这门课没有时间所以不冲突」。
                meetingsById.put(id, List.of());
                unknownReasons.add("班次 " + id + " 时间无法解析：" + outcome.getReason());
            }
        }

        List<String> conflicts = new ArrayList<>();
        for (int i = 0; i < ids.size(); i++) {
            for (int j = i + 1; j < ids.size(); j++) {
                if (overlaps(meetingsById.get(ids.get(i)), meetingsById.get(ids.get(j)))) {
                    // 一对只报一次，哪怕它们有多个时间段同时相撞。
                    conflicts.add("班次 " + ids.get(i) + " 与 " + ids.get(j) + " 时间冲突");
                }
            }
        }

        if (!conflicts.isEmpty()) {
            return new ConflictResult(true, !unknownReasons.isEmpty(),
                String.join("；", conflicts));
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
