package com.coursepilot.verifier.web;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.coursepilot.verifier.persistence.entity.Course;
import com.coursepilot.verifier.persistence.entity.CurriculumCourse;
import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot;
import com.coursepilot.verifier.persistence.repo.CourseRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumCourseRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumSnapshotRepository;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
    "coursepilot.service-key=test-key",
    "spring.datasource.url=jdbc:h2:mem:queryendpointtest;DB_CLOSE_DELAY=-1"
})
class QueryEndpointTest {

    @Autowired private MockMvc mvc;
    @Autowired private CourseRepository courses;
    @Autowired private CurriculumSnapshotRepository snapshots;
    @Autowired private CurriculumCourseRepository memberships;

    @BeforeEach
    void createExplicitSnapshotMemberships() {
        CurriculumSnapshot first = snapshot("TEST_CURR_A");
        CurriculumSnapshot second = snapshot("TEST_CURR_B");
        Course a = course("QA001", "Alpha course");
        Course shared = course("QA002", "Shared course");
        Course b = course("QA003", "Beta course");
        Course orphan = course("QA999", "Unassociated legacy course");
        List.of(first, second).forEach(s -> snapshots.findById(s.getSnapshotId())
            .orElseGet(() -> snapshots.save(s)));
        List.of(a, shared, b, orphan).forEach(c -> courses.findById(c.getCourseCode())
            .orElseGet(() -> courses.save(c)));
        addMembership("TEST_CURR_A", "QA001", "Alpha A", 3.0, "必修");
        addMembership("TEST_CURR_A", "QA002", "Shared A", 3.0, "必修");
        addMembership("TEST_CURR_B", "QA002", "Shared B", 5.0, "专选");
        addMembership("TEST_CURR_B", "QA003", "Beta B", 4.0, "通识");
    }

    @Test
    void coursePagesAreIsolatedBySnapshotAndUseOffsetCursor() throws Exception {
        mvc.perform(get("/api/v1/courses")
                .param("curriculumSnapshotId", "TEST_CURR_A").param("limit", "1")
                .header("X-Service-Key", "test-key").header("X-Subject-Id", "student:test")
                .header("X-Request-Id", "req:query-a"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.items.length()").value(1))
            .andExpect(jsonPath("$.data.items[0].courseCode").value("QA001"))
            .andExpect(jsonPath("$.data.nextCursor").value("1"));

        mvc.perform(get("/api/v1/courses")
                .param("curriculumSnapshotId", "TEST_CURR_A").param("limit", "1")
                .param("cursor", "1")
                .header("X-Service-Key", "test-key").header("X-Subject-Id", "student:test")
                .header("X-Request-Id", "req:query-a2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.items[0].courseCode").value("QA002"))
            .andExpect(jsonPath("$.data.items[0].name").value("Shared A"))
            .andExpect(jsonPath("$.data.items[0].credits").value(3.0))
            .andExpect(jsonPath("$.data.nextCursor").value(org.hamcrest.Matchers.nullValue()));

        mvc.perform(get("/api/v1/courses")
                .param("curriculumSnapshotId", "TEST_CURR_B").param("limit", "10")
                .header("X-Service-Key", "test-key").header("X-Subject-Id", "student:test")
                .header("X-Request-Id", "req:query-b"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.items.length()").value(2))
            .andExpect(jsonPath("$.data.items[0].courseCode").value("QA002"))
            .andExpect(jsonPath("$.data.items[0].name").value("Shared B"))
            .andExpect(jsonPath("$.data.items[0].credits").value(5.0))
            .andExpect(jsonPath("$.data.items[1].courseCode").value("QA003"));
    }

    @Test
    void unpublishedOrUnknownSnapshotIsRejectedAndUnassociatedCourseIsNotReturned() throws Exception {
        mvc.perform(get("/api/v1/courses")
                .param("curriculumSnapshotId", "missing")
                .header("X-Service-Key", "test-key").header("X-Subject-Id", "student:test")
                .header("X-Request-Id", "req:query-missing"))
            .andExpect(status().isUnprocessableEntity());

        mvc.perform(get("/api/v1/courses")
                .param("curriculumSnapshotId", "TEST_CURR_A").param("query", "legacy")
                .header("X-Service-Key", "test-key").header("X-Subject-Id", "student:test")
                .header("X-Request-Id", "req:query-orphan"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.items.length()").value(0));
    }

    @Test
    void malformedCursorMatchesTeacherQueryErrorSemantics() throws Exception {
        mvc.perform(get("/api/v1/courses")
                .param("curriculumSnapshotId", "TEST_CURR_A").param("cursor", "-1")
                .header("X-Service-Key", "test-key").header("X-Subject-Id", "student:test")
                .header("X-Request-Id", "req:query-cursor"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("INVALID_QUERY"));
    }

    @Test
    void legacyMembershipWithoutSnapshotFactsReturnsExplicitUnknownError() throws Exception {
        snapshots.findById("TEST_CURR_LEGACY").orElseGet(() -> snapshots.save(snapshot("TEST_CURR_LEGACY")));
        Course legacy = courses.findById("QA998").orElseGet(() -> courses.save(course("QA998", "legacy")));
        addLegacyMembership("TEST_CURR_LEGACY", legacy);
        mvc.perform(get("/api/v1/courses")
                .param("curriculumSnapshotId", "TEST_CURR_LEGACY").param("query", "QA998")
                .header("X-Service-Key", "test-key").header("X-Subject-Id", "student:test")
                .header("X-Request-Id", "req:legacy-unknown"))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.status").value("ERROR"))
            .andExpect(jsonPath("$.issues[0].code").value("SNAPSHOT_COURSE_FACTS_UNKNOWN"));
    }

    @Test
    void freshSyntheticSeedIsExplicitlyVisibleOnlyInItsOwnSnapshot() throws Exception {
        mvc.perform(get("/api/v1/courses")
                .param("curriculumSnapshotId", "PLAN_CS_2025")
                .header("X-Service-Key", "test-key").header("X-Subject-Id", "student:test")
                .header("X-Request-Id", "req:seed-courses"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.items.length()").value(4));
    }

    private CurriculumSnapshot snapshot(String id) {
        return new CurriculumSnapshot(id, CurriculumSnapshot.Kind.CURRICULUM,
            CurriculumSnapshot.State.PUBLISHED, CurriculumSnapshot.SourceKind.SYNTHETIC,
            CurriculumSnapshot.SourceValidation.SYNTHETIC, null, Instant.parse("2026-01-01T00:00:00Z"));
    }

    private Course course(String code, String name) {
        return new Course(code, name, 3.0, "必修");
    }

    private void addMembership(String snapshotId, String courseCode, String name, Double credits, String category) {
        if (!memberships.existsBySnapshot_SnapshotIdAndCourse_CourseCode(snapshotId, courseCode)) {
            memberships.save(new CurriculumCourse(snapshots.getReferenceById(snapshotId),
                courses.getReferenceById(courseCode), name, credits, category, "SYNTHETIC",
                "synthetic:" + snapshotId + ":" + courseCode, "synthetic test fixture " + courseCode,
                Instant.parse("2026-01-01T00:00:00Z")));
        }
    }

    private void addLegacyMembership(String snapshotId, Course course) {
        if (!memberships.existsBySnapshot_SnapshotIdAndCourse_CourseCode(snapshotId, course.getCourseCode())) {
            memberships.save(new CurriculumCourse(snapshots.getReferenceById(snapshotId), course));
        }
    }
}
