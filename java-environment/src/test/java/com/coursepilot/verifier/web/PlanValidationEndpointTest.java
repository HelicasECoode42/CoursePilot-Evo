package com.coursepilot.verifier.web;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.coursepilot.verifier.persistence.entity.Course;
import com.coursepilot.verifier.persistence.entity.CourseOffering;
import com.coursepilot.verifier.persistence.repo.CourseOfferingRepository;
import com.coursepilot.verifier.persistence.repo.CourseRepository;
import com.coursepilot.verifier.persistence.repo.TranscriptRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

/**
 * POST /api/v1/plans/validate 的端到端测试。
 *
 * 种子数据（SeedData）：CS101 3 学分 周一第1-2节，CS102 4 学分 周一第2-3节（与 CS101 相撞），
 * CS103 学分未知且时间待定；学业记录 S001 已修 CS101/CS102/GE101。
 * 本类另外补：CS201（3 学分，S001 未修）、周五班次，以及一个非 SYNTHETIC 的班次。
 */
@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
    "coursepilot.service-key=test-key",
    "spring.datasource.url=jdbc:h2:mem:plantest;DB_CLOSE_DELAY=-1"
})
class PlanValidationEndpointTest {

    private static final String KEY = "X-Service-Key";
    private static final String SUBJECT = "X-Subject-Id";
    private static final String OWNER = "S001";

    @Autowired private MockMvc mvc;
    @Autowired private ObjectMapper json;
    @Autowired private CourseOfferingRepository offerings;
    @Autowired private CourseRepository courses;
    @Autowired private TranscriptRepository transcripts;

    @BeforeEach
    void extraFixtures() {
        courses.save(new Course("CS201", "算法设计", 3.0, "必修"));
        offerings.save(new CourseOffering("P_CS201_FRI", "CS201", "陈老师", "周五第5-6节{第1-16周}", "SYNTHETIC"));
        offerings.save(new CourseOffering("P_REAL_MON", "CS101", "张老师", "周一第1-2节{第1-16周}", "BROWSER_SNAPSHOT"));
    }

    // ------------------------------------------------------------- helpers

    private static final String ITEM_CS101 = "{\"courseCode\":\"CS101\",\"teacherKey\":null,\"classId\":\"O_CS101_01\"}";
    private static final String ITEM_CS102 = "{\"courseCode\":\"CS102\",\"teacherKey\":null,\"classId\":\"O_CS102_01\"}";
    private static final String ITEM_CS103 = "{\"courseCode\":\"CS103\",\"teacherKey\":null,\"classId\":\"O_CS103_01\"}";
    private static final String ITEM_CS201 = "{\"courseCode\":\"CS201\",\"teacherKey\":null,\"classId\":\"P_CS201_FRI\"}";

    private static String body(String mode, String record, String items, String constraints) {
        return """
            {"schemaVersion":"1.0","curriculumSnapshotId":"PLAN_CS_2025","offeringSnapshotId":"OFFER_2025_FALL",
             "academicRecordId":"%s","mode":"%s","items":[%s],"hardConstraints":[%s]}
            """.formatted(record, mode, items, constraints);
    }

    private static String block(String kind, Integer day, Integer section, String text) {
        return "{\"kind\":\"%s\",\"courseCode\":null,\"teacherKey\":null,\"dayOfWeek\":%s,\"section\":%s,\"value\":null,\"sourceText\":\"%s\"}"
            .formatted(kind, day == null ? "null" : day, section == null ? "null" : section, text);
    }

    private MvcResult validate(String body) throws Exception {
        return mvc.perform(post("/api/v1/plans/validate")
                .header(KEY, "test-key").header(SUBJECT, OWNER)
                .contentType(MediaType.APPLICATION_JSON).content(body))
            .andReturn();
    }

    private JsonNode data(MvcResult r) throws Exception {
        return json.readTree(r.getResponse().getContentAsString()).get("data");
    }

