package com.coursepilot.verifier.web;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
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

    /**
     * 路径写法差异不能绕过密钥校验。
     *
     * 这组是真实故障的回归：早先 ServiceKeyFilter 用
     * getRequestURI().startsWith("/api/v1/") 决定要不要校验，而
     * /api/v1;x=1/courses 的原始路径带着分号后的矩阵变量，不匹配前缀于是
     * 跳过校验，Spring 的路径匹配却会剥掉这段照样路由到控制器。结果不带
     * 密钥、只自报 X-Subject-Id 就能读到任意主体的缺口与完整核对结果。
     *
     * 现在过滤器不按路径开豁免口，这些写法一律 401。
     */
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
        // 刻意只自报身份、不带密钥：这正是绕过时用的请求。
        mvc.perform(get(path).header(SUBJECT, "S001"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("分号路径 + 自报身份读不到任何学业数据")
    void semicolonPathLeaksNothing() throws Exception {
        mvc.perform(get("/api/v1;x=1/verification/credit-gap?planId=PLAN_CS_2025")
                .header(SUBJECT, "S001"))
            .andExpect(status().isUnauthorized())
            // 绕过时这里会出现「还差 N 学分」。
            .andExpect(content().string(org.hamcrest.Matchers.not(
                org.hamcrest.Matchers.containsString("学分"))))
            .andExpect(jsonPath("$.data").value(org.hamcrest.Matchers.nullValue()));
    }

    @Test
    @DisplayName("H2 控制台不对外开放，不能绕过授权直接跑 SQL")
    void h2ConsoleIsDisabled() throws Exception {
        mvc.perform(get("/h2-console")).andExpect(status().is4xxClientError());
    }
}
