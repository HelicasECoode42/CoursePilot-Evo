package com.coursepilot.verifier.web;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.coursepilot.verifier.persistence.entity.Course;
import com.coursepilot.verifier.persistence.repo.CourseRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.ResultActions;

/**
 * 「补录 → 核对」这根线的端到端证明：通过 POST /api/v1/academic-records 写入，
 * 紧接着 POST /api/v1/requirements/audit 必须反映刚写入的内容。
 *
 * 之前的 bug 是写进 transcript、核对读 academic_record，两边断开，这里就是防止它再断开。
 * 种子里 PLAN_CS_2025 的类别是：必修 10 学分、通识 4 学分。
 */
@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
    "coursepilot.service-key=test-key",
    "spring.datasource.url=jdbc:h2:mem:e2etest;DB_CLOSE_DELAY=-1"
})
class AcademicRecordAuditEndToEndTest {

    private static final String KEY = "X-Service-Key";
    private static final String SUBJECT = "X-Subject-Id";
    private static final String IDEM = "Idempotency-Key";
    private static final String STUDENT = "S801";

    @Autowired private MockMvc mvc;
    @Autowired private ObjectMapper json;
    @Autowired private CourseRepository courses;

    @Test
    @DisplayName("补录后立即核对：结果反映刚写入的课程与 revision，再次补录后 revision 递增")
    void auditReflectsWrittenRecord() throws Exception {
        if (!courses.existsById("GE102")) {
            courses.save(new Course("GE102", "通识阅读", 2.0, "通识"));
        }

        // 补录前：没有学业记录，通识 4 学分无法确定，缺口为 null，不能当成确定的 0 或确定的缺口。
        JsonNode before = audit();
        JsonNode general = itemRequiring(before, 4.0);
        assertEquals("UNKNOWN", general.get("state").asText());
        assertEquals(0.0, general.get("earnedCredits").asDouble());
        assertTrue(general.get("gapCredits").isNull(), "无记录时缺口不能是确定数字");

        // 补录：通识 GE101 + GE102 共 4 学分，必修 CS101 + CS102 共 7 学分。
        submit(sampleBody(true)).andExpect(status().isCreated());

        JsonNode after = audit();
        JsonNode generalAfter = itemRequiring(after, 4.0);
        assertEquals("SATISFIED", generalAfter.get("state").asText(),
            "写入的通识课没有反映到核对结果里");
        assertEquals(4.0, generalAfter.get("earnedCredits").asDouble());
        assertEquals(0.0, generalAfter.get("gapCredits").asDouble());

        JsonNode compulsory = itemRequiring(after, 10.0);
        assertEquals("UNSATISFIED", compulsory.get("state").asText());
        assertEquals(7.0, compulsory.get("earnedCredits").asDouble());
        assertEquals(3.0, compulsory.get("gapCredits").asDouble());

        assertEquals(1, after.get("recordRevision").asInt(), "首次补录后 revision 应为 1");
        assertTrue(after.get("transcriptComplete").asBoolean());

        // 第二次补录（新幂等键、内容改为未声明完整）：revision 递增，完整性如实跟随。
        submit(sampleBody(false)).andExpect(status().isCreated());
        JsonNode again = audit();
        assertEquals(2, again.get("recordRevision").asInt(), "再次补录后 revision 应为 2");
        assertFalse(again.get("transcriptComplete").asBoolean());
        assertEquals("SATISFIED", itemRequiring(again, 4.0).get("state").asText());
    }

    private ResultActions submit(String body) throws Exception {
        return mvc.perform(post("/api/v1/academic-records")
                .header(KEY, "test-key").header(SUBJECT, STUDENT)
                .header(IDEM, "k-e2e-" + System.nanoTime())
                .contentType(MediaType.APPLICATION_JSON).content(body));
    }

    /** 核对响应里的 data。未知项会让封套变为 UNKNOWN，但 data 照常返回，这里只读 data。 */
    private JsonNode audit() throws Exception {
        String body = """
            {"schemaVersion":"1.0","curriculumSnapshotId":"PLAN_CS_2025","academicRecordId":"%s"}
            """.formatted(STUDENT);
        MvcResult result = mvc.perform(post("/api/v1/requirements/audit")
                .header(KEY, "test-key").header(SUBJECT, STUDENT)
                .contentType(MediaType.APPLICATION_JSON).content(body))
            .andExpect(status().isOk())
            .andReturn();
        return json.readTree(result.getResponse().getContentAsString()).get("data");
    }

    /** 按 requiredCredits 找要求项：requirementId 是自增主键，类别名是中文，不适合直接定位。 */
    private JsonNode itemRequiring(JsonNode data, double required) {
        for (JsonNode item : data.get("requirements")) {
            if (item.get("requiredCredits").asDouble() == required) {
                return item;
            }
        }
        throw new AssertionError("核对结果里没有 requiredCredits=" + required + " 的要求项");
    }

    private static String sampleBody(boolean transcriptComplete) {
        return """
            {"schemaVersion":"1.0","curriculumSnapshotId":"PLAN_CS_2025",
             "transcriptComplete":%s,"sourceKind":"USER_IMPORT",
             "completedCourses":[
               {"courseCode":"GE101","earnedCredits":2.0,"outcome":"PASSED","completedTerm":"2024-2025-2"},
               {"courseCode":"GE102","earnedCredits":2.0,"outcome":"PASSED","completedTerm":"2024-2025-2"},
               {"courseCode":"CS101","earnedCredits":3.0,"outcome":"PASSED","completedTerm":"2024-2025-1"},
               {"courseCode":"CS102","earnedCredits":4.0,"outcome":"PASSED","completedTerm":"2024-2025-1"}
             ]}
            """.formatted(transcriptComplete);
    }
}