    private static boolean hasCode(JsonNode list, String code) {
        for (JsonNode n : list) if (code.equals(n.get("code").asText())) return true;
        return false;
    }

    // ------------------------------------------------------------- verdicts

    @Test
    @DisplayName("两门课时间相撞 -> INVALID，violations 点名两门课与两个班次")
    void clashIsInvalidAndNamesBothClasses() throws Exception {
        MvcResult r = validate(body("SIMULATION", OWNER, ITEM_CS101 + "," + ITEM_CS102, ""));
        assertEquals(200, r.getResponse().getStatus());
        JsonNode d = data(r);
        assertEquals("INVALID", d.get("verdict").asText());
        assertEquals("SIMULATION", d.get("scope").asText());
        JsonNode v = d.get("violations");
        assertEquals(1, v.size());
        assertEquals("TIME_CONFLICT", v.get(0).get("code").asText());
        String msg = v.get(0).get("message").asText();
        assertTrue(msg.contains("CS101") && msg.contains("CS102"), msg);
        assertTrue(msg.contains("O_CS101_01") && msg.contains("O_CS102_01"), msg);
    }

    @Test
    @DisplayName("班次时间解析不出来 -> UNKNOWN，不是 VALID")
    void unparseableTimeIsUnknownNotValid() throws Exception {
        MvcResult r = validate(body("SIMULATION", OWNER, ITEM_CS101 + "," + ITEM_CS103, ""));
        JsonNode d = data(r);
        assertEquals("UNKNOWN", d.get("verdict").asText());
        assertEquals("UNKNOWN", json.readTree(r.getResponse().getContentAsString()).get("status").asText());
        assertTrue(hasCode(d.get("unknownChecks"), "TIME_UNPARSEABLE"));
        assertEquals(0, d.get("violations").size());
    }

    @Test
    @DisplayName("mode=REAL -> scope 是 COURSE_ONLY 而不是 REAL_TIMETABLE，时间检查进 unknownChecks")
    void realModeIsCourseOnlyAndTimeGoesToUnknown() throws Exception {
        // CS101 与 CS102 在时间上相撞，但 REAL 没有已验证来源，不能据此判 INVALID，也不能判 VALID。
        MvcResult r = validate(body("REAL", OWNER, ITEM_CS101 + "," + ITEM_CS102, ""));
        JsonNode d = data(r);
        assertEquals("COURSE_ONLY", d.get("scope").asText());
        assertNotEquals("REAL_TIMETABLE", d.get("scope").asText());
        assertEquals("UNKNOWN", d.get("verdict").asText());
        assertEquals(0, d.get("violations").size());
        String msg = null;
        for (JsonNode n : d.get("unknownChecks")) {
            if ("TIMETABLE_UNVERIFIED".equals(n.get("code").asText())) msg = n.get("message").asText();
        }
        assertNotNull(msg, "时间检查必须进 unknownChecks");
        assertTrue(msg.contains("没有已验证来源的班次"), msg);
        for (JsonNode n : d.get("performedChecks")) {
            assertFalse(n.asText().contains("时间冲突核对"), "REAL 不应声称做过时间冲突核对: " + n.asText());
        }
    }

    @Test
    @DisplayName("mode=SIMULATION 但班次非 SYNTHETIC -> 不是 SIMULATION，判 UNKNOWN")
    void nonSyntheticClassIsNotSimulation() throws Exception {
        String item = "{\"courseCode\":\"CS101\",\"teacherKey\":null,\"classId\":\"P_REAL_MON\"}";
        JsonNode d = data(validate(body("SIMULATION", OWNER, item, "")));
        assertEquals("COURSE_ONLY", d.get("scope").asText());
        assertEquals("UNKNOWN", d.get("verdict").asText());
    }

