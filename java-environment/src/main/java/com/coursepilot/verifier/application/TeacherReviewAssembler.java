package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.entity.CourseOffering;
import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot;
import com.coursepilot.verifier.persistence.entity.ReviewNote;
import com.coursepilot.verifier.persistence.entity.TeacherCourse;
import com.coursepilot.verifier.persistence.repo.CourseOfferingRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumSnapshotRepository;
import com.coursepilot.verifier.persistence.repo.ReviewNoteRepository;
import com.coursepilot.verifier.persistence.repo.TeacherCourseRepository;
import com.coursepilot.verifier.web.UnknownSnapshot;
import com.coursepilot.verifier.web.dto.TeacherReviewDtos;
import com.coursepilot.verifier.web.dto.TeacherReviewDtos.Availability;
import com.coursepilot.verifier.web.dto.TeacherReviewDtos.MatchStatus;
import com.coursepilot.verifier.web.dto.TeacherReviewDtos.ReviewNoteList;
import com.coursepilot.verifier.web.dto.TeacherReviewDtos.TeacherCourseOption;
import com.coursepilot.verifier.web.dto.TeacherReviewDtos.TeacherCourseOptionList;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Locale;

/**
 * 教师课程意愿对象与评价证据的组装：实体 -> 契约 DTO。
 *
 * 三条硬规则都在这里落地：
 *  1. 评价只有同时命中「课程 + 教师」绑定才是 COURSE_TEACHER_MATCHED；teacherKey 为空
 *     是 COURSE_ONLY，有教师但没有绑定是 UNVERIFIED。绝不把评价硬塞给某位教师。
 *  2. availability 只有在「当期开课 + 来源已核验」时才是 CURRENT_VERIFIED。
 *     历史评价不能证明当期开课，所以只有历史记录时是 HISTORICAL_ONLY，判断不了是 UNKNOWN。
 *  3. 维度按契约 dimensions 原样保留，不把它们合并成一个分数。
 */
@Service
public class TeacherReviewAssembler {

    private final CurriculumSnapshotRepository snapshotRepo;
    private final TeacherCourseRepository teacherRepo;
    private final ReviewNoteRepository reviewRepo;
    private final CourseOfferingRepository offeringRepo;

    public TeacherReviewAssembler(CurriculumSnapshotRepository snapshotRepo,
                                  TeacherCourseRepository teacherRepo,
                                  ReviewNoteRepository reviewRepo,
                                  CourseOfferingRepository offeringRepo) {
        this.snapshotRepo = snapshotRepo;
        this.teacherRepo = teacherRepo;
        this.reviewRepo = reviewRepo;
        this.offeringRepo = offeringRepo;
    }

    /**
     * 列出某培养快照下的教师课程对象。分页用偏移量游标：offset 为 cursor 的数值，
     * nextCursor 为下一页的偏移量，没有下一页则为 null。
     */
    public TeacherCourseOptionList listOptions(String curriculumSnapshotId, String courseCode,
                                               String query, int limit, int offset) {
        CurriculumSnapshot snapshot = snapshotRepo.findById(curriculumSnapshotId)
            .orElseThrow(() -> new UnknownSnapshot(curriculumSnapshotId));
        if (snapshot.getKind() != CurriculumSnapshot.Kind.CURRICULUM
            || snapshot.getState() != CurriculumSnapshot.State.PUBLISHED) {
            throw new UnknownSnapshot(curriculumSnapshotId);
        }

        String needle = query == null ? null : query.toLowerCase(Locale.ROOT);
        List<TeacherCourse> filtered = teacherRepo
            .findByCurriculumSnapshotIdOrderByCourseCodeAscTeacherKeyAsc(curriculumSnapshotId).stream()
            .filter(t -> courseCode == null || courseCode.equals(t.getCourseCode()))
            .filter(t -> needle == null
                || t.getTeacherDisplayName().toLowerCase(Locale.ROOT).contains(needle)
                || t.getCourseCode().toLowerCase(Locale.ROOT).contains(needle))
            .toList();

        int start = Math.min(offset, filtered.size());
        int end = Math.min(start + limit, filtered.size());
        String nextCursor = end < filtered.size() ? String.valueOf(end) : null;

        List<TeacherCourseOption> items = filtered.subList(start, end).stream()
            .map(this::toOption)
            .toList();
        return new TeacherCourseOptionList(items, nextCursor);
    }

