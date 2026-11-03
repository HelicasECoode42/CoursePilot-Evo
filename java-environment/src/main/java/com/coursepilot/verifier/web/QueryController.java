package com.coursepilot.verifier.web;

import com.coursepilot.verifier.persistence.entity.CourseOffering;
import com.coursepilot.verifier.persistence.entity.CurriculumCourse;
import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot;
import com.coursepilot.verifier.persistence.repo.CourseOfferingRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumCourseRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumSnapshotRepository;
import com.coursepilot.verifier.persistence.repo.OffsetPageRequest;
import com.coursepilot.verifier.web.dto.CatalogDtos;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.regex.Pattern;

@RestController
@RequestMapping("/api/v1")
public class QueryController {

    private static final Pattern ID = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$");
    private static final Pattern OFFSET_CURSOR = Pattern.compile("^[0-9]{1,9}$");
    private static final int DEFAULT_LIMIT = 20;
    private static final int MAX_LIMIT = 200;
    /** 契约 listOfferings 未指定 courseCode 时的 limit 上限为 100。 */
    private static final int MAX_OFFERING_LIMIT = 100;
    /**
     * 指定单门 courseCode 时的上限：一门课的全部班次都要能取到（真实快照中单门课可达 186 个班次）。
     * 没有游标，因此这个上限是硬顶；调用方若恰好拿满该数量，须视为可能不完整。
     */
    static final int MAX_COURSE_OFFERING_LIMIT = 1000;

    private final CurriculumSnapshotRepository snapshotRepo;
    private final CurriculumCourseRepository curriculumCourseRepo;
    private final CourseOfferingRepository offeringRepo;
    private final CatalogAssembler catalog;
    private final SubjectGuard subjects;

    public QueryController(CurriculumSnapshotRepository snapshotRepo,
                           CurriculumCourseRepository curriculumCourseRepo,
                           CourseOfferingRepository offeringRepo,
                           CatalogAssembler catalog,
                           SubjectGuard subjects) {
        this.snapshotRepo = snapshotRepo;
        this.curriculumCourseRepo = curriculumCourseRepo;
        this.offeringRepo = offeringRepo;
        this.catalog = catalog;
        this.subjects = subjects;
    }

    /** Courses are visible only through an explicit membership in a published curriculum snapshot. */
    @GetMapping("/courses")
    public Envelope<CatalogDtos.CourseList> courses(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader(value = "X-Subject-Id", required = false) String subjectId,
        @RequestParam String curriculumSnapshotId,
        @RequestParam(required = false) String query,
        @RequestParam(required = false) Integer limit,
        @RequestParam(required = false) String cursor) {
        subjects.require(subjectId);
        requireId("curriculumSnapshotId", curriculumSnapshotId);
        if (query != null && (query.isEmpty() || query.length() > 200)) {
            throw new InvalidQuery("query", "query 长度须在 1 到 200 之间");
        }
        int size = limit == null ? DEFAULT_LIMIT : limit;
        if (size < 1 || size > MAX_LIMIT) {
            throw new InvalidQuery("limit", "limit 须在 1 到 " + MAX_LIMIT + " 之间");
        }
        int offset = offsetOf(cursor);
        CurriculumSnapshot snapshot = snapshotRepo.findById(curriculumSnapshotId)
            .orElseThrow(() -> new UnknownSnapshot(curriculumSnapshotId));
        if (snapshot.getKind() != CurriculumSnapshot.Kind.CURRICULUM
            || snapshot.getState() != CurriculumSnapshot.State.PUBLISHED) {
            throw new UnknownSnapshot(curriculumSnapshotId);
        }

        Page<CurriculumCourse> page = curriculumCourseRepo.findCourses(
            curriculumSnapshotId, query, new OffsetPageRequest(offset, size + 1, null));
        List<CurriculumCourse> fetched = page.getContent();
        boolean hasNext = fetched.size() > size;
        List<CurriculumCourse> selected = fetched.stream().limit(size).toList();
        selected.stream().filter(cc -> !hasCompleteFacts(cc, curriculumSnapshotId)).findFirst()
            .ifPresent(cc -> { throw new UnknownCourseFacts(curriculumSnapshotId, cc.getCourse().getCourseCode()); });
        List<CatalogDtos.Course> items = selected.stream().map(catalog::toCourse).toList();
        String nextCursor = hasNext ? String.valueOf(offset + size) : null;
        List<Envelope.SourceRef> provenance = selected.stream().map(CurriculumCourse::getSourceReference)
            .map(source -> new Envelope.SourceRef(source.getKind(), source.getRefId(),
                source.getSnapshotId(), source.getLocator(), source.getCapturedAt()))
            .distinct().toList();
        return Envelope.ok(requestId, new CatalogDtos.CourseList(items, nextCursor)).withProvenance(provenance);
    }