    @Test
    @DisplayName("mode=SIMULATION 且全部 SYNTHETIC、无冲突、检查做完 -> VALID")
    void simulationWithoutConflictIsValid() throws Exception {
        JsonNode d = data(validate(body("SIMULATION", OWNER, ITEM_CS101 + "," + ITEM_CS201, "")));
        assertEquals("SIMULATION", d.get("scope").asText());
        assertEquals("VALID", d.get("verdict").asText());
        assertEquals(0, d.get("violations").size());
        assertEquals(0, d.get("unknownChecks").size());
        assertTrue(d.get("performedChecks").size() > 0);
        assertEquals(transcripts.findByStudentId(OWNER).orElseThrow().getRevision(), d.get("recordRevision").asInt());
    }

    @Test
    @DisplayName("方案里的课没修过不影响判定（CS201 未在学业记录里）")
    void notYetTakenCourseDoesNotBlock() throws Exception {
        JsonNode d = data(validate(body("SIMULATION", OWNER, ITEM_CS201, "")));
        assertEquals("VALID", d.get("verdict").asText());
    }

    @Test
    @DisplayName("每次核验的 verifierResultId 都是新的")
    void verifierResultIdIsFresh() throws Exception {
        String a = data(validate(body("SIMULATION", OWNER, ITEM_CS201, ""))).get("verifierResultId").asText();
        String b = data(validate(body("SIMULATION", OWNER, ITEM_CS201, ""))).get("verifierResultId").asText();
        assertNotEquals(a, b);
    }

    // ------------------------------------------------------------- hard constraints

    @Test
    @DisplayName("BLOCK_DAY 命中 -> INVALID")
    void blockDayHitIsInvalid() throws Exception {
        JsonNode d = data(validate(body("SIMULATION", OWNER, ITEM_CS101, block("BLOCK_DAY", 1, null, "周一不排课"))));
        assertEquals("INVALID", d.get("verdict").asText());
        assertTrue(hasCode(d.get("violations"), "CONSTRAINT_BLOCK_DAY"));
    }

    @Test
    @DisplayName("BLOCK_DAY 未命中 -> VALID")
    void blockDayMissIsValid() throws Exception {
        JsonNode d = data(validate(body("SIMULATION", OWNER, ITEM_CS101, block("BLOCK_DAY", 3, null, "周三不排课"))));
        assertEquals("VALID", d.get("verdict").asText());
    }

    @Test
    @DisplayName("无法验的时间约束 -> 进 unknownChecks，verdict 不是 VALID（REAL 下）")
    void unverifiableConstraintIsNotSilentlyValid() throws Exception {
        JsonNode d = data(validate(body("REAL", OWNER, ITEM_CS201, block("BLOCK_DAY", 3, null, "周三不排课"))));
        assertNotEquals("VALID", d.get("verdict").asText());
        assertEquals("UNKNOWN", d.get("verdict").asText());
        boolean fieldOk = false;
        boolean found = false;
        for (JsonNode n : d.get("unknownChecks")) {
            if ("CONSTRAINT_UNVERIFIABLE".equals(n.get("code").asText())) {
                found = true;
                fieldOk = "hardConstraints[0]".equals(n.get("field").asText());
            }
        }
        assertTrue(found, "约束无法核验必须进 unknownChecks");
        assertTrue(fieldOk, "未知项应指向 hardConstraints[0]");
    }

    @Test
    @DisplayName("方案项未指定班次时，时间类硬约束不能静默通过")
    void nullClassIsUnknownForTimeConstraint() throws Exception {
        String item = "{\"courseCode\":\"CS201\",\"teacherKey\":null,\"classId\":null}";
        JsonNode d = data(validate(body("SIMULATION", OWNER, item, block("BLOCK_DAY", 3, null, "周三不排课"))));
        assertEquals("UNKNOWN", d.get("verdict").asText());
        assertTrue(hasCode(d.get("unknownChecks"), "CONSTRAINT_UNVERIFIABLE"));
    }

