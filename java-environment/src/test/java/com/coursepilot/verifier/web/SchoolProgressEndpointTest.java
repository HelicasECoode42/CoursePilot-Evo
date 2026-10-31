package com.coursepilot.verifier.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.coursepilot.verifier.persistence.repo.SchoolProgressSnapshotRepository;
import com.coursepilot.verifier.persistence.repo.TranscriptRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
    "coursepilot.service-key=test-key",
    "spring.datasource.url=jdbc:h2:mem:schoolprogresstest;DB_CLOSE_DELAY=-1"
})
class SchoolProgressEndpointTest {
    @Autowired private MockMvc mvc;
    @Autowired private SchoolProgressSnapshotRepository snapshots;
    @Autowired private TranscriptRepository transcripts;

    private String body() {
        return """
            {"schemaVersion":"1.0","curriculumSnapshotId":"PLAN_CS_2025",
             "snapshot":{"format":"coursepilot-shu-academic-progress","version":1,
             "capturedAt":"2026-10-29T00:00:00Z","source":"fictional fixture",
             "nodes":[
               {"nodeId":"parent","parentId":null,"schoolNodeId":"98","leaf":false,"name":"公共基础课","requiredCredits":12,"earnedCredits":6,"remainingCredits":6},
               {"nodeId":"child","parentId":"parent","schoolNodeId":"54","leaf":true,"name":"公共基础课","requiredCredits":4,"earnedCredits":2,"remainingCredits":2}],
             "courses":[
               {"nodeId":"child","courseCode":"CP001","name":"虚构已通过课程","credits":2,"outcome":"PASSED","completedYear":"2024-2025","completedTerm":"1","grade":null,"makeup":null,"retake":null,"suggestedYear":null,"suggestedTerm":null},
               {"nodeId":"parent","courseCode":"CP001","name":"虚构已通过课程","credits":2,"outcome":"PASSED","completedYear":"2024-2025","completedTerm":"1","grade":null,"makeup":null,"retake":null,"suggestedYear":null,"suggestedTerm":null},
               {"nodeId":"child","courseCode":"CP002","name":"虚构未知课程","credits":2,"outcome":"UNKNOWN","completedYear":null,"completedTerm":null,"grade":null,"makeup":null,"retake":null,"suggestedYear":null,"suggestedTerm":null},
               {"nodeId":"child","courseCode":"CP003","name":"虚构未修课程","credits":2,"outcome":"NOT_TAKEN","completedYear":null,"completedTerm":null,"grade":null,"makeup":null,"retake":null,"suggestedYear":null,"suggestedTerm":null},
               {"nodeId":"child","courseCode":"CP004","name":"虚构未通过课程","credits":3,"outcome":"FAILED","completedYear":"2024-2025","completedTerm":"2","grade":null,"makeup":null,"retake":null,"suggestedYear":null,"suggestedTerm":null},
               {"nodeId":"child","courseCode":"CP005","name":"虚构在读课程","credits":4,"outcome":"IN_PROGRESS","completedYear":"2025-2026","completedTerm":"1","grade":null,"makeup":null,"retake":null,"suggestedYear":null,"suggestedTerm":null}]}}
            """;
    }

    private MvcResult send(String subject, String key) throws Exception {
        return mvc.perform(put("/api/v1/school-progress")
                .header("X-Service-Key", "test-key").header("X-Subject-Id", subject)
                .header("Idempotency-Key", key).contentType(MediaType.APPLICATION_JSON).content(body()))
            .andReturn();
    }

