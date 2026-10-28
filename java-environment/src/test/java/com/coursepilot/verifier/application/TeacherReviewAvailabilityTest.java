package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.entity.TeacherCourse;
import com.coursepilot.verifier.web.dto.TeacherReviewDtos.Availability;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * availability 判定的纯规则测试。CURRENT_VERIFIED 只在「声明当期 + 来源已核验」时出现。
 */
class TeacherReviewAvailabilityTest {

    @Test
    @DisplayName("当期学期 + 来源已核验才是 CURRENT_VERIFIED")
    void currentVerifiedRequiresTermAndVerifiedSource() {
        assertThat(TeacherReviewAssembler.availability("2025-FALL", TeacherCourse.SourceValidation.VERIFIED, false))
            .isEqualTo(Availability.CURRENT_VERIFIED);
        assertThat(TeacherReviewAssembler.availability("2025-FALL", TeacherCourse.SourceValidation.VERIFIED, true))
            .isEqualTo(Availability.CURRENT_VERIFIED);
    }

    @Test
    @DisplayName("声明了当期但未核验或来自合成数据，不能是 CURRENT_VERIFIED")
    void unverifiedCurrentTermIsNotCurrentVerified() {
        assertThat(TeacherReviewAssembler.availability("2025-FALL", TeacherCourse.SourceValidation.UNVERIFIED, true))
            .isEqualTo(Availability.HISTORICAL_ONLY);
        assertThat(TeacherReviewAssembler.availability("2025-FALL", TeacherCourse.SourceValidation.SYNTHETIC, false))
            .isEqualTo(Availability.UNKNOWN);
    }

    @Test
    @DisplayName("没有当期声明但有历史评价是 HISTORICAL_ONLY，两者都没有是 UNKNOWN")
    void historyWithoutCurrentIsHistoricalOnly() {
        assertThat(TeacherReviewAssembler.availability(null, TeacherCourse.SourceValidation.VERIFIED, true))
            .isEqualTo(Availability.HISTORICAL_ONLY);
        assertThat(TeacherReviewAssembler.availability(null, TeacherCourse.SourceValidation.SYNTHETIC, false))
            .isEqualTo(Availability.UNKNOWN);
    }
}
