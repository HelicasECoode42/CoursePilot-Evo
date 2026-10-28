package com.coursepilot.verifier.web;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.coursepilot.verifier.persistence.entity.Transcript;
import com.coursepilot.verifier.persistence.entity.TranscriptCourse;
import com.coursepilot.verifier.persistence.repo.IdempotencyEntryRepository;
import com.coursepilot.verifier.persistence.repo.TranscriptRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
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
 * 学业记录三个端点：列表形状、单条归属、POST 201 与字段、幂等、outcome 与重修存取。
 *
 * 每个写入用例使用独立的主体 ID，因为同一个 Spring 上下文共享一个内存库。
 */
@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
    "coursepilot.service-key=test-key",
    "spring.datasource.url=jdbc:h2:mem:recordtest;DB_CLOSE_DELAY=-1"
})
class AcademicRecordEndpointTest {

    private static final String KEY = "X-Service-Key";
    private static final String SUBJECT = "X-Subject-Id";
    private static final String IDEM = "Idempotency-Key";

    /** 四种 outcome 都出现，其中 CS101 第二次出现，用于重修。 */
    private static final String BODY_FOUR_OUTCOMES = """
        {"schemaVersion":"1.0","curriculumSnapshotId":"PLAN_CS_2025",
         "transcriptComplete":false,"sourceKind":"USER_IMPORT",
         "completedCourses":[
           {"courseCode":"CS101","earnedCredits":3.0,"outcome":"PASSED","completedTerm":"2024-2025-1"},
           {"courseCode":"MATH201","earnedCredits":null,"outcome":"IN_PROGRESS","completedTerm":null},
           {"courseCode":"PHYS110","earnedCredits":null,"outcome":"UNKNOWN","completedTerm":"2023-2024-2"},
           {"courseCode":"CS101","earnedCredits":0.0,"outcome":"FAILED","completedTerm":"2024-2025-2"}
         ]}
        """;

    @Autowired private MockMvc mvc;
    @Autowired private ObjectMapper json;
    @Autowired private TranscriptRepository transcripts;
    @Autowired private IdempotencyEntryRepository idempotency;

    private MvcResult submit(String subject, String key, String body) throws Exception {
        return mvc.perform(post("/api/v1/academic-records")
                .header(KEY, "test-key").header(SUBJECT, subject).header(IDEM, key)
                .contentType(MediaType.APPLICATION_JSON).content(body))
            .andReturn();
    }

    @Test
    @DisplayName("列表是 {items} 形状，不含 studentId")
    void listHasItemsShapeWithoutOwner() throws Exception {
        mvc.perform(get("/api/v1/academic-records").header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("OK"))
            .andExpect(jsonPath("$.data.items").isArray())
            .andExpect(jsonPath("$.data.items[0].academicRecordId").value("S001"))
            .andExpect(jsonPath("$.data.items[0].completedCourses.length()").value(4))
            .andExpect(content().string(org.hamcrest.Matchers.not(
                org.hamcrest.Matchers.containsString("studentId"))));
    }

