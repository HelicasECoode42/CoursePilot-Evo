package com.coursepilot.verifier.web;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import com.coursepilot.verifier.persistence.entity.ReviewNote;
import com.coursepilot.verifier.persistence.repo.ReviewNoteRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class ReviewImportControllerTest {
    private static final String INPUT = """
        {"schemaVersion":"1.0","notes":[{"reviewNoteId":"review:1","courseCode":"CS101",
        "teacherKey":null,"termId":null,"sourceKind":"USER_IMPORT","publishedAt":null,
        "sourceUrl":null,"excerpt":"课程反馈","dimensions":["TEACHING"],
        "matchStatus":"UNVERIFIED","sourceRefId":"source:original"}]}
        """;

    @Test void importsSourceAndUnknownMatchAndRejectsBadCredentials() throws Exception {
        var repo = mock(ReviewNoteRepository.class);
        var controller = new ReviewImportController(repo, new SubjectGuard(), "admin-secret");
        var body = new ObjectMapper().readTree(INPUT);
        assertEquals(401, controller.importReviews("req:1", "subject:1", "wrong", body).getStatusCode().value());
        verifyNoInteractions(repo);
        assertEquals(201, controller.importReviews("req:1", "subject:1", "admin-secret", body).getStatusCode().value());
        @SuppressWarnings("unchecked") var captured = (ArgumentCaptor<List<ReviewNote>>) (ArgumentCaptor<?>) ArgumentCaptor.forClass(List.class);
        verify(repo).saveAll(captured.capture());
        assertEquals("source:original", captured.getValue().get(0).getSourceRefId());
        assertEquals("UNVERIFIED", captured.getValue().get(0).getImportedMatchStatus());
    }

    @Test void rejectsDuplicateIdsBeforeWriting() throws Exception {
        var repo = mock(ReviewNoteRepository.class);
        var controller = new ReviewImportController(repo, new SubjectGuard(), "admin-secret");
        var body = (com.fasterxml.jackson.databind.node.ObjectNode) new ObjectMapper().readTree(INPUT);
        var notes = (com.fasterxml.jackson.databind.node.ArrayNode) body.get("notes");
        notes.add(notes.get(0).deepCopy());
        assertEquals(400, controller.importReviews("req:1", "subject:1", "admin-secret", body).getStatusCode().value());
        verifyNoInteractions(repo);
    }

    @Test void rejectsNonWebSourceUrls() throws Exception {
        var repo = mock(ReviewNoteRepository.class);
        var controller = new ReviewImportController(repo, new SubjectGuard(), "admin-secret");
        var body = new ObjectMapper().readTree(INPUT.replace("\"sourceUrl\":null", "\"sourceUrl\":\"file:///private/review\""));
        assertEquals(400, controller.importReviews("req:1", "subject:1", "admin-secret", body).getStatusCode().value());
        verifyNoInteractions(repo);
    }

    @Test void importsDisplayNameWithoutCreatingTeacherMatch() throws Exception {
        var repo = mock(ReviewNoteRepository.class);
        var controller = new ReviewImportController(repo, new SubjectGuard(), "admin-secret");
        var body = new ObjectMapper().readTree(INPUT.replace("\"sourceRefId\":\"source:original\"", "\"sourceRefId\":\"source:original\",\"teacherDisplayName\":\"李老师\""));
        assertEquals(201, controller.importReviews("req:2", "subject:1", "admin-secret", body).getStatusCode().value());
        @SuppressWarnings("unchecked") var captured = (ArgumentCaptor<List<ReviewNote>>) (ArgumentCaptor<?>) ArgumentCaptor.forClass(List.class);
        verify(repo).saveAll(captured.capture());
        ReviewNote note = captured.getValue().get(0);
        assertNull(note.getTeacherKey());
        assertEquals("李老师", note.getTeacherDisplayName());
        assertEquals("UNVERIFIED", note.getImportedMatchStatus());
    }
}