    /**
     * 契约 listOfferings：data = { items: CourseOffering[] }。
     * 只返回属于 offeringSnapshotId 的班次；快照必须是已发布的 OFFERING，且 curriculumSnapshotId
     * 必须是已发布的 CURRICULUM。时间由 Java 从 meetingTextRaw 重新解析。
     */
    @GetMapping("/offerings")
    public Envelope<CatalogDtos.OfferingList> offerings(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader(value = "X-Subject-Id", required = false) String subjectId,
        @RequestParam String curriculumSnapshotId,
        @RequestParam String offeringSnapshotId,
        @RequestParam(required = false) String courseCode,
        @RequestParam(required = false) Integer limit) {
        subjects.require(subjectId);
        requireId("curriculumSnapshotId", curriculumSnapshotId);
        requireId("offeringSnapshotId", offeringSnapshotId);
        if (courseCode != null) requireId("courseCode", courseCode);
        // 单门课：默认返回该课全部班次（上限 MAX_COURSE_OFFERING_LIMIT）；未指定课程：沿用默认 20、上限 100。
        int maxLimit = courseCode == null ? MAX_OFFERING_LIMIT : MAX_COURSE_OFFERING_LIMIT;
        int size = limit == null ? (courseCode == null ? DEFAULT_LIMIT : MAX_COURSE_OFFERING_LIMIT) : limit;
        if (size < 1 || size > maxLimit) {
            throw new InvalidQuery("limit", "limit 须在 1 到 " + maxLimit + " 之间");
        }
        requirePublished(curriculumSnapshotId, CurriculumSnapshot.Kind.CURRICULUM);
        requirePublished(offeringSnapshotId, CurriculumSnapshot.Kind.OFFERING);

        PageRequest page = PageRequest.of(0, size, Sort.by("offeringId"));
        List<CourseOffering> rows = courseCode == null
            ? offeringRepo.findBySnapshotId(offeringSnapshotId, page)
            : offeringRepo.findBySnapshotIdAndCourseCode(offeringSnapshotId, courseCode, page);
        List<CatalogDtos.CourseOffering> items = rows.stream().map(catalog::toOffering).toList();
        return Envelope.ok(requestId, new CatalogDtos.OfferingList(items));
    }

    private void requirePublished(String snapshotId, CurriculumSnapshot.Kind kind) {
        CurriculumSnapshot snapshot = snapshotRepo.findById(snapshotId)
            .orElseThrow(() -> new UnknownSnapshot(snapshotId));
        if (snapshot.getKind() != kind || snapshot.getState() != CurriculumSnapshot.State.PUBLISHED) {
            throw new UnknownSnapshot(snapshotId);
        }
    }

    private static void requireId(String field, String value) {
        if (value == null || !ID.matcher(value).matches()) {
            throw new InvalidQuery(field, field + " 缺失或格式不合法");
        }
    }

    private static int offsetOf(String cursor) {
        if (cursor == null) return 0;
        if (!OFFSET_CURSOR.matcher(cursor).matches()) {
            throw new InvalidQuery("cursor", "cursor 格式不合法");
        }
        return Integer.parseInt(cursor);
    }

    private static boolean hasCompleteFacts(CurriculumCourse cc, String snapshotId) {
        var source = cc.getSourceReference();
        return cc.getName() != null && !cc.getName().isBlank()
            && cc.getCategory() != null && !cc.getCategory().isBlank()
            && source != null && source.getRefId() != null && !source.getRefId().isBlank()
            && snapshotId.equals(source.getSnapshotId())
            && source.getLocator() != null && !source.getLocator().isBlank()
            && ("CURRICULUM".equals(source.getKind()) || "SYNTHETIC".equals(source.getKind()));
    }
}
