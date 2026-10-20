package com.coursepilot.verifier.application;

import com.coursepilot.verifier.domain.ConflictResult;
import com.coursepilot.verifier.domain.MeetingTime;
import com.coursepilot.verifier.persistence.entity.CourseOffering;
import com.coursepilot.verifier.persistence.repo.CourseOfferingRepository;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

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

        List<CourseOffering> offerings = offeringRepo.findAllById(offeringIds);
        if (offerings.size() != offeringIds.size()) {
            return new ConflictResult(false, true, "部分班次不存在，无法完整核验");
        }

        List<List<MeetingTime>> times = new ArrayList<>();
        List<String> unknownReasons = new ArrayList<>();

        for (CourseOffering offering : offerings) {
            TimeParser.ParseOutcome outcome = timeParser.parse(offering.getMeetingTextRaw());
            if (!outcome.isOk()) {
                unknownReasons.add("班次 " + offering.getOfferingId()
                    + " 时间无法解析：" + outcome.getReason());
                times.add(List.of());
            } else {
                times.add(outcome.getMeetings());
            }
        }

        List<String> conflicts = new ArrayList<>();
        for (int i = 0; i < times.size(); i++) {
            for (int j = i + 1; j < times.size(); j++) {
                for (MeetingTime a : times.get(i)) {
                    for (MeetingTime b : times.get(j)) {
                        if (a.conflictsWith(b)) {
                            conflicts.add("班次 " + offeringIds.get(i)
                                + " 与 " + offeringIds.get(j) + " 时间冲突");
                        }
                    }
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
}
