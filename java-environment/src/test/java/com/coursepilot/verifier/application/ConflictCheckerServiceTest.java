package com.coursepilot.verifier.application;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.coursepilot.verifier.domain.ConflictResult;
import com.coursepilot.verifier.persistence.entity.CourseOffering;
import com.coursepilot.verifier.persistence.repo.CourseOfferingRepository;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Transactional
class ConflictCheckerServiceTest {

    @Autowired private ConflictChecker checker;
    @Autowired private CourseOfferingRepository offeringRepo;

    private void save(String id, String courseCode, String time) {
        offeringRepo.save(new CourseOffering(id, courseCode, "某老师", time, "SYNTHETIC"));
    }

    @Test
    @DisplayName("报出来的必须是真正相撞的那两个班次")
    void namesTheOfferingsThatActuallyClash() {
        save("O_A", "A", "周一第1-2节{第1-16周}");
        save("O_B", "B", "周一第2-3节{第1-16周}");
        save("O_X", "X", "时间待定");

        ConflictResult result = checker.check(List.of("O_X", "O_A", "O_B"));

        assertTrue(result.hasKnownConflict(), result.getReason());
        assertTrue(result.getReason().contains("O_A") && result.getReason().contains("O_B"),
            "应当点名 O_A 与 O_B，实际：" + result.getReason());
        assertFalse(result.getReason().contains("O_X 与") || result.getReason().contains("与 O_X"),
            "O_X 时间都解析不出来，不可能是冲突方，实际：" + result.getReason());
    }

    @Test
    @DisplayName("同一个班次传两次不算「班次不存在」")
    void duplicateIdIsNotMissingData() {
        save("O_A", "A", "周一第1-2节{第1-16周}");
        ConflictResult result = checker.check(List.of("O_A", "O_A"));
        assertFalse(result.hasKnownConflict());
        assertFalse(result.getReason().contains("不存在"),
            "重复 ID 不该被说成缺数据，实际：" + result.getReason());
    }

    @Test
    @DisplayName("真的缺班次时要说清少的是哪个")
    void missingOfferingIsNamed() {
        save("O_A", "A", "周一第1-2节{第1-16周}");
        ConflictResult result = checker.check(List.of("O_A", "O_NOPE"));
        assertFalse(result.hasKnownConflict());
        assertTrue(result.hasUnknownParticipant());
        assertTrue(result.getReason().contains("O_NOPE"), result.getReason());
    }

    @Test
    @DisplayName("一周上两次的课，第二段相撞也要判出来")
    void secondBlockClashIsDetected() {
        save("O_A", "A", "周一第1-2节{第1-16周},周三第5-6节{第1-16周}");
        save("O_C", "C", "周三第6-7节{第1-16周}");
        ConflictResult result = checker.check(List.of("O_A", "O_C"));
        assertTrue(result.hasKnownConflict(), "周三第 6 节重叠，应当判冲突。实际：" + result.getReason());
    }

    @Test
    @DisplayName("时间解析不出来是未知，不是「不冲突」")
    void unparsableTimeIsUnknownNotConflictFree() {
        save("O_X", "X", "时间待定");
        save("O_A", "A", "周一第1-2节{第1-16周}");
        ConflictResult result = checker.check(List.of("O_X", "O_A"));
        assertFalse(result.hasKnownConflict());
        assertTrue(result.hasUnknownParticipant(), "必须标记存在未知参与者");
    }
}
