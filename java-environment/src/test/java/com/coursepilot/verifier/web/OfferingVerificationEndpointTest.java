package com.coursepilot.verifier.web;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot;
import com.coursepilot.verifier.persistence.repo.CurriculumSnapshotRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.coursepilot.verifier.persistence.entity.CurriculumUnmodeledRule;
import com.coursepilot.verifier.persistence.entity.Transcript;
import com.coursepilot.verifier.persistence.repo.CurriculumUnmodeledRuleRepository;
import com.coursepilot.verifier.persistence.repo.TranscriptRepository;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

/**
 * POST /api/v1/offering-snapshots/{id}/verification 与 OFFICIAL_DOCUMENT 导入，
 * 以及核验后 REAL 方案核验的 scope。每个用例使用独立的学期与班次编号。
 */
@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:h2:mem:offering-verification-http;DB_CLOSE_DELAY=-1",
    "spring.jpa.hibernate.ddl-auto=create-drop",
    "coursepilot.service-key=test-service-key",
    "coursepilot.admin-key=test-admin-key",
    "coursepilot.import.synthetic.enabled=true"
})
@AutoConfigureMockMvc
class OfferingVerificationEndpointTest {

    private static final String SERVICE = "X-Service-Key";
    private static final String SUBJECT = "X-Subject-Id";
    private static final String ADMIN = "X-Admin-Key";
    private static final String GOOD_SERVICE = "test-service-key";
    private static final String GOOD_ADMIN = "test-admin-key";
    private static final String SHA = "b".repeat(64);

    @Autowired private MockMvc mvc;
    @Autowired private ObjectMapper json;
    @Autowired private CurriculumSnapshotRepository snapshots;

    private static String offering(String classId, String courseCode, String raw) {
        return """
            {"courseCode":"%s","classId":"%s","teacherKey":"teacher:t1","teacherText":"王老师","credits":3,"capacity":60,
             "meetingTextRaw":"%s","meetings":[{"dayOfWeek":5,"sectionStart":1,"sectionEnd":2,"weeks":[1]}],
             "parseStatus":"PARSED","sourceRefId":"src:%s"}
            """.formatted(courseCode, classId, raw, classId);
    }

    private static String importBody(String termId, String sourceKind, String... offerings) {
        return """
            {"schemaVersion":"1.0","termId":"%s","sourceKind":"%s","capturedAt":"2026-11-02T08:00:00Z",
             "calendar":{"weeks":16,"sectionsPerDay":12},"offerings":[%s]}
            """.formatted(termId, sourceKind, String.join(",", offerings));
    }

    private MvcResult importOffering(String body) throws Exception {
        return mvc.perform(post("/api/v1/offering-snapshots/import").header(SERVICE, GOOD_SERVICE)
            .header(SUBJECT, "S001").header("X-Request-Id", "req-vimp").header(ADMIN, GOOD_ADMIN)
            .contentType(MediaType.APPLICATION_JSON).content(body)).andReturn();
    }

    private String snapshotOf(MvcResult r) throws Exception {
        return json.readTree(r.getResponse().getContentAsString()).get("data").get("snapshotId").asText();
    }

    private MvcResult verify(String snapshotId, String body, String adminKey) throws Exception {
        MockHttpServletRequestBuilder req = post("/api/v1/offering-snapshots/" + snapshotId + "/verification")
            .header(SERVICE, GOOD_SERVICE).header(SUBJECT, "S001").header("X-Request-Id", "req-ver-1")
            .contentType(MediaType.APPLICATION_JSON).content(body);
        if (adminKey != null) req.header(ADMIN, adminKey);
        return mvc.perform(req).andReturn();
    }

    private static String request(String verifier, String uploader, int sample, int errors) {
        return """
            {"schemaVersion":"1.0","verifierName":"%s","uploaderName":"%s","sampleSize":%d,
             "errorCount":%d,"sampleFileSha256":"%s","note":"抽样对照官方 PDF"}
            """.formatted(verifier, uploader, sample, errors, SHA);
    }

    private CurriculumSnapshot.SourceValidation validationOf(String snapshotId) {
        return snapshots.findById(snapshotId).orElseThrow().getSourceValidation();
    }

