package com.coursepilot.verifier.web;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot;
import com.coursepilot.verifier.persistence.repo.CurriculumSnapshotRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

/**
 * POST /api/v1/offering-snapshots/import 与 GET /api/v1/offerings 的端到端测试。
 * 每个用例使用独立的班次编号前缀，避免共享同一个内存库时互相冲突。
 */
@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:h2:mem:offering-import-http;DB_CLOSE_DELAY=-1",
    "spring.jpa.hibernate.ddl-auto=create-drop",
    "coursepilot.service-key=test-service-key",
    "coursepilot.admin-key=test-admin-key",
    "coursepilot.import.synthetic.enabled=true"
})
@AutoConfigureMockMvc
class OfferingImportEndpointTest {

    private static final String SERVICE = "X-Service-Key";
    private static final String SUBJECT = "X-Subject-Id";
    private static final String ADMIN = "X-Admin-Key";
    private static final String GOOD_SERVICE = "test-service-key";
    private static final String GOOD_ADMIN = "test-admin-key";

    @Autowired private MockMvc mvc;
    @Autowired private ObjectMapper json;
    @Autowired private CurriculumSnapshotRepository snapshots;

    // ------------------------------------------------------------ helpers

    private static String offering(String classId, String courseCode, String teacherText, String raw, String claimed) {
        return """
            {"courseCode":"%s","classId":"%s","teacherKey":null,"teacherText":"%s","credits":3,"capacity":60,
             "meetingTextRaw":"%s","meetings":[{"dayOfWeek":5,"sectionStart":1,"sectionEnd":2,"weeks":[1]}],
             "parseStatus":"%s","sourceRefId":"src:%s"}
            """.formatted(courseCode, classId, teacherText, raw, claimed, classId);
    }

    private static String importBody(String termId, String sourceKind, String... offerings) {
        return """
            {"schemaVersion":"1.0","termId":"%s","sourceKind":"%s","capturedAt":"2026-10-01T08:00:00Z",
             "calendar":{"weeks":16,"sectionsPerDay":12},"offerings":[%s]}
            """.formatted(termId, sourceKind, String.join(",", offerings));
    }

    private MvcResult importAs(String body, String adminKey) throws Exception {
        MockHttpServletRequestBuilder req = post("/api/v1/offering-snapshots/import")
            .header(SERVICE, GOOD_SERVICE).header(SUBJECT, "S001").header("X-Request-Id", "req-offer-1")
            .contentType(MediaType.APPLICATION_JSON).content(body);
        if (adminKey != null) req.header(ADMIN, adminKey);
        return mvc.perform(req).andReturn();
    }

    private JsonNode data(MvcResult r) throws Exception {
        return json.readTree(r.getResponse().getContentAsString()).get("data");
    }

    /** ImportResult.issues 在 data 里，不是信封顶层。 */
    private JsonNode issues(MvcResult r) throws Exception {
        return data(r).get("issues");
    }

    private MvcResult query(String offeringSnapshotId, String courseCode) throws Exception {
        var req = get("/api/v1/offerings").param("curriculumSnapshotId", "PLAN_CS_2025")
            .param("offeringSnapshotId", offeringSnapshotId)
            .header(SERVICE, GOOD_SERVICE).header(SUBJECT, "S001");
        if (courseCode != null) req.param("courseCode", courseCode);
        return mvc.perform(req).andReturn();
    }

    private MvcResult query(String offeringSnapshotId, String courseCode, String limit) throws Exception {
        var req = get("/api/v1/offerings").param("curriculumSnapshotId", "PLAN_CS_2025")
            .param("offeringSnapshotId", offeringSnapshotId)
            .header(SERVICE, GOOD_SERVICE).header(SUBJECT, "S001");
        if (courseCode != null) req.param("courseCode", courseCode);
        if (limit != null) req.param("limit", limit);
        return mvc.perform(req).andReturn();
    }

    private static String item(String courseCode, String classId) {
        return "{\"courseCode\":\"%s\",\"teacherKey\":null,\"classId\":\"%s\"}".formatted(courseCode, classId);
    }

    private MvcResult validateSimulation(String offeringSnapshotId, String items) throws Exception {
        String body = """
            {"schemaVersion":"1.0","curriculumSnapshotId":"PLAN_CS_2025","offeringSnapshotId":"%s",
             "academicRecordId":"S001","mode":"SIMULATION","items":[%s],"hardConstraints":[]}
            """.formatted(offeringSnapshotId, items);
        return mvc.perform(post("/api/v1/plans/validate").header(SERVICE, GOOD_SERVICE).header(SUBJECT, "S001")
            .contentType(MediaType.APPLICATION_JSON).content(body)).andReturn();
    }

