package com.coursepilot.verifier.config;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot;
import com.coursepilot.verifier.persistence.repo.CourseOfferingRepository;
import com.coursepilot.verifier.persistence.repo.CourseRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumCourseRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumSnapshotRepository;
import com.coursepilot.verifier.persistence.repo.RequirementRepository;
import com.coursepilot.verifier.persistence.repo.ReviewNoteRepository;
import com.coursepilot.verifier.persistence.repo.TeacherCourseRepository;
import com.coursepilot.verifier.persistence.repo.TranscriptRepository;
import java.time.Instant;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.boot.CommandLineRunner;

class SeedDataTest {

    @Test
    void doesNotAttachDemoCoursesToExistingRealSnapshot() throws Exception {
        Fixtures f = new Fixtures();
        when(f.snapshots.count()).thenReturn(1L);
        when(f.snapshots.findById("PLAN_CS_2025")).thenReturn(Optional.of(
            new CurriculumSnapshot("PLAN_CS_2025", CurriculumSnapshot.Kind.CURRICULUM,
                CurriculumSnapshot.State.PUBLISHED, CurriculumSnapshot.SourceKind.CURRICULUM_FILE,
                CurriculumSnapshot.SourceValidation.VERIFIED, null, Instant.EPOCH)));

        assertDoesNotThrow(() -> f.runner().run());

        verify(f.snapshots, never()).save(org.mockito.ArgumentMatchers.any());
        verify(f.curriculumCourses, never()).save(org.mockito.ArgumentMatchers.any());
    }

    @Test
    void existingPartialSnapshotTableWithoutDemoIdDoesNotBreakStartup() throws Exception {
        Fixtures f = new Fixtures();
        when(f.snapshots.count()).thenReturn(2L);
        when(f.snapshots.findById("PLAN_CS_2025")).thenReturn(Optional.empty());

        assertDoesNotThrow(() -> f.runner().run());

        verify(f.curriculumCourses, never()).save(org.mockito.ArgumentMatchers.any());
        verify(f.snapshots, never()).save(org.mockito.ArgumentMatchers.any());
    }

    private static final class Fixtures {
        final CourseRepository courses = mock(CourseRepository.class);
        final RequirementRepository requirements = mock(RequirementRepository.class);
        final CourseOfferingRepository offerings = mock(CourseOfferingRepository.class);
        final CurriculumSnapshotRepository snapshots = mock(CurriculumSnapshotRepository.class);
        final CurriculumCourseRepository curriculumCourses = mock(CurriculumCourseRepository.class);
        final TranscriptRepository transcripts = mock(TranscriptRepository.class);
        final TeacherCourseRepository teacherCourses = mock(TeacherCourseRepository.class);
        final ReviewNoteRepository reviews = mock(ReviewNoteRepository.class);

        CommandLineRunner runner() {
            return new SeedData().init(courses, requirements, offerings, snapshots,
                curriculumCourses, transcripts, teacherCourses, reviews);
        }
    }
}
