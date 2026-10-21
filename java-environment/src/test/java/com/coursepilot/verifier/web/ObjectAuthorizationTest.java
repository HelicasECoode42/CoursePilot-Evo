package com.coursepilot.verifier.web;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 对象级授权回归（b-verifier.md B-F6 / B-06）。
 *
 * 这组测试盯的是「越权读」：合并前 GET /api/v1/academic-records?studentId=S001
 * 和 /api/v1/verification/credit-gap?studentId=S001 对任何调用方都可读，
 * 谁都能拿别人的学号读成绩单。这里逐条锁住修好后的行为，防止以后
 * 为了方便又把 studentId 参数加回去。
 */
@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
    "coursepilot.service-key=test-key",
    "spring.datasource.url=jdbc:h2:mem:authtest;DB_CLOSE_DELAY=-1"
})
class ObjectAuthorizationTest {

    private static final String KEY = "X-Service-Key";
    private static final String SUBJECT = "X-Subject-Id";

    @Autowired
    private MockMvc mvc;

    @Test
    @DisplayName("没有服务密钥：401，不是放行")
    void missingServiceKeyIsRejected() throws Exception {
        mvc.perform(get("/api/v1/academic-records").header(SUBJECT, "S001"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.status").value("ERROR"))
            .andExpect(jsonPath("$.issues[0].code").value("SERVICE_KEY_INVALID"));
    }

    @Test
    @DisplayName("服务密钥错误：401")
    void wrongServiceKeyIsRejected() throws Exception {
        mvc.perform(get("/api/v1/academic-records").header(KEY, "nope").header(SUBJECT, "S001"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("401 响应体不回显收到的密钥")
    void rejectionDoesNotEchoTheKey() throws Exception {
        mvc.perform(get("/api/v1/academic-records").header(KEY, "guessed-secret").header(SUBJECT, "S001"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().string(org.hamcrest.Matchers.not(
                org.hamcrest.Matchers.containsString("guessed-secret"))))
            .andExpect(content().string(org.hamcrest.Matchers.not(
                org.hamcrest.Matchers.containsString("test-key"))));
    }

    @Test
    @DisplayName("有密钥但没有主体身份：400，不默认成某个学生")
    void missingSubjectIsRejected() throws Exception {
        mvc.perform(get("/api/v1/academic-records").header(KEY, "test-key"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("INVALID_SUBJECT"));
    }

    @Test
    @DisplayName("学业记录列表不再接受 studentId 参数，传了也只按 X-Subject-Id 定范围")
    void studentIdParamIsIgnored() throws Exception {
        // 原越权写法：带上别人的学号。现在参数无效，范围由主体头决定。
        mvc.perform(get("/api/v1/academic-records?studentId=S001")
                .header(KEY, "test-key").header(SUBJECT, "S999"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.items").isArray())
            // 响应里不能出现归属信息：契约的 AcademicRecord 没有 studentId 字段。
            .andExpect(content().string(org.hamcrest.Matchers.not(
                org.hamcrest.Matchers.containsString("studentId"))));
    }

    @Test
    @DisplayName("读别人的学业记录：404 不可见，不回 403")
    void otherSubjectsRecordIsNotVisible() throws Exception {
        mvc.perform(get("/api/v1/academic-records/S001")
                .header(KEY, "test-key").header(SUBJECT, "S999"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.issues[0].code").value("NOT_VISIBLE"));
    }

    @Test
    @DisplayName("读自己的学业记录：放行")
    void ownRecordIsVisible() throws Exception {
        mvc.perform(get("/api/v1/academic-records/S001")
                .header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(status().isOk());
    }

    @Test
    @DisplayName("核对别人的记录：404，拿不到对方的已修课程清单")
    void auditOfOtherSubjectIsRejected() throws Exception {
        String body = """
            {"schemaVersion":"1.0","curriculumSnapshotId":"PLAN_CS_2025","academicRecordId":"S001"}
            """;
        mvc.perform(post("/api/v1/requirements/audit")
                .header(KEY, "test-key").header(SUBJECT, "S999")
                .contentType(MediaType.APPLICATION_JSON).content(body))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.data").doesNotExist());
    }

    @Test
    @DisplayName("核对自己的记录：照常返回核对结果")
    void auditOfOwnRecordWorks() throws Exception {
        String body = """
            {"schemaVersion":"1.0","curriculumSnapshotId":"PLAN_CS_2025","academicRecordId":"S001"}
            """;
        mvc.perform(post("/api/v1/requirements/audit")
                .header(KEY, "test-key").header(SUBJECT, "S001")
                .contentType(MediaType.APPLICATION_JSON).content(body))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.academicRecordId").value("S001"))
            .andExpect(jsonPath("$.data.requirements").isArray());
    }

    @Test
    @DisplayName("缺口查询也按主体定范围，不接受 studentId 参数")
    void creditGapIsSubjectScoped() throws Exception {
        mvc.perform(get("/api/v1/verification/credit-gap?planId=PLAN_CS_2025&studentId=S001")
                .header(KEY, "test-key").header(SUBJECT, "S999"))
            .andExpect(status().isOk())
            .andExpect(content().string(org.hamcrest.Matchers.not(
                org.hamcrest.Matchers.containsString("\"studentId\""))));
    }

    @Test
    @DisplayName("H2 控制台不对外开放，不能绕过授权直接跑 SQL")
    void h2ConsoleIsDisabled() throws Exception {
        mvc.perform(get("/h2-console")).andExpect(status().is4xxClientError());
    }
}
