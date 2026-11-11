package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.entity.Course;
import com.coursepilot.verifier.persistence.entity.CourseOffering;
import com.coursepilot.verifier.persistence.entity.CurriculumCourse;
import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot;
import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot.Kind;
import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot.SourceKind;
import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot.SourceValidation;
import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot.State;
import com.coursepilot.verifier.persistence.entity.TeacherCourse;
import com.coursepilot.verifier.persistence.repo.CourseOfferingRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumCourseRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumSnapshotRepository;
import com.coursepilot.verifier.persistence.repo.ReviewNoteRepository;
import com.coursepilot.verifier.persistence.repo.TeacherCourseRepository;
import com.coursepilot.verifier.web.dto.TeacherReviewDtos;
import com.coursepilot.verifier.web.dto.TeacherReviewDtos.Availability;
import com.coursepilot.verifier.web.dto.TeacherReviewDtos.FactSource;
import com.coursepilot.verifier.web.dto.TeacherReviewDtos.TeacherCourseOption;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.Limit;
import org.springframework.data.domain.Sort;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * 教师选项中「本学期开课表」事实的推导：开课快照选取、教师聚合、provenance 与 availability。
 * 仓库用 Mockito 替身，不依赖种子数据（种子全部是 SYNTHETIC，不应被选中）。
 */
class TeacherOfferingOptionsTest {

    private static final String CUR = "CUR_REAL";
    private static final Instant T0 = Instant.parse("2026-10-01T00:00:00Z");
    private static final Instant T1 = Instant.parse("2026-11-01T00:00:00Z");
    private static final Instant T2 = Instant.parse("2026-11-02T00:00:00Z");

    private CurriculumSnapshotRepository snapshots;
    private CurriculumCourseRepository curriculumCourses;
    private TeacherCourseRepository teacherCourses;
    private ReviewNoteRepository reviews;
    private CourseOfferingRepository offerings;
    private TeacherReviewAssembler assembler;

    private CurriculumSnapshot curriculum;

    @BeforeEach
    void setUp() {
        snapshots = mock(CurriculumSnapshotRepository.class);
        curriculumCourses = mock(CurriculumCourseRepository.class);
        teacherCourses = mock(TeacherCourseRepository.class);
        reviews = mock(ReviewNoteRepository.class);
        offerings = mock(CourseOfferingRepository.class);
        assembler = new TeacherReviewAssembler(snapshots, curriculumCourses, teacherCourses, reviews, offerings);

        curriculum = new CurriculumSnapshot(CUR, Kind.CURRICULUM, State.PUBLISHED, SourceKind.CURRICULUM_FILE,
            SourceValidation.UNVERIFIED, null, T0);
        when(snapshots.findById(CUR)).thenReturn(Optional.of(curriculum));
        when(curriculumCourses.findBySnapshot_SnapshotIdOrderByCourse_CourseCodeAsc(CUR)).thenReturn(List.of(
            curriculumCourse("CS101", "程序设计基础"),
            curriculumCourse("CS201", "数据结构")));
    }

    private CurriculumCourse curriculumCourse(String code, String name) {
        return new CurriculumCourse(curriculum, new Course(code, name, 3.0, "必修"), name, 3.0, "必修",
            "CURRICULUM_FILE", "src:" + code, "loc", T0);
    }

    private static CurriculumSnapshot offeringSnapshot(String id, SourceKind kind, SourceValidation validation,
                                                       String termId, Instant createdAt) {
        return new CurriculumSnapshot(id, Kind.OFFERING, State.PUBLISHED, kind, validation, termId, createdAt);
    }

    private void publishedOfferings(CurriculumSnapshot... list) {
        when(snapshots.findByKindAndState(eq(Kind.OFFERING), eq(State.PUBLISHED), any(Sort.class), any(Limit.class)))
            .thenReturn(List.of(list));
    }

    private static CourseOffering section(String id, String courseCode, String teacher, String teacherKey,
                                          String snapshotId) {
        return new CourseOffering(id, courseCode, teacher, "周一 1-2 节", "OFFICIAL_DOCUMENT", snapshotId,
            "PARSED", teacherKey, "src", 3.0, 60);
    }