    /**
     * 检索某课程的评价证据。teacherKey 给定时只返回该教师的评价（不含 teacherKey 为空的课程级评价）；
     * 未给定时返回该课程全部评价，各自带 matchStatus 说明匹配程度。
     */
    public ReviewNoteList search(String courseCode, String teacherKey, String termId, int limit) {
        List<TeacherReviewDtos.ReviewNote> items = reviewRepo.findByCourseCodeOrderByReviewNoteIdAsc(courseCode).stream()
            .filter(n -> teacherKey == null || teacherKey.equals(n.getTeacherKey()))
            .filter(n -> termId == null || termId.equals(n.getTermId()))
            .limit(limit)
            .map(this::toReview)
            .toList();
        return new ReviewNoteList(items);
    }

    private TeacherCourseOption toOption(TeacherCourse t) {
        List<ReviewNote> matched = reviewRepo.findByCourseCodeAndTeacherKeyOrderByReviewNoteIdAsc(
            t.getCourseCode(), t.getTeacherKey());
        List<String> reviewIds = matched.stream().map(ReviewNote::getReviewNoteId).toList();
        boolean hasHistory = matched.stream().anyMatch(n -> n.getTermId() != null);

        // 班次只按「课程 + 教师显示名」对应到开课记录。教师在开课表里是自由文本，没有教师主键。
        List<String> classIds = offeringRepo.findByCourseCode(t.getCourseCode()).stream()
            .filter(o -> t.getTeacherDisplayName().equals(o.getTeacher()))
            .map(CourseOffering::getOfferingId)
            .sorted()
            .toList();

        return new TeacherCourseOption(
            t.getCourseCode(),
            t.getTeacherKey(),
            t.getTeacherDisplayName(),
            availability(t.getCurrentTermId(), t.getSourceValidation(), hasHistory),
            reviewIds,
            classIds);
    }

    /**
     * 开课状态判定。CURRENT_VERIFIED 需要同时满足：声明了当期学期，且来源已核验（VERIFIED）。
     * 历史评价不能证明当期开课，因此只有历史记录时是 HISTORICAL_ONLY。
     * 当前没有任何 VERIFIED 的绑定数据，所以线上结果不会出现 CURRENT_VERIFIED。
     */
    static Availability availability(String currentTermId, TeacherCourse.SourceValidation sourceValidation,
                                     boolean hasHistory) {
        if (currentTermId != null && sourceValidation == TeacherCourse.SourceValidation.VERIFIED) {
            return Availability.CURRENT_VERIFIED;
        }
        if (hasHistory) {
            return Availability.HISTORICAL_ONLY;
        }
        return Availability.UNKNOWN;
    }

    private TeacherReviewDtos.ReviewNote toReview(ReviewNote n) {
        return new TeacherReviewDtos.ReviewNote(
            n.getReviewNoteId(),
            n.getCourseCode(),
            n.getTeacherKey(),
            n.getTermId(),
            TeacherReviewDtos.SourceKind.valueOf(n.getSourceKind().name()),
            n.getPublishedAt(),
            httpUrlOrNull(n.getSourceUrl()),
            n.getExcerpt(),
            n.getDimensions().stream()
                .sorted()
                .map(d -> TeacherReviewDtos.Dimension.valueOf(d.name()))
                .toList(),
            matchStatus(n),
            // 指向库内这条评价记录本身，不编造外部出处。
            "review:" + n.getReviewNoteId());
    }

    /** 匹配状态现算：没有教师即课程级；有教师且存在同课程绑定才算已匹配；其余为未核验。 */
    private MatchStatus matchStatus(ReviewNote n) {
        if (n.getTeacherKey() == null) {
            return MatchStatus.COURSE_ONLY;
        }
        return teacherRepo.existsByCourseCodeAndTeacherKey(n.getCourseCode(), n.getTeacherKey())
            ? MatchStatus.COURSE_TEACHER_MATCHED
            : MatchStatus.UNVERIFIED;
    }

    /** sourceUrl 只接受 http/https 可点击引用（docs/04 第 76 行）；其他一律不输出。 */
    private static String httpUrlOrNull(String url) {
        if (url == null) {
            return null;
        }
        String lower = url.toLowerCase(Locale.ROOT);
        return (lower.startsWith("http://") || lower.startsWith("https://")) ? url : null;
    }
}
