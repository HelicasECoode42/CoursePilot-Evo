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

    @Test
    void backfillsMissingCurriculumCoursesInAnExistingSyntheticDatabase() throws Exception {
        // 旧文件库：course 行已存在（所以种子会 early return），快照存在且是演示快照，
        // 但快照级 CurriculumCourse 表是后加的，归属行缺失。
        // 不补的话 GET /api/v1/courses?curriculumSnapshotId=... 返回 0 门课，
        // Agent 拿不到候选，只能一直答 UNABLE_TO_VERIFY。
        Fixtures f = new Fixtures();
        when(f.snapshots.count()).thenReturn(2L);
        when(f.snapshots.findById("PLAN_CS_2025")).thenReturn(Optional.of(syntheticDemoSnapshot()));
        when(f.courses.count()).thenReturn(4L);
        for (String code : java.util.List.of("CS101", "CS102", "GE101", "CS103")) {
            when(f.courses.existsById(code)).thenReturn(true);
            when(f.curriculumCourses
                .existsBySnapshot_SnapshotIdAndCourse_CourseCode("PLAN_CS_2025", code))
                .thenReturn(false);
        }

        f.runner().run();

        verify(f.curriculumCourses, org.mockito.Mockito.times(4))
            .save(org.mockito.ArgumentMatchers.any());
    }

    @Test
    void doesNotDuplicateCurriculumCoursesThatAlreadyExist() throws Exception {
        Fixtures f = new Fixtures();
        when(f.snapshots.count()).thenReturn(2L);
        when(f.snapshots.findById("PLAN_CS_2025")).thenReturn(Optional.of(syntheticDemoSnapshot()));
        when(f.courses.count()).thenReturn(4L);
        for (String code : java.util.List.of("CS101", "CS102", "GE101", "CS103")) {
            when(f.courses.existsById(code)).thenReturn(true);
            when(f.curriculumCourses
                .existsBySnapshot_SnapshotIdAndCourse_CourseCode("PLAN_CS_2025", code))
                .thenReturn(true);
        }

        f.runner().run();

        verify(f.curriculumCourses, never()).save(org.mockito.ArgumentMatchers.any());
    }

    private static CurriculumSnapshot syntheticDemoSnapshot() {
        return new CurriculumSnapshot("PLAN_CS_2025", CurriculumSnapshot.Kind.CURRICULUM,
            CurriculumSnapshot.State.PUBLISHED, CurriculumSnapshot.SourceKind.SYNTHETIC,
            CurriculumSnapshot.SourceValidation.SYNTHETIC, null, Instant.EPOCH);
    }
}
