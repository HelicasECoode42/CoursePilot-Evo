package com.coursepilot.verifier.web;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * listCurricula（GET /api/v1/curriculum-snapshots）的契约与真实性回归。
 */
@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
    "coursepilot.service-key=test-key",
    "spring.datasource.url=jdbc:h2:mem:curriculumtest;DB_CLOSE_DELAY=-1"
})
class CurriculumControllerTest {

    private static final String KEY = "X-Service-Key";
    private static final String SUBJECT = "X-Subject-Id";

    @Autowired
    private MockMvc mvc;

    @Test
    @DisplayName("data 是 { items: [...] } 而不是裸数组，字段齐全且是契约枚举值")
    void returnsContractShape() throws Exception {
        mvc.perform(get("/api/v1/curriculum-snapshots").header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("OK"))
            .andExpect(jsonPath("$.data.items").isArray())
            .andExpect(jsonPath("$.data.items[0].snapshotId").value("PLAN_CS_2025"))
            .andExpect(jsonPath("$.data.items[0].kind").value("CURRICULUM"))
            .andExpect(jsonPath("$.data.items[0].state").value("PUBLISHED"))
            .andExpect(jsonPath("$.data.items[0].sourceKind").value("SYNTHETIC"))
            .andExpect(jsonPath("$.data.items[0].sourceValidation").value("SYNTHETIC"))
            // 契约允许 termId 为 null，但 required 列了它，所以键必须在、值为 null，
            // 不能把字段整个省掉。
            .andExpect(jsonPath("$.data.items[0].termId").hasJsonPath())
            .andExpect(jsonPath("$.data.items[0].termId").value(org.hamcrest.Matchers.nullValue()))
            .andExpect(jsonPath("$.data.items[0].createdAt").value("2025-09-01T00:00:00Z"));
    }

    @Test
    @DisplayName("最新的快照在前")
    void newestFirst() throws Exception {
        mvc.perform(get("/api/v1/curriculum-snapshots").header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(jsonPath("$.data.items[0].snapshotId").value("PLAN_CS_2025"))
            .andExpect(jsonPath("$.data.items[1].snapshotId").value("PLAN_CS_2024"));
    }

    @Test
    @DisplayName("只列培养方案，不把开课快照混进来")
    void offeringSnapshotsAreNotListed() throws Exception {
        mvc.perform(get("/api/v1/curriculum-snapshots").header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(jsonPath("$.data.items.length()").value(2))
            .andExpect(jsonPath("$.data.items[?(@.snapshotId=='OFFER_2025_FALL')]").isEmpty());
    }

    @Test
    @DisplayName("自称 BROWSER_SNAPSHOT 的快照不会自动变 VERIFIED")
    void claimedBrowserSnapshotStaysUnverified() throws Exception {
        // AGENTS.md：上传者提供 BROWSER_SNAPSHOT 标签不能使 sourceValidation 自动 VERIFIED。
        mvc.perform(get("/api/v1/curriculum-snapshots").header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(jsonPath("$.data.items[1].sourceKind").value("BROWSER_SNAPSHOT"))
            .andExpect(jsonPath("$.data.items[1].sourceValidation").value("UNVERIFIED"));
    }

    @Test
    @DisplayName("没有服务密钥读不到快照列表")
    void requiresServiceKey() throws Exception {
        mvc.perform(get("/api/v1/curriculum-snapshots").header(SUBJECT, "S001"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("没有主体身份读不到快照列表")
    void requiresSubject() throws Exception {
        mvc.perform(get("/api/v1/curriculum-snapshots").header(KEY, "test-key"))
            .andExpect(status().isBadRequest());
    }
}
