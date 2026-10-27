package com.coursepilot.verifier.web;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
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
            .andExpect(jsonPath("$.issues[0].code").value("SERVICE_KEY_INVALID")); // 修正 code
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
        mvc.perform(get("/api/v1/academic-records?studentId=S001")
                .header(KEY, "test-key").header(SUBJECT, "S999"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data").isArray())
            .andExpect(content().string(org.hamcrest.Matchers.not(
                org.hamcrest.Matchers.containsString("studentId"))));
    }

    @Test
    @DisplayName("读别人的学业记录：S999 没有数据，返回空列表")
    void otherSubjectsRecordIsNotVisible() throws Exception {
        // 远端原测试是 GET /academic-records/S001，但现在的接口是按 Header 过滤列表
        mvc.perform(get("/api/v1/academic-records")
                .header(KEY, "test-key").header(SUBJECT, "S999"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data").isArray())
            .andExpect(jsonPath("$.data.length()").value(0));
    }

    @Test
    @DisplayName("读自己的学业记录：放行，返回对应数据")
    void ownRecordIsVisible() throws Exception {
        mvc.perform(get("/api/v1/academic-records")
                .header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data").isArray())
            .andExpect(jsonPath("$.data.length()").value(1)); // SeedData 里 S001 有一条记录
    }

    @Test
    @DisplayName("核对别人的记录：返回 UNKNOWN 越权拦截，拿不到对方的已修课程清单")
    void auditOfOtherSubjectIsRejected() throws Exception {
        String body = """
            {"schemaVersion":"1.0","curriculumSnapshotId":"PLAN_CS_2025","academicRecordId":"REC-2026-001"}
            """;
        mvc.perform(post("/api/v1/requirements/audit")
                .header(KEY, "test-key").header(SUBJECT, "S999")
                .contentType(MediaType.APPLICATION_JSON).content(body))
            .andExpect(status().isOk()) // 越权拦截目前通过 Envelope.unknown 返回，状态码为 200
            .andExpect(jsonPath("$.status").value("UNKNOWN"))
            .andExpect(jsonPath("$.issues[0].message").value("越权拦截"));
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

    @ParameterizedTest(name = "[{index}] {0} 必须 401")
    @ValueSource(strings = {
        "/api/v1/courses",
        "/api/v1;x=1/courses",
        "/api/v1;x=1/academic-records/S001",
        "/api/v1;x=1/verification/credit-gap?planId=PLAN_CS_2025",
        "/api/v1/courses;x=1",
        "/./api/v1/courses",
        "/foo/../api/v1/courses",
        "/api/v1/./courses",
        "/api/v1/cour%73es",
        "/api/v1/courses/",
    })
    @DisplayName("路径写法差异不能绕过密钥校验")
    void pathVariantsCannotBypassServiceKey(String path) throws Exception {
        mvc.perform(get(path).header(SUBJECT, "S001"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("分号路径 + 自报身份读不到任何学业数据")
    void semicolonPathLeaksNothing() throws Exception {
        mvc.perform(get("/api/v1;x=1/verification/credit-gap?planId=PLAN_CS_2025")
                .header(SUBJECT, "S001"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("H2 控制台不对外开放，不能绕过授权直接跑 SQL")
    void h2ConsoleIsDisabled() throws Exception {
        mvc.perform(get("/h2-console")).andExpect(status().is4xxClientError());
    }
}