    @Test
    void savesTreeAndCourseFactsIdempotently() throws Exception {
        MvcResult first = send("S901", "school-one");
        MvcResult replay = send("S901", "school-two");
        assertEquals(200, first.getResponse().getStatus());
        assertEquals(200, replay.getResponse().getStatus());
        mvc.perform(get("/api/v1/school-progress").header("X-Service-Key", "test-key")
                .header("X-Subject-Id", "S901"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.snapshot.nodes.length()").value(2))
            .andExpect(jsonPath("$.data.snapshot.nodes[0].schoolNodeId").value("98"))
            .andExpect(jsonPath("$.data.snapshot.nodes[1].parentId").value("parent"))
            .andExpect(jsonPath("$.data.snapshot.nodes[0].name").value("公共基础课"))
            .andExpect(jsonPath("$.data.snapshot.nodes[1].name").value("公共基础课"))
            .andExpect(jsonPath("$.data.academicRecord.sourceKind").value("USER_IMPORT"))
            .andExpect(jsonPath("$.data.academicRecord.completedCourses[1].outcome").value("UNKNOWN"));
        assertEquals(1, snapshots.countBySubjectId("S901"));
        var record = transcripts.findByStudentId("S901").orElseThrow();
        assertEquals(4, record.getCompletedCourses().size(), "same course/term on two school nodes is one attempt; NOT_TAKEN remains only in source snapshot");
        assertEquals("UNKNOWN", record.getCompletedCourses().get(1).getOutcome().name());
        assertNull(record.getCompletedCourses().get(1).getEarnedCredits(), "UNKNOWN must not count imported credits");
        assertNull(record.getCompletedCourses().get(2).getEarnedCredits(), "FAILED must not count imported credits");
        assertNull(record.getCompletedCourses().get(3).getEarnedCredits(), "IN_PROGRESS must not count imported credits");
        assertEquals(0, record.getCompletedCourses().get(0).getEarnedCredits().compareTo(new java.math.BigDecimal("2.00")));
        assertNotEquals("PASSED", record.getCompletedCourses().get(1).getOutcome().name());
    }

    @Test
    void contentHashIgnoresCaptureTimeAndIncludesCurriculumId() throws Exception {
        send("S903", "school-three");
        String recaptured = body().replace("2026-10-29T00:00:00Z", "2026-10-30T00:00:00Z");
        mvc.perform(put("/api/v1/school-progress").header("X-Service-Key", "test-key")
                .header("X-Subject-Id", "S903").header("Idempotency-Key", "school-four")
                .contentType(MediaType.APPLICATION_JSON).content(recaptured))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.receipt.reused").value(true));
        String otherCurriculum = body().replace("PLAN_CS_2025", "PLAN_CS_2024");
        mvc.perform(put("/api/v1/school-progress").header("X-Service-Key", "test-key")
                .header("X-Subject-Id", "S903").header("Idempotency-Key", "school-five")
                .contentType(MediaType.APPLICATION_JSON).content(otherCurriculum))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.receipt.reused").value(false));
        assertEquals(2, snapshots.countBySubjectId("S903"));
    }

    @Test
    void idempotencyKeyReplaysSameRequestAndRejectsDifferentRequestBody() throws Exception {
        MvcResult first = send("S904", "school-idempotency");
        MvcResult replay = send("S904", "school-idempotency");
        assertEquals(200, first.getResponse().getStatus());
        assertEquals(200, replay.getResponse().getStatus());
        String replayedId = new com.fasterxml.jackson.databind.ObjectMapper()
            .readTree(first.getResponse().getContentAsString()).path("data").path("receipt")
            .path("schoolProgressId").asText();
        mvc.perform(put("/api/v1/school-progress").header("X-Service-Key", "test-key")
                .header("X-Subject-Id", "S904").header("Idempotency-Key", "school-idempotency")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body().replace("\"remainingCredits\":2", "\"remainingCredits\":3")))
            .andExpect(status().isConflict());
        mvc.perform(get("/api/v1/school-progress").header("X-Service-Key", "test-key")
                .header("X-Subject-Id", "S904"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.receipt.schoolProgressId").value(replayedId));
        assertEquals(1, snapshots.countBySubjectId("S904"));
    }

    @Test
    void importRequiresIdempotencyKey() throws Exception {
        mvc.perform(put("/api/v1/school-progress").header("X-Service-Key", "test-key")
                .header("X-Subject-Id", "S905").contentType(MediaType.APPLICATION_JSON).content(body()))
            .andExpect(status().isBadRequest());
        assertEquals(0, snapshots.countBySubjectId("S905"));
    }

    @Test
    void rejectsBrokenParentAndUnknownOutcome() throws Exception {
        String brokenParent = body().replace("\"parentId\":\"parent\"", "\"parentId\":\"missing\"");
        mvc.perform(put("/api/v1/school-progress").header("X-Service-Key", "test-key")
                .header("X-Subject-Id", "S902").header("Idempotency-Key", "bad-parent")
                .contentType(MediaType.APPLICATION_JSON).content(brokenParent))
            .andExpect(status().isBadRequest());
        String unknownOutcome = body().replace("\"outcome\":\"UNKNOWN\"", "\"outcome\":\"PASS_BY_GRADE\"");
        mvc.perform(put("/api/v1/school-progress").header("X-Service-Key", "test-key")
                .header("X-Subject-Id", "S902").header("Idempotency-Key", "bad-outcome")
                .contentType(MediaType.APPLICATION_JSON).content(unknownOutcome))
            .andExpect(status().isBadRequest());
    }
}