    @Test
    void officialDocumentImportIsStoredAsUnverifiedAndCannotBeClaimed() throws Exception {
        MvcResult r = importOffering(importBody("2026-2027-OFD", "OFFICIAL_DOCUMENT",
            offering("OFD_CS101_01", "CS101", "周一第1-2节{第1-16周}")));
        assertEquals(200, r.getResponse().getStatus());
        String id = snapshotOf(r);
        assertEquals(CurriculumSnapshot.SourceKind.OFFICIAL_DOCUMENT, snapshots.findById(id).orElseThrow().getSourceKind());
        assertEquals(CurriculumSnapshot.SourceValidation.UNVERIFIED, validationOf(id));
    }

    @Test
    void errorRateAtOrBelowTwoPercentVerifiesAndAboveRejects() throws Exception {
        String id = snapshotOf(importOffering(importBody("2026-2027-RATE", "OFFICIAL_DOCUMENT",
            offering("RATE_CS101_01", "CS101", "周一第1-2节{第1-16周}"))));

        // 1/50 = 2% 恰好通过
        MvcResult ok = verify(id, request("核验甲", "上传乙", 50, 1), GOOD_ADMIN);
        assertEquals(200, ok.getResponse().getStatus());
        assertEquals("VERIFIED", json.readTree(ok.getResponse().getContentAsString()).get("data").get("outcome").asText());
        assertEquals(CurriculumSnapshot.SourceValidation.VERIFIED, validationOf(id));

        // 3/50 超过 2%，记为 REJECTED，且最近结论生效后快照回到 UNVERIFIED
        MvcResult bad = verify(id, request("核验甲", "上传乙", 50, 3), GOOD_ADMIN);
        assertEquals(200, bad.getResponse().getStatus());
        assertEquals("REJECTED", json.readTree(bad.getResponse().getContentAsString()).get("data").get("outcome").asText());
        assertEquals(CurriculumSnapshot.SourceValidation.UNVERIFIED, validationOf(id));
    }

    @Test
    void rejectsSameVerifierAndUploaderRegardlessOfCaseAndSpaces() throws Exception {
        String id = snapshotOf(importOffering(importBody("2026-2027-SAME", "OFFICIAL_DOCUMENT",
            offering("SAME_CS101_01", "CS101", "周一第1-2节{第1-16周}"))));
        MvcResult r = verify(id, request(" Zhang  San ", "zhangsan", 30, 0), GOOD_ADMIN);
        assertEquals(422, r.getResponse().getStatus());
        assertEquals("VERIFIER_IS_UPLOADER", json.readTree(r.getResponse().getContentAsString()).get("issues").get(0).get("code").asText());
        assertEquals(CurriculumSnapshot.SourceValidation.UNVERIFIED, validationOf(id));
    }

    @Test
    void rejectsSyntheticSnapshotSmallSampleAndBadInputs() throws Exception {
        String synthetic = snapshotOf(importOffering(importBody("2026-2027-SYN", "SYNTHETIC",
            offering("SYN_CS101_01", "CS101", "周一第1-2节{第1-16周}"))));
        assertEquals(422, verify(synthetic, request("核验甲", "上传乙", 30, 0), GOOD_ADMIN).getResponse().getStatus());

        String id = snapshotOf(importOffering(importBody("2026-2027-SMALL", "OFFICIAL_DOCUMENT",
            offering("SMALL_CS101_01", "CS101", "周一第1-2节{第1-16周}"))));
        assertEquals(400, verify(id, request("核验甲", "上传乙", 29, 0), GOOD_ADMIN).getResponse().getStatus());
        assertEquals(422, verify(id, request("核验甲", "上传乙", 30, 31), GOOD_ADMIN).getResponse().getStatus());
        assertEquals(400, verify(id, request("核验甲", "上传乙", 30, 0).replace(SHA, "XYZ"), GOOD_ADMIN).getResponse().getStatus());
        assertEquals(CurriculumSnapshot.SourceValidation.UNVERIFIED, validationOf(id));
    }

    @Test
    void requiresAdminKeyAndUnknownSnapshotIsNotFound() throws Exception {
        String id = snapshotOf(importOffering(importBody("2026-2027-AUTH", "OFFICIAL_DOCUMENT",
            offering("AUTHV_CS101_01", "CS101", "周一第1-2节{第1-16周}"))));
        assertEquals(401, verify(id, request("核验甲", "上传乙", 30, 0), null).getResponse().getStatus());
        assertEquals(401, verify(id, request("核验甲", "上传乙", 30, 0), "wrong").getResponse().getStatus());
        assertEquals(404, verify("OFS_NOPE", request("核验甲", "上传乙", 30, 0), GOOD_ADMIN).getResponse().getStatus());
    }