    private void sections(String snapshotId, CourseOffering... list) {
        when(offerings.findBySnapshotIdAndCourseCodeIn(eq(snapshotId), anyCollection())).thenReturn(List.of(list));
    }

    private List<TeacherCourseOption> options(String query) {
        return assembler.listOptions(CUR, null, query, 100, 0).items();
    }

    @Test
    @DisplayName("搜索「王」能找到本学期开课表中的教师，并带上班次数、课程名与来源")
    void wangFindsOfferingTeacherWithProvenance() {
        CurriculumSnapshot unverified = offeringSnapshot("OFS_U", SourceKind.OFFICIAL_DOCUMENT,
            SourceValidation.UNVERIFIED, "2026-2027-1", T1);
        publishedOfferings(unverified);
        sections("OFS_U",
            section("O_2", "CS101", "王明", "10012", "OFS_U"),
            section("O_1", "CS101", "王明", "10012", "OFS_U"),
            section("O_3", "CS201", "李华", "10020", "OFS_U"));

        List<TeacherCourseOption> items = options("王");

        assertThat(items).hasSize(1);
        TeacherCourseOption o = items.get(0);
        assertThat(o.courseCode()).isEqualTo("CS101");
        assertThat(o.courseName()).isEqualTo("程序设计基础");
        assertThat(o.teacherKey()).isEqualTo("10012");
        assertThat(o.teacherDisplayName()).isEqualTo("王明");
        assertThat(o.sectionCount()).isEqualTo(2);
        assertThat(o.classIds()).containsExactly("O_1", "O_2");
        assertThat(o.offeringSnapshotId()).isEqualTo("OFS_U");
        assertThat(o.offeringSourceValidation()).isEqualTo(TeacherReviewDtos.SourceValidation.UNVERIFIED);
        assertThat(o.factSource()).isEqualTo(FactSource.OFFERING_SNAPSHOT);
        // 未核验的开课快照不能给出 CURRENT_VERIFIED。
        assertThat(o.availability()).isEqualTo(Availability.UNKNOWN);
    }

    @Test
    @DisplayName("开课快照已核验（VERIFIED）时 availability 为 CURRENT_VERIFIED")
    void verifiedSnapshotGivesCurrentVerified() {
        publishedOfferings(offeringSnapshot("OFS_V", SourceKind.OFFICIAL_DOCUMENT, SourceValidation.VERIFIED,
            "2026-2027-1", T1));
        sections("OFS_V", section("O_1", "CS101", "王明", "10012", "OFS_V"));

        TeacherCourseOption o = options("王").get(0);
        assertThat(o.availability()).isEqualTo(Availability.CURRENT_VERIFIED);
        assertThat(o.offeringSourceValidation()).isEqualTo(TeacherReviewDtos.SourceValidation.VERIFIED);
    }

    @Test
    @DisplayName("选取开课快照：VERIFIED 优先于更新的未核验快照，OFFICIAL_DOCUMENT 优先于更新的浏览器快照，永不取 SYNTHETIC")
    void pickOrderPrefersVerifiedThenOfficialNeverSynthetic() {
        CurriculumSnapshot synthetic = offeringSnapshot("OFS_SYN", SourceKind.SYNTHETIC, SourceValidation.SYNTHETIC,
            null, T2);
        CurriculumSnapshot browserNewer = offeringSnapshot("OFS_BR", SourceKind.BROWSER_SNAPSHOT,
            SourceValidation.UNVERIFIED, null, T2);
        CurriculumSnapshot officialOlder = offeringSnapshot("OFS_OFF", SourceKind.OFFICIAL_DOCUMENT,
            SourceValidation.UNVERIFIED, null, T0);
        publishedOfferings(synthetic, browserNewer, officialOlder);
        assertThat(assembler.pickOfferingSnapshot(null).getSnapshotId()).isEqualTo("OFS_OFF");

        CurriculumSnapshot verifiedBrowser = offeringSnapshot("OFS_VB", SourceKind.BROWSER_SNAPSHOT,
            SourceValidation.VERIFIED, null, T0);
        publishedOfferings(synthetic, officialOlder, verifiedBrowser);
        assertThat(assembler.pickOfferingSnapshot(null).getSnapshotId()).isEqualTo("OFS_VB");

        publishedOfferings(synthetic);
        assertThat(assembler.pickOfferingSnapshot(null)).isNull();
    }