    // ------------------------------------------------------------ auth

    @Test
    void rejectsMissingServiceKeyAndMissingOrWrongAdminKey() throws Exception {
        String body = importBody("2026-AUTH", "BROWSER_SNAPSHOT", offering("AUTH_01", "CS101", "陈老师", "周一第1-2节{第1-16周}", "PARSED"));
        mvc.perform(post("/api/v1/offering-snapshots/import").header(SUBJECT, "S001").header("X-Request-Id", "r1")
                .contentType(MediaType.APPLICATION_JSON).content(body))
            .andExpect(status().isUnauthorized());
        assertEquals(401, importAs(body, null).getResponse().getStatus());
        var wrong = importAs(body, "not-the-key");
        assertEquals(401, wrong.getResponse().getStatus());
        assertEquals("ADMIN_KEY_INVALID", json.readTree(wrong.getResponse().getContentAsString())
            .get("issues").get(0).get("code").asText());
        assertEquals(0, snapshots.findAll().stream().filter(s -> s.getTermId() != null && s.getTermId().equals("2026-AUTH")).count());
    }

    // ------------------------------------------------------------ happy path, query back, idempotency

    @Test
    void importsOfferingSnapshotQueryableByItsId() throws Exception {
        String body = importBody("2026-HAPPY", "BROWSER_SNAPSHOT",
            offering("HAPPY_CS101", "CS101", "陈老师", "周二第3-4节{第1-16周}", "PARSED"),
            offering("HAPPY_CS102", "CS102", "刘老师", "时间待定", "PARSED"));
        MvcResult first = importAs(body, GOOD_ADMIN);
        assertEquals(200, first.getResponse().getStatus());
        JsonNode d = data(first);
        assertEquals("PUBLISHED", d.get("state").asText());
        assertFalse(d.get("reused").asBoolean());
        String snapshotId = d.get("snapshotId").asText();
        assertTrue(snapshotId.startsWith("OFS_") && snapshotId.length() == 64, snapshotId);

        CurriculumSnapshot stored = snapshots.findById(snapshotId).orElseThrow();
        assertEquals(CurriculumSnapshot.Kind.OFFERING, stored.getKind());
        assertEquals(CurriculumSnapshot.SourceKind.BROWSER_SNAPSHOT, stored.getSourceKind());
        assertEquals(CurriculumSnapshot.SourceValidation.UNVERIFIED, stored.getSourceValidation());
        assertEquals(16, stored.getCalendarWeeks());
        assertEquals(12, stored.getSectionsPerDay());

        // 上传者的 BROWSER_SNAPSHOT 不能自动核验；列表里看到的也是 UNVERIFIED。
        mvc.perform(get("/api/v1/offering-snapshots").header(SERVICE, GOOD_SERVICE).header(SUBJECT, "S001"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.items[?(@.snapshotId=='" + snapshotId + "')].sourceValidation").value(org.hamcrest.Matchers.contains("UNVERIFIED")));

        JsonNode items = json.readTree(query(snapshotId, null).getResponse().getContentAsString()).get("data").get("items");
        assertEquals(2, items.size());
        JsonNode cs101 = find(items, "HAPPY_CS101");
        assertEquals("PARSED", cs101.get("parseStatus").asText());
        assertEquals("陈老师", cs101.get("teacherText").asText());
        assertEquals(2, cs101.get("meetings").get(0).get("dayOfWeek").asInt());
        assertEquals("src:HAPPY_CS101", cs101.get("sourceRefId").asText());
        assertEquals("UNPARSED", find(items, "HAPPY_CS102").get("parseStatus").asText());
        assertEquals(0, find(items, "HAPPY_CS102").get("meetings").size());

        JsonNode byCourse = json.readTree(query(snapshotId, "CS101").getResponse().getContentAsString()).get("data").get("items");
        assertEquals(1, byCourse.size());
        assertEquals("HAPPY_CS101", byCourse.get(0).get("classId").asText());
    }

    @Test
    void sameContentReimportIsIdempotentAndOrderInsensitive() throws Exception {
        String a = offering("IDEM_01", "CS101", "陈老师", "周一第1-2节{第1-16周}", "PARSED");
        String b = offering("IDEM_02", "CS102", "刘老师", "周四第1-2节{第1-16周}", "PARSED");
        JsonNode first = data(importAs(importBody("2026-IDEM", "BROWSER_SNAPSHOT", a, b), GOOD_ADMIN));
        MvcResult again = importAs(importBody("2026-IDEM", "BROWSER_SNAPSHOT", b, a), GOOD_ADMIN);
        assertEquals(200, again.getResponse().getStatus());
        JsonNode second = data(again);
        assertEquals(first.get("snapshotId").asText(), second.get("snapshotId").asText());
        assertTrue(second.get("reused").asBoolean());
        JsonNode items = json.readTree(query(first.get("snapshotId").asText(), null).getResponse().getContentAsString())
            .get("data").get("items");
        assertEquals(2, items.size());
    }

    // ------------------------------------------------------------ parsing and claims

    @Test
    void unparseableTextIsKeptAsUnknownAndClientClaimsAreNotTrusted() throws Exception {
        MvcResult r = importAs(importBody("2026-CLAIM", "BROWSER_SNAPSHOT",
            offering("CLAIM_01", "CS103", "王老师", "这不是时间", "PARSED")), GOOD_ADMIN);
        assertEquals(200, r.getResponse().getStatus());
        String snapshotId = data(r).get("snapshotId").asText();
        assertTrue(hasIssue(issues(r), "CLIENT_PARSE_STATUS_IGNORED"));
        assertTrue(hasIssue(issues(r), "MEETING_TEXT_UNPARSED"));
        JsonNode stored = find(json.readTree(query(snapshotId, null).getResponse().getContentAsString())
            .get("data").get("items"), "CLAIM_01");
        assertEquals("UNPARSED", stored.get("parseStatus").asText());
        assertEquals(0, stored.get("meetings").size());
    }

    @Test
    void sourceValidationCannotBeClaimedByThePayload() throws Exception {
        String body = importBody("2026-CLAIM2", "BROWSER_SNAPSHOT",
            offering("CLAIM2_01", "CS101", "陈老师", "周一第1-2节{第1-16周}", "PARSED"))
            .replace("\"offerings\"", "\"sourceValidation\":\"VERIFIED\",\"offerings\"");
        assertEquals(400, importAs(body, GOOD_ADMIN).getResponse().getStatus());
        assertEquals(0, snapshots.findAll().stream().filter(s -> "2026-CLAIM2".equals(s.getTermId())).count());
    }

    @Test
    void unknownCourseCodeIsAcceptedWithIssue() throws Exception {
        MvcResult r = importAs(importBody("2026-UNK", "BROWSER_SNAPSHOT",
            offering("UNK_01", "NOPE999", "陈老师", "周一第1-2节{第1-16周}", "PARSED")), GOOD_ADMIN);
        assertEquals(200, r.getResponse().getStatus());
        assertTrue(hasIssue(issues(r), "COURSE_NOT_IN_CATALOG"));
    }

    // ------------------------------------------------------------ rejects

    @Test
    void rejectsSchemaViolationsDuplicatesAndIdCollisions() throws Exception {
        String missingField = importBody("2026-BAD", "BROWSER_SNAPSHOT",
            offering("BAD_01", "CS101", "陈老师", "周一第1-2节{第1-16周}", "PARSED")).replace("\"calendar\"", "\"calendarX\"");
        assertEquals(400, importAs(missingField, GOOD_ADMIN).getResponse().getStatus());

        String dup = importBody("2026-DUP", "BROWSER_SNAPSHOT",
            offering("DUP_01", "CS101", "陈老师", "周一第1-2节{第1-16周}", "PARSED"),
            offering("DUP_01", "CS102", "刘老师", "周二第1-2节{第1-16周}", "PARSED"));
        assertEquals(422, importAs(dup, GOOD_ADMIN).getResponse().getStatus());

        // 班次编号 O_CS101_01 已是种子数据的班次，不能被另一快照覆盖。
        String collide = importBody("2026-COL", "BROWSER_SNAPSHOT",
            offering("O_CS101_01", "CS101", "陈老师", "周一第1-2节{第1-16周}", "PARSED"));
        MvcResult r = importAs(collide, GOOD_ADMIN);
        assertEquals(409, r.getResponse().getStatus());
        assertEquals("CLASS_ID_CONFLICT", json.readTree(r.getResponse().getContentAsString())
            .get("issues").get(0).get("code").asText());
    }

    // ------------------------------------------------------------ plan validation with imported SYNTHETIC

    @Test
    void simulationOverImportedSyntheticOfferingsChecksConflicts() throws Exception {
        String synthetic = importBody("2026-SIM", "SYNTHETIC",
            offering("SIM_CS201_FRI", "CS201", "陈老师", "周五第5-6节{第1-16周}", "PARSED"),
            offering("SIM_CS101_MON", "CS101", "张老师", "周一第5-6节{第1-16周}", "PARSED"),
            offering("SIM_CS102_FRI", "CS102", "李老师", "周五第5-6节{第1-16周}", "PARSED"));
        MvcResult imported = importAs(synthetic, GOOD_ADMIN);
        assertEquals(200, imported.getResponse().getStatus());
        String snapshotId = data(imported).get("snapshotId").asText();
        assertEquals(CurriculumSnapshot.SourceValidation.SYNTHETIC,
            snapshots.findById(snapshotId).orElseThrow().getSourceValidation());

        JsonNode ok = data(validateSimulation(snapshotId,
            item("CS201", "SIM_CS201_FRI") + "," + item("CS101", "SIM_CS101_MON")));
        assertEquals("SIMULATION", ok.get("scope").asText());
        assertEquals("VALID", ok.get("verdict").asText());

        JsonNode clash = data(validateSimulation(snapshotId,
            item("CS201", "SIM_CS201_FRI") + "," + item("CS102", "SIM_CS102_FRI")));
        assertEquals("SIMULATION", clash.get("scope").asText());
        assertEquals("INVALID", clash.get("verdict").asText());
        assertEquals("TIME_CONFLICT", clash.get("violations").get(0).get("code").asText());
    }

    // ------------------------------------------------------------ helpers

    private static JsonNode find(JsonNode items, String classId) {
        for (JsonNode n : items) if (classId.equals(n.get("classId").asText())) return n;
        throw new AssertionError("missing " + classId);
    }

    @Test
    void courseQueryReturnsEverySectionOfOneCourseBeyondOneHundred() throws Exception {
        // 186 sections for one course (real snapshot has up to 186) and 106 for another.
        StringBuilder rows = new StringBuilder();
        for (int i = 0; i < 186; i++) {
            if (i > 0) rows.append(',');
            rows.append(offering("MANY_A_%03d".formatted(i), "BIGA01", "陈老师", "周一第1-2节{第1-16周}", "PARSED"));
        }
        for (int i = 0; i < 106; i++) {
            rows.append(',').append(offering("MANY_B_%03d".formatted(i), "BIGB01", "刘老师", "周二第3-4节{第1-16周}", "PARSED"));
        }
        String body = """
            {"schemaVersion":"1.0","termId":"2026-MANY","sourceKind":"BROWSER_SNAPSHOT","capturedAt":"2026-10-01T08:00:00Z",
             "calendar":{"weeks":16,"sectionsPerDay":12},"offerings":[%s]}
            """.formatted(rows);
        MvcResult imported = importAs(body, GOOD_ADMIN);
        assertEquals(200, imported.getResponse().getStatus());
        String snapshotId = data(imported).get("snapshotId").asText();

        MvcResult all = query(snapshotId, "BIGA01", "1000");
        assertEquals(200, all.getResponse().getStatus());
        JsonNode items = json.readTree(all.getResponse().getContentAsString()).get("data").get("items");
        assertEquals(186, items.size());
        var classIds = new java.util.HashSet<String>();
        items.forEach(n -> classIds.add(n.get("classId").asText()));
        assertEquals(186, classIds.size());

        MvcResult courseDefault = query(snapshotId, "BIGB01", null);
        assertEquals(106, json.readTree(courseDefault.getResponse().getContentAsString())
            .get("data").get("items").size());

        // Without a courseCode the cap stays at 100 and the default stays at 20.
        MvcResult unfilteredDefault = query(snapshotId, null, null);
        assertEquals(20, json.readTree(unfilteredDefault.getResponse().getContentAsString())
            .get("data").get("items").size());
        MvcResult unfilteredTooBig = query(snapshotId, null, "101");
        assertEquals(400, unfilteredTooBig.getResponse().getStatus());
    }

    private static boolean hasIssue(JsonNode issues, String code) {
        for (JsonNode n : issues) if (code.equals(n.get("code").asText())) return true;
        return false;
    }
}