    @Test
    void realPlanOverVerifiedOfferingsHasRealScopeAndNoUnverifiedIssue() throws Exception {
        String id = snapshotOf(importOffering(importBody("2026-2027-REAL", "OFFICIAL_DOCUMENT",
            offering("REAL_CS201_FRI", "CS201", "周五第5-6节{第1-16周}"),
            offering("REAL_CS101_MON", "CS101", "周一第5-6节{第1-16周}"))));
        String plan = """
            {"schemaVersion":"1.0","curriculumSnapshotId":"PLAN_CS_2025","offeringSnapshotId":"%s",
             "academicRecordId":"S001","mode":"REAL","items":[
               {"courseCode":"CS201","teacherKey":null,"classId":"REAL_CS201_FRI"},
               {"courseCode":"CS101","teacherKey":null,"classId":"REAL_CS101_MON"}],"hardConstraints":[]}
            """.formatted(id);
        JsonNode before = data(validate(plan));
        assertEquals("COURSE_ONLY", before.get("scope").asText());
        assertTrue(hasCode(before.get("unknownChecks"), "TIMETABLE_UNVERIFIED"));

        assertEquals(200, verify(id, request("核验甲", "上传乙", 30, 0), GOOD_ADMIN).getResponse().getStatus());
        JsonNode after = data(validate(plan));
        assertEquals("REAL_TIMETABLE", after.get("scope").asText());
        assertFalse(hasCode(after.get("unknownChecks"), "TIMETABLE_UNVERIFIED"));
        assertEquals("VALID", after.get("verdict").asText());
    }

    /** 同一培养快照下的学业记录 S811：带一条未建模规则，用于验证分项互不吞并。 */
    @Autowired private TranscriptRepository transcripts;
    @Autowired private CurriculumUnmodeledRuleRepository unmodeledRules;

    private void ensureRulesCurriculum() {
        if (snapshots.findById("TEST_CURR_RULES").isPresent()) return;
        snapshots.save(new CurriculumSnapshot("TEST_CURR_RULES", CurriculumSnapshot.Kind.CURRICULUM,
            CurriculumSnapshot.State.PUBLISHED, CurriculumSnapshot.SourceKind.SYNTHETIC,
            CurriculumSnapshot.SourceValidation.SYNTHETIC, null, Instant.parse("2026-01-01T00:00:00Z")));
        unmodeledRules.save(new CurriculumUnmodeledRule(snapshots.getReferenceById("TEST_CURR_RULES"),
            "测试表", 7, "测试表!A7", "毕业前至少修读一门全英语课程", "synthetic raw note",
            "未建模（测试）", "原表注释/规则", CurriculumUnmodeledRule.Disposition.UNMODELED));
        Transcript record = new Transcript("S811");
        record.revise("TEST_CURR_RULES", true, Transcript.SourceKind.SYNTHETIC,
            Instant.parse("2026-01-01T00:00:00Z"), List.of());
        transcripts.save(record);
    }

    /** 导入并核验一个 REAL 开课快照（CS201 周五、CS101 周一，互不冲突），返回快照编号。 */
    private String verifiedRulesOfferings(String term, String prefix) throws Exception {
        String id = snapshotOf(importOffering(importBody(term, "OFFICIAL_DOCUMENT",
            offering(prefix + "_CS201_FRI", "CS201", "周五第5-6节{第1-16周}"),
            offering(prefix + "_CS101_MON", "CS101", "周一第5-6节{第1-16周}"))));
        assertEquals(200, verify(id, request("核验甲", "上传乙", 30, 0), GOOD_ADMIN).getResponse().getStatus());
        return id;
    }

    private static String rulesPlan(String snapshotId, String prefix, String constraints) {
        return """
            {"schemaVersion":"1.0","curriculumSnapshotId":"TEST_CURR_RULES","offeringSnapshotId":"%s",
             "academicRecordId":"S811","mode":"REAL","items":[
               {"courseCode":"CS201","teacherKey":null,"classId":"%s_CS201_FRI"},
               {"courseCode":"CS101","teacherKey":null,"classId":"%s_CS101_MON"}],"hardConstraints":[%s]}
            """.formatted(snapshotId, prefix, prefix, constraints);
    }