    @Test
    @DisplayName("没有记录的主体：items 为空数组，200 而不是 404")
    void listIsEmptyWithoutRecord() throws Exception {
        mvc.perform(get("/api/v1/academic-records").header(KEY, "test-key").header(SUBJECT, "S555"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("OK"))
            .andExpect(jsonPath("$.data.items").isArray())
            .andExpect(jsonPath("$.data.items").isEmpty());
    }

    @Test
    @DisplayName("单条：自己的记录按契约形状返回")
    void ownRecordMatchesContract() throws Exception {
        mvc.perform(get("/api/v1/academic-records/S001").header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.academicRecordId").value("S001"))
            .andExpect(jsonPath("$.data.revision").value(1))
            .andExpect(jsonPath("$.data.curriculumSnapshotId").value("PLAN_CS_2025"))
            .andExpect(jsonPath("$.data.sourceKind").value("SYNTHETIC"))
            .andExpect(jsonPath("$.data.createdAt").exists());
    }

    @Test
    @DisplayName("单条：自己名下还没有记录，404")
    void ownMissingRecordIsNotVisible() throws Exception {
        mvc.perform(get("/api/v1/academic-records/S556").header(KEY, "test-key").header(SUBJECT, "S556"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.issues[0].code").value("NOT_VISIBLE"));
    }

    @Test
    @DisplayName("POST 返回 201，字段齐全，服务端分配 revision 1 与 createdAt")
    void postReturns201WithAllFields() throws Exception {
        mvc.perform(post("/api/v1/academic-records")
                .header(KEY, "test-key").header(SUBJECT, "S701").header(IDEM, "k-create-1")
                .contentType(MediaType.APPLICATION_JSON).content(BODY_FOUR_OUTCOMES))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.status").value("OK"))
            .andExpect(jsonPath("$.data.academicRecordId").value("S701"))
            .andExpect(jsonPath("$.data.revision").value(1))
            .andExpect(jsonPath("$.data.curriculumSnapshotId").value("PLAN_CS_2025"))
            .andExpect(jsonPath("$.data.transcriptComplete").value(false))
            .andExpect(jsonPath("$.data.sourceKind").value("USER_IMPORT"))
            .andExpect(jsonPath("$.data.createdAt").exists())
            .andExpect(jsonPath("$.data.completedCourses.length()").value(4))
            .andExpect(jsonPath("$.data.completedCourses[0].earnedCredits").value(3.0))
            .andExpect(jsonPath("$.data.completedCourses[1].earnedCredits").value(
                org.hamcrest.Matchers.nullValue()))
            .andExpect(jsonPath("$.data.completedCourses[1].completedTerm").value(
                org.hamcrest.Matchers.nullValue()))
            .andExpect(content().string(org.hamcrest.Matchers.not(
                org.hamcrest.Matchers.containsString("studentId"))));
    }

    @Test
    @DisplayName("outcome 四种取值都能存取，重修在库里记下 attemptNo 1 与 2")
    void outcomesAndRetakeAttemptsArePersisted() throws Exception {
        assertEquals(201, submit("S702", "k-outcome-1", BODY_FOUR_OUTCOMES).getResponse().getStatus());

        Transcript t = transcripts.findByStudentId("S702").orElseThrow();
        List<TranscriptCourse> rows = t.getCompletedCourses();
        assertEquals(List.of(TranscriptCourse.Outcome.PASSED, TranscriptCourse.Outcome.IN_PROGRESS,
            TranscriptCourse.Outcome.UNKNOWN, TranscriptCourse.Outcome.FAILED),
            rows.stream().map(TranscriptCourse::getOutcome).toList());
        assertEquals(List.of(1, 1, 1, 2), rows.stream().map(TranscriptCourse::getAttemptNo).toList(),
            "同一 courseCode 的第二次出现是第 2 次修读");
        assertEquals(0, rows.get(3).getEarnedCredits().compareTo(java.math.BigDecimal.ZERO),
            "FAILED 的学分 0 要原样保存，不能丢成 null");
    }

    @Test
    @DisplayName("同幂等键重复提交只落一条：第二次回放第一次的答复，revision 不变")
    void sameIdempotencyKeyWritesOnce() throws Exception {
        MvcResult first = submit("S703", "k-idem-1", BODY_FOUR_OUTCOMES);
        MvcResult second = submit("S703", "k-idem-1", BODY_FOUR_OUTCOMES);

        assertEquals(201, first.getResponse().getStatus());
        assertEquals(201, second.getResponse().getStatus());
        JsonNode firstData = json.readTree(first.getResponse().getContentAsString()).get("data");
        JsonNode secondData = json.readTree(second.getResponse().getContentAsString()).get("data");
        assertEquals(firstData, secondData, "重复提交的 data 必须与第一次完全一致");

        Transcript t = transcripts.findByStudentId("S703").orElseThrow();
        assertEquals(1, t.getRevision(), "重复提交不能推进 revision");
        assertEquals(4, t.getCompletedCourses().size(), "子表不能被重复写入");
        assertTrue(idempotency.findByStudentIdAndIdemKey("S703", "k-idem-1").isPresent());
    }

    @Test
    @DisplayName("同键但内容不同：409，不写库")
    void sameKeyDifferentBodyIsConflict() throws Exception {
        assertEquals(201, submit("S704", "k-conf-1", BODY_FOUR_OUTCOMES).getResponse().getStatus());
        String changed = BODY_FOUR_OUTCOMES.replace("\"transcriptComplete\":false",
            "\"transcriptComplete\":true");
        MvcResult again = submit("S704", "k-conf-1", changed);

        assertEquals(409, again.getResponse().getStatus());
        assertTrue(again.getResponse().getContentAsString().contains("\"CONFLICT\""));
        assertEquals(1, transcripts.findByStudentId("S704").orElseThrow().getRevision());
    }

    @Test
    @DisplayName("不同键再次写入：revision 递增，子表整体替换而不是累加")
    void newKeyBumpsRevisionAndReplacesCourses() throws Exception {
        assertEquals(201, submit("S705", "k-rev-1", BODY_FOUR_OUTCOMES).getResponse().getStatus());
        String one = """
            {"schemaVersion":"1.0","curriculumSnapshotId":"PLAN_CS_2025",
             "transcriptComplete":true,"sourceKind":"USER_IMPORT",
             "completedCourses":[{"courseCode":"CS102","earnedCredits":4.0,"outcome":"PASSED","completedTerm":null}]}
            """;
        mvc.perform(post("/api/v1/academic-records")
                .header(KEY, "test-key").header(SUBJECT, "S705").header(IDEM, "k-rev-2")
                .contentType(MediaType.APPLICATION_JSON).content(one))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.data.revision").value(2))
            .andExpect(jsonPath("$.data.completedCourses.length()").value(1));
    }

    @Test
    @DisplayName("没有 Idempotency-Key：400")
    void missingIdempotencyKeyIsBadRequest() throws Exception {
        mvc.perform(post("/api/v1/academic-records")
                .header(KEY, "test-key").header(SUBJECT, "S706")
                .contentType(MediaType.APPLICATION_JSON).content(BODY_FOUR_OUTCOMES))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("MISSING_HEADER"));
    }

    @Test
    @DisplayName("没有主体身份：400，不写库")
    void missingSubjectIsBadRequest() throws Exception {
        mvc.perform(post("/api/v1/academic-records")
                .header(KEY, "test-key").header(IDEM, "k-nosubj")
                .contentType(MediaType.APPLICATION_JSON).content(BODY_FOUR_OUTCOMES))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("INVALID_SUBJECT"));
    }

    @Test
    @DisplayName("学分超范围或精度超两位：400")
    void badCreditsAreRejected() throws Exception {
        String tooBig = BODY_FOUR_OUTCOMES.replace("\"earnedCredits\":3.0", "\"earnedCredits\":1000.5");
        mvc.perform(post("/api/v1/academic-records")
                .header(KEY, "test-key").header(SUBJECT, "S707").header(IDEM, "k-bad-1")
                .contentType(MediaType.APPLICATION_JSON).content(tooBig))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("INVALID_INPUT"));

        String tooPrecise = BODY_FOUR_OUTCOMES.replace("\"earnedCredits\":3.0", "\"earnedCredits\":3.001");
        mvc.perform(post("/api/v1/academic-records")
                .header(KEY, "test-key").header(SUBJECT, "S707").header(IDEM, "k-bad-2")
                .contentType(MediaType.APPLICATION_JSON).content(tooPrecise))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("INVALID_INPUT"));
    }