    @Test
    @DisplayName("PIN_COURSE：必选课不在方案里 -> INVALID")
    void pinnedCourseMissingIsInvalid() throws Exception {
        String pin = "{\"kind\":\"PIN_COURSE\",\"courseCode\":\"CS201\",\"teacherKey\":null,\"dayOfWeek\":null,\"section\":null,\"value\":null,\"sourceText\":\"必选CS201\"}";
        JsonNode d = data(validate(body("SIMULATION", OWNER, ITEM_CS101, pin)));
        assertEquals("INVALID", d.get("verdict").asText());
        assertTrue(hasCode(d.get("violations"), "PIN_COURSE_MISSING"));
    }

    @Test
    @DisplayName("MAX_CREDITS：已知学分超上限 -> INVALID；刚好等于上限 -> VALID")
    void maxCreditsBoundary() throws Exception {
        // CS101 3 学分 + CS201 3 学分 = 6，两门课时间不冲突
        String over = "{\"kind\":\"MAX_CREDITS\",\"courseCode\":null,\"teacherKey\":null,\"dayOfWeek\":null,\"section\":null,\"value\":5,\"sourceText\":\"最多5学分\"}";
        String exact = over.replace("\"value\":5", "\"value\":6");
        String items = ITEM_CS101 + "," + ITEM_CS201;
        assertEquals("INVALID", data(validate(body("SIMULATION", OWNER, items, over))).get("verdict").asText());
        assertEquals("VALID", data(validate(body("SIMULATION", OWNER, items, exact))).get("verdict").asText());
    }

    @Test
    @DisplayName("MAX_CREDITS 遇到学分未知的课 -> UNKNOWN，不判通过")
    void maxCreditsWithUnknownCreditsIsUnknown() throws Exception {
        String c = "{\"kind\":\"MAX_CREDITS\",\"courseCode\":null,\"teacherKey\":null,\"dayOfWeek\":null,\"section\":null,\"value\":30,\"sourceText\":\"最多30学分\"}";
        JsonNode d = data(validate(body("SIMULATION", OWNER, ITEM_CS103, c)));
        assertEquals("UNKNOWN", d.get("verdict").asText());
        assertTrue(hasCode(d.get("unknownChecks"), "CREDITS_UNKNOWN"));
    }

    // ------------------------------------------------------------- authorization and shape

    @Test
    @DisplayName("别人的 academicRecordId -> 404")
    void otherPeoplesRecordIs404() throws Exception {
        MvcResult r = validate(body("SIMULATION", "S002", ITEM_CS201, ""));
        assertEquals(404, r.getResponse().getStatus());
        assertEquals("NOT_VISIBLE", json.readTree(r.getResponse().getContentAsString())
            .get("issues").get(0).get("code").asText());
    }

    @Test
    @DisplayName("不存在的 curriculumSnapshotId -> 422")
    void unknownCurriculumIs422() throws Exception {
        String b = body("SIMULATION", OWNER, ITEM_CS201, "").replace("PLAN_CS_2025", "NO_SUCH_PLAN");
        assertEquals(422, validate(b).getResponse().getStatus());
    }

    @Test
    @DisplayName("mode 取值非法 -> 400")
    void badModeIs400() throws Exception {
        assertEquals(400, validate(body("FAKE", OWNER, ITEM_CS201, "")).getResponse().getStatus());
    }

    @Test
    @DisplayName("路径不挂在 /verification 下面")
    void notMountedUnderVerification() throws Exception {
        mvc.perform(post("/api/v1/verification/plans/validate")
                .header(KEY, "test-key").header(SUBJECT, OWNER)
                .contentType(MediaType.APPLICATION_JSON).content(body("SIMULATION", OWNER, ITEM_CS201, "")))
            .andExpect(status().isNotFound());
    }

    @Test
    @DisplayName("不存在的学业记录 -> 404")
    void missingRecordIs404() throws Exception {
        mvc.perform(post("/api/v1/plans/validate")
                .header(KEY, "test-key").header(SUBJECT, "NOBODY")
                .contentType(MediaType.APPLICATION_JSON).content(body("SIMULATION", "NOBODY", ITEM_CS201, "")))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.status").value("ERROR"));
    }
}
