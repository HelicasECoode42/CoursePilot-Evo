package com.coursepilot.verifier.web;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

/**
 * 契约封套形状回归：listCourses / listOfferings 的 data 必须是 {items: [...]}，
 * 不是裸数组；每条记录只含契约字段，不泄漏实体字段（offeringId/teacher/sourceKind）。
 */
@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
    "coursepilot.service-key=test-key",
    "spring.datasource.url=jdbc:h2:mem:catalogenvelope;DB_CLOSE_DELAY=-1"
})
class CatalogEnvelopeTest {

    @Autowired
    private MockMvc mvc;

    @Test
    @DisplayName("GET /courses：按已发布快照返回课程和分页游标")
    void coursesEnvelope() throws Exception {
        mvc.perform(get("/api/v1/courses").param("curriculumSnapshotId", "PLAN_CS_2025")
                .header("X-Service-Key", "test-key").header("X-Subject-Id", "S001"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("OK"))
            .andExpect(jsonPath("$.data").isMap())
            .andExpect(jsonPath("$.data.items").isArray())
            .andExpect(jsonPath("$.data.nextCursor").value(org.hamcrest.Matchers.nullValue()))
            .andExpect(jsonPath("$.data.items[?(@.courseCode=='CS101')].sourceRefIds[0]")
                .value("synthetic:PLAN_CS_2025:CS101"))
            .andExpect(jsonPath("$.data.items[?(@.courseCode=='CS103')].credits").value(org.hamcrest.Matchers.contains((Object) null)))
            .andExpect(jsonPath("$.data.items[0].sourceRefIds").isArray())
            .andExpect(jsonPath("$.provenance[0].kind").value("SYNTHETIC"))
            .andExpect(jsonPath("$.provenance[0].snapshotId").value("PLAN_CS_2025"))
            .andExpect(jsonPath("$.provenance[0].locator").value("synthetic seed course CS101"));
    }

    @Test
    @DisplayName("GET /offerings：data 为 {items}，映射 classId/teacherText/parseStatus/meetings，无实体残留字段")
    void offeringsEnvelope() throws Exception {
        mvc.perform(get("/api/v1/offerings").param("courseCode", "CS101").header("X-Service-Key", "test-key"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data").isMap())
            .andExpect(jsonPath("$.data.items").isArray())
            .andExpect(jsonPath("$.data.items[0].classId").value("O_CS101_01"))
            .andExpect(jsonPath("$.data.items[0].teacherText").value("张老师"))
            .andExpect(jsonPath("$.data.items[0].teacherKey").doesNotExist())
            .andExpect(jsonPath("$.data.items[0].parseStatus").value("PARSED"))
            .andExpect(jsonPath("$.data.items[0].meetings[0].dayOfWeek").value(1))
            .andExpect(jsonPath("$.data.items[0].meetings[0].sectionStart").value(1))
            .andExpect(jsonPath("$.data.items[0].meetings[0].sectionEnd").value(2))
            .andExpect(jsonPath("$.data.items[0].meetings[0].weeks[0]").value(1))
            .andExpect(jsonPath("$.data.items[0].sourceRefId").value("offering:O_CS101_01"))
            .andExpect(jsonPath("$.data.items[0].offeringId").doesNotExist())
            .andExpect(jsonPath("$.data.items[0].teacher").doesNotExist())
            .andExpect(jsonPath("$.data.items[0].sourceKind").doesNotExist());
    }

    @Test
    @DisplayName("GET /offerings：时间待定的班次为 UNPARSED 且 meetings 为空")
    void unparsedOfferingIsMarked() throws Exception {
        mvc.perform(get("/api/v1/offerings").param("courseCode", "CS103").header("X-Service-Key", "test-key"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.items[0].classId").value("O_CS103_01"))
            .andExpect(jsonPath("$.data.items[0].parseStatus").value("UNPARSED"))
            .andExpect(jsonPath("$.data.items[0].meetings").isEmpty());
    }
}