    @Test
    @DisplayName("未知 outcome 与错误 schemaVersion：400")
    void unknownOutcomeAndSchemaVersionAreRejected() throws Exception {
        String unknownOutcome = BODY_FOUR_OUTCOMES.replace("\"PASSED\"", "\"DONE\"");
        mvc.perform(post("/api/v1/academic-records")
                .header(KEY, "test-key").header(SUBJECT, "S708").header(IDEM, "k-outcome-bad")
                .contentType(MediaType.APPLICATION_JSON).content(unknownOutcome))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("MALFORMED_JSON"));

        String wrongVersion = BODY_FOUR_OUTCOMES.replace("\"1.0\"", "\"2.0\"");
        mvc.perform(post("/api/v1/academic-records")
                .header(KEY, "test-key").header(SUBJECT, "S708").header(IDEM, "k-ver-bad")
                .contentType(MediaType.APPLICATION_JSON).content(wrongVersion))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("INVALID_INPUT"));
    }

    @Test
    @DisplayName("快照不存在：422，不写库")
    void unknownSnapshotIsUnprocessable() throws Exception {
        String body = BODY_FOUR_OUTCOMES.replace("PLAN_CS_2025", "NO_SUCH_PLAN");
        mvc.perform(post("/api/v1/academic-records")
                .header(KEY, "test-key").header(SUBJECT, "S709").header(IDEM, "k-snap-1")
                .contentType(MediaType.APPLICATION_JSON).content(body))
            .andExpect(status().isUnprocessableEntity())
            .andExpect(jsonPath("$.issues[0].code").value("SNAPSHOT_NOT_FOUND"));
        assertTrue(transcripts.findByStudentId("S709").isEmpty());
    }

    @Test
    @DisplayName("写入端点同样要求服务密钥")
    void postWithoutServiceKeyIsUnauthorized() throws Exception {
        mvc.perform(post("/api/v1/academic-records")
                .header(SUBJECT, "S710").header(IDEM, "k-nokey")
                .contentType(MediaType.APPLICATION_JSON).content(BODY_FOUR_OUTCOMES))
            .andExpect(status().isUnauthorized());
    }
}
