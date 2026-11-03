package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.entity.CourseOffering;
import com.coursepilot.verifier.persistence.entity.CurriculumCourse;
import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot;
import com.coursepilot.verifier.persistence.entity.ReviewNote;
import com.coursepilot.verifier.persistence.entity.TeacherCourse;
import com.coursepilot.verifier.persistence.repo.CourseOfferingRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumCourseRepository;
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
import org.springframework.data.domain.Limit;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;

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

    /** 契约 TeacherCourseOption.classIds 的上限；超出时只截断列表，sectionCount 仍为全量。 */
    private static final int MAX_CLASS_IDS = 200;
    /** 候选开课快照的扫描上限，远大于实际的已发布开课快照数量。 */
    private static final int OFFERING_SNAPSHOT_SCAN = 200;

    private final CurriculumSnapshotRepository snapshotRepo;
    private final CurriculumCourseRepository curriculumCourseRepo;
    private final TeacherCourseRepository teacherRepo;
    private final ReviewNoteRepository reviewRepo;
    private final CourseOfferingRepository offeringRepo;

    public TeacherReviewAssembler(CurriculumSnapshotRepository snapshotRepo,
                                  CurriculumCourseRepository curriculumCourseRepo,
                                  TeacherCourseRepository teacherRepo,
                                  ReviewNoteRepository reviewRepo,
                                  CourseOfferingRepository offeringRepo) {
        this.snapshotRepo = snapshotRepo;
        this.curriculumCourseRepo = curriculumCourseRepo;
        this.teacherRepo = teacherRepo;
        this.reviewRepo = reviewRepo;
        this.offeringRepo = offeringRepo;
    }

    /**
     * 列出某培养快照下的教师课程对象，两类事实合并为一个列表：
     *  - 培养快照登记的教师绑定（teacher_course，种子路径，行为不变）；
     *  - 本学期开课快照中、课程属于该培养快照、带教师工号的班次，按「课程 + 教师」聚合。
     * 同一对课程与教师两边都有时，以开课事实为准（它带班次数与来源状态）。
     * 分页用偏移量游标：offset 为 cursor 的数值，nextCursor 为下一页的偏移量，没有下一页则为 null。
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
        Map<String, String> courseNames = courseNamesOf(curriculumSnapshotId);

        Map<String, TeacherCourseOption> byPair = new LinkedHashMap<>();
        for (TeacherCourse t : teacherRepo.findByCurriculumSnapshotIdOrderByCourseCodeAscTeacherKeyAsc(curriculumSnapshotId)) {
            if (courseCode != null && !courseCode.equals(t.getCourseCode())) {
                continue;
            }
            String name = courseNames.get(t.getCourseCode());
            if (!matches(needle, t.getCourseCode(), name, t.getTeacherDisplayName())) {
                continue;
            }
            byPair.put(pairKey(t.getCourseCode(), t.getTeacherKey()), bindingOption(t, name));
        }
        for (TeacherCourseOption o : offeringOptions(snapshot, courseCode, needle, courseNames)) {
            byPair.put(pairKey(o.courseCode(), o.teacherKey()), o);
        }

        List<TeacherCourseOption> all = byPair.values().stream()
            .sorted(Comparator.comparing(TeacherCourseOption::courseCode)
                .thenComparing(TeacherCourseOption::teacherKey))
            .toList();
        int start = Math.min(offset, all.size());
        int end = Math.min(start + limit, all.size());
        String nextCursor = end < all.size() ? String.valueOf(end) : null;
        return new TeacherCourseOptionList(all.subList(start, end), nextCursor);
    }

    /**
     * 由开课快照推出「课程 + 教师」对。只取培养快照中存在的课程（有班次的那部分），
     * 教师按工号聚合；没有工号的班次无法确定教师，跳过。
     * availability 只有开课快照 VERIFIED 时才是 CURRENT_VERIFIED，否则是 UNKNOWN（未核验，不能当作已确认的开课）。
     */
    private List<TeacherCourseOption> offeringOptions(CurriculumSnapshot curriculum, String courseCode,
                                                      String needle, Map<String, String> courseNames) {
        CurriculumSnapshot offering = pickOfferingSnapshot(curriculum.getTermId());
        if (offering == null) {
            return List.of();
        }
        List<String> codes = courseNames.keySet().stream()
            .filter(c -> courseCode == null || courseCode.equals(c))
            .toList();
        if (codes.isEmpty()) {
            return List.of();
        }

        Map<String, List<CourseOffering>> groups = new TreeMap<>();
        for (CourseOffering o : offeringRepo.findBySnapshotIdAndCourseCodeIn(offering.getSnapshotId(), codes)) {
            if (o.getTeacherKey() == null || o.getTeacher() == null || !courseNames.containsKey(o.getCourseCode())) {
                continue;
            }
            groups.computeIfAbsent(pairKey(o.getCourseCode(), o.getTeacherKey()), k -> new ArrayList<>()).add(o);
        }

        boolean verified = offering.getSourceValidation() == CurriculumSnapshot.SourceValidation.VERIFIED;
        List<TeacherCourseOption> out = new ArrayList<>();
        for (List<CourseOffering> sections : groups.values()) {
            sections.sort(Comparator.comparing(CourseOffering::getOfferingId));
            CourseOffering first = sections.get(0);
            String name = courseNames.get(first.getCourseCode());
            if (!matches(needle, first.getCourseCode(), name, first.getTeacher())) {
                continue;
            }
            List<String> reviewIds = reviewIdsOf(first.getCourseCode(), first.getTeacherKey());
            List<String> classIds = sections.stream()
                .map(CourseOffering::getOfferingId)
                .limit(MAX_CLASS_IDS)
                .toList();
            out.add(new TeacherCourseOption(
                first.getCourseCode(),
                first.getTeacherKey(),
                first.getTeacher(),
                verified ? Availability.CURRENT_VERIFIED : Availability.UNKNOWN,
                reviewIds,
                classIds,
                name,
                sections.size(),
                offering.getSnapshotId(),
                TeacherReviewDtos.SourceValidation.valueOf(offering.getSourceValidation().name()),
                TeacherReviewDtos.FactSource.OFFERING_SNAPSHOT));
        }
        return out;
    }

    /**
     * 选取用于教师选项的开课快照：已发布的 OFFERING，永不取 SYNTHETIC。培养快照登记了学期时只取同学期；
     * 没有学期（当前真实培养快照如此）时不按学期过滤。排序：VERIFIED 优先，其次 OFFICIAL_DOCUMENT，同级取最新。
     */
    CurriculumSnapshot pickOfferingSnapshot(String termId) {
        return snapshotRepo.findByKindAndState(CurriculumSnapshot.Kind.OFFERING, CurriculumSnapshot.State.PUBLISHED,
                Sort.by(Sort.Direction.DESC, "createdAt"), Limit.of(OFFERING_SNAPSHOT_SCAN))
            .stream()
            .filter(s -> s.getSourceKind() != CurriculumSnapshot.SourceKind.SYNTHETIC)
            .filter(s -> termId == null || termId.equals(s.getTermId()))
            .sorted(Comparator
                .comparingInt((CurriculumSnapshot s) -> s.getSourceValidation() == CurriculumSnapshot.SourceValidation.VERIFIED ? 0 : 1)
                .thenComparingInt(s -> s.getSourceKind() == CurriculumSnapshot.SourceKind.OFFICIAL_DOCUMENT ? 0 : 1))
            .findFirst()
            .orElse(null);
    }

    /** 培养快照的课程号 -> 课程名（同一课程号多名时取排序最前的一个，记为占位编号歧义，不在此消解）。 */
    private Map<String, String> courseNamesOf(String curriculumSnapshotId) {
        Map<String, String> names = new TreeMap<>();
        for (CurriculumCourse cc : curriculumCourseRepo
            .findBySnapshot_SnapshotIdOrderByCourse_CourseCodeAsc(curriculumSnapshotId)) {
            names.putIfAbsent(cc.getCourse().getCourseCode(), cc.getName());
        }
        return names;
    }

    private TeacherCourseOption bindingOption(TeacherCourse t, String courseName) {
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

        return TeacherCourseOption.binding(
            t.getCourseCode(),
            t.getTeacherKey(),
            t.getTeacherDisplayName(),
            availability(t.getCurrentTermId(), t.getSourceValidation(), hasHistory),
            reviewIds,
            classIds,
            courseName);
    }

    private List<String> reviewIdsOf(String courseCode, String teacherKey) {
        return reviewRepo.findByCourseCodeAndTeacherKeyOrderByReviewNoteIdAsc(courseCode, teacherKey).stream()
            .map(ReviewNote::getReviewNoteId)
            .toList();
    }

    private static String pairKey(String courseCode, String teacherKey) {
        return courseCode + "\u0000" + teacherKey;
    }

    /** 课程号、课程名、教师名任一包含检索词（不区分大小写）即命中；needle 为空表示不过滤。 */
    private static boolean matches(String needle, String courseCode, String courseName, String teacherName) {
        if (needle == null) {
            return true;
        }
        return contains(courseCode, needle) || contains(courseName, needle) || contains(teacherName, needle);
    }

    private static boolean contains(String value, String needle) {
        return value != null && value.toLowerCase(Locale.ROOT).contains(needle);
    }

    /**
     * 检索某课程的评价证据。teacherKey 给定时只返回该教师的评价（不含 teacherKey 为空的课程级评价）；
     * 未给定时返回该课程全部评价，各自带 matchStatus 说明匹配程度。
     */
    public ReviewNoteList search(String courseCode, String teacherKey, String termId, int limit) {
        return search(courseCode, teacherKey, termId, limit, 0);
    }

    public ReviewNoteList search(String courseCode, String teacherKey, String termId, int limit, int offset) {
        List<TeacherReviewDtos.ReviewNote> items = reviewRepo.findByCourseCodeOrderByReviewNoteIdAsc(courseCode).stream()
            .filter(n -> teacherKey == null || teacherKey.equals(n.getTeacherKey()))
            .filter(n -> termId == null || termId.equals(n.getTermId()))
            .skip(offset)
            .limit(limit + 1L)
            .map(this::toReview)
            .toList();
        boolean hasNext = items.size() > limit;
        return new ReviewNoteList(hasNext ? items.subList(0, limit) : items,
            hasNext ? String.valueOf(offset + limit) : null);
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
            n.getTeacherDisplayName(),
            n.getDimensions().stream()
                .sorted()
                .map(d -> TeacherReviewDtos.Dimension.valueOf(d.name()))
                .toList(),
            matchStatus(n),
            // 指向库内这条评价记录本身，不编造外部出处。
            n.getSourceRefId() == null ? "review:" + n.getReviewNoteId() : n.getSourceRefId());
    }

    /** 匹配状态现算：没有教师即课程级；有教师且存在同课程绑定才算已匹配；其余为未核验。 */
    private MatchStatus matchStatus(ReviewNote n) {
        if ("UNVERIFIED".equals(n.getImportedMatchStatus())) return MatchStatus.UNVERIFIED;
        if ("COURSE_ONLY".equals(n.getImportedMatchStatus())) return MatchStatus.COURSE_ONLY;
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