    @Test
    @DisplayName("培养快照登记了学期时只取同学期的开课快照")
    void termFilterAppliesWhenCurriculumHasTerm() {
        CurriculumSnapshot termed = new CurriculumSnapshot(CUR, Kind.CURRICULUM, State.PUBLISHED,
            SourceKind.CURRICULUM_FILE, SourceValidation.UNVERIFIED, "2026-2027-1", T0);
        assertThat(assembler.pickOfferingSnapshot(termed.getTermId())).isNull();

        publishedOfferings(
            offeringSnapshot("OFS_OLD", SourceKind.OFFICIAL_DOCUMENT, SourceValidation.UNVERIFIED, "2025-FALL", T2),
            offeringSnapshot("OFS_NOW", SourceKind.OFFICIAL_DOCUMENT, SourceValidation.UNVERIFIED, "2026-2027-1", T1));
        assertThat(assembler.pickOfferingSnapshot("2026-2027-1").getSnapshotId()).isEqualTo("OFS_NOW");
    }

    @Test
    @DisplayName("没有工号的班次跳过；培养快照之外的课程不进入结果")
    void sectionsWithoutTeacherKeyOrOutsideCurriculumAreSkipped() {
        publishedOfferings(offeringSnapshot("OFS_U", SourceKind.OFFICIAL_DOCUMENT, SourceValidation.UNVERIFIED,
            null, T1));
        sections("OFS_U",
            section("O_1", "CS101", "王明", null, "OFS_U"),
            section("O_2", "CS999", "王外", "19999", "OFS_U"));

        assertThat(options(null)).isEmpty();
    }

    @Test
    @DisplayName("同一对课程与教师同时存在绑定登记与开课事实时，以开课事实为准；只有绑定的仍保留为 TEACHER_BINDING")
    void offeringFactOverridesBindingForSamePair() {
        when(teacherCourses.findByCurriculumSnapshotIdOrderByCourseCodeAscTeacherKeyAsc(CUR)).thenReturn(List.of(
            new TeacherCourse(CUR, "CS101", "10012", "王明", null, TeacherCourse.SourceValidation.SYNTHETIC),
            new TeacherCourse(CUR, "CS201", "10020", "李华", null, TeacherCourse.SourceValidation.SYNTHETIC)));
        publishedOfferings(offeringSnapshot("OFS_U", SourceKind.OFFICIAL_DOCUMENT, SourceValidation.UNVERIFIED,
            null, T1));
        sections("OFS_U", section("O_1", "CS101", "王明", "10012", "OFS_U"));

        List<TeacherCourseOption> items = options(null);
        assertThat(items).hasSize(2);
        assertThat(items.get(0).courseCode()).isEqualTo("CS101");
        assertThat(items.get(0).factSource()).isEqualTo(FactSource.OFFERING_SNAPSHOT);
        assertThat(items.get(1).courseCode()).isEqualTo("CS201");
        assertThat(items.get(1).factSource()).isEqualTo(FactSource.TEACHER_BINDING);
        assertThat(items.get(1).sectionCount()).isNull();
        assertThat(items.get(1).offeringSnapshotId()).isNull();
    }

    @Test
    @DisplayName("没有可用开课快照时，只返回原有的教师绑定结果")
    void noOfferingSnapshotKeepsSeedPath() {
        when(teacherCourses.findByCurriculumSnapshotIdOrderByCourseCodeAscTeacherKeyAsc(CUR)).thenReturn(List.of(
            new TeacherCourse(CUR, "CS101", "10012", "王明", null, TeacherCourse.SourceValidation.SYNTHETIC)));
        publishedOfferings();

        List<TeacherCourseOption> items = options("王");
        assertThat(items).hasSize(1);
        assertThat(items.get(0).factSource()).isEqualTo(FactSource.TEACHER_BINDING);
        assertThat(items.get(0).availability()).isEqualTo(Availability.UNKNOWN);
        assertThat(items.get(0).courseName()).isEqualTo("程序设计基础");
    }
}