    private MvcResult validateAs(String body, String subject) throws Exception {
        return mvc.perform(post("/api/v1/plans/validate").header(SERVICE, GOOD_SERVICE).header(SUBJECT, subject)
            .contentType(MediaType.APPLICATION_JSON).content(body)).andReturn();
    }

    private static JsonNode section(JsonNode d, String scope) {
        for (JsonNode s : d.get("sections")) {
            if (scope.equals(s.get("scope").asText())) return s;
        }
        throw new AssertionError("缺少分项 " + scope);
    }

    @Test
    void verifiedConflictFreeTimetablePassesWhileCurriculumStaysUnknown() throws Exception {
        ensureRulesCurriculum();
        String id = verifiedRulesOfferings("2026-2027-RULES-A", "RA");
        JsonNode d = data(validateAs(rulesPlan(id, "RA", ""), "S811"));

        assertEquals("REAL_TIMETABLE", d.get("scope").asText());
        assertEquals("UNKNOWN", d.get("verdict").asText(), "总判决随最差分项：毕业要求侧 UNKNOWN");
        assertEquals(0, d.get("violations").size());

        JsonNode timetable = section(d, "TIMETABLE");
        assertEquals("VALID", timetable.get("verdict").asText());
        assertEquals(0, timetable.get("unknownChecks").size());

        JsonNode curriculum = section(d, "CURRICULUM");
        assertEquals("UNKNOWN", curriculum.get("verdict").asText());
        assertEquals(0, curriculum.get("violations").size());
        assertTrue(hasCode(curriculum.get("unknownChecks"), "UNMODELED_CURRICULUM_RULES"));
        // 顶层 unknownChecks 仍是两个分项的合并：这里只有毕业要求侧的一条。
        assertEquals(1, d.get("unknownChecks").size());
    }

    @Test
    void unverifiedOfficialDocumentMakesTimetableUnknownWithTimetableUnverified() throws Exception {
        ensureRulesCurriculum();
        String id = snapshotOf(importOffering(importBody("2026-2027-RULES-B", "OFFICIAL_DOCUMENT",
            offering("RB_CS201_FRI", "CS201", "周五第5-6节{第1-16周}"),
            offering("RB_CS101_MON", "CS101", "周一第5-6节{第1-16周}"))));
        JsonNode d = data(validateAs(rulesPlan(id, "RB", ""), "S811"));

        assertEquals("COURSE_ONLY", d.get("scope").asText());
        JsonNode timetable = section(d, "TIMETABLE");
        assertEquals("UNKNOWN", timetable.get("verdict").asText());
        assertTrue(hasCode(timetable.get("unknownChecks"), "TIMETABLE_UNVERIFIED"));
        assertEquals(0, timetable.get("violations").size());
    }

    @Test
    void blockDayHitMakesTimetableInvalidAndOverallInvalidEvenWithCurriculumUnknown() throws Exception {
        ensureRulesCurriculum();
        String id = verifiedRulesOfferings("2026-2027-RULES-C", "RC");
        String blockFriday = "{\"kind\":\"BLOCK_DAY\",\"courseCode\":null,\"teacherKey\":null,"
            + "\"dayOfWeek\":5,\"section\":null,\"value\":null,\"sourceText\":\"周五不排课\"}";
        JsonNode d = data(validateAs(rulesPlan(id, "RC", blockFriday), "S811"));

        assertEquals("INVALID", d.get("verdict").asText());
        JsonNode timetable = section(d, "TIMETABLE");
        assertEquals("INVALID", timetable.get("verdict").asText());
        assertTrue(hasCode(timetable.get("violations"), "CONSTRAINT_BLOCK_DAY"));
        assertEquals("UNKNOWN", section(d, "CURRICULUM").get("verdict").asText());
    }

    private MvcResult validate(String body) throws Exception {
        return mvc.perform(post("/api/v1/plans/validate").header(SERVICE, GOOD_SERVICE).header(SUBJECT, "S001")
            .contentType(MediaType.APPLICATION_JSON).content(body)).andReturn();
    }

    private JsonNode data(MvcResult r) throws Exception {
        return json.readTree(r.getResponse().getContentAsString()).get("data");
    }

    private static boolean hasCode(JsonNode issues, String code) {
        for (JsonNode n : issues) if (code.equals(n.get("code").asText())) return true;
        return false;
    }
}
