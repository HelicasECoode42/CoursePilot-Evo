package com.coursepilot.verifier.web;

import com.coursepilot.verifier.persistence.entity.CurriculumCourse;
import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot;
import com.coursepilot.verifier.persistence.repo.CourseOfferingRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumCourseRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumSnapshotRepository;
import com.coursepilot.verifier.persistence.repo.OffsetPageRequest;
import com.coursepilot.verifier.web.dto.CatalogDtos;
import org.springframework.data.domain.Page;
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

    /** 契约 listOfferings：data = { items: CourseOffering[] }。时间由 Java 重新解析 meetingTextRaw。 */
    @GetMapping("/offerings")
    public Envelope<CatalogDtos.OfferingList> offerings(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestParam String courseCode) {
        List<CatalogDtos.CourseOffering> items = offeringRepo.findByCourseCode(courseCode)
            .stream().map(catalog::toOffering).toList();
        return Envelope.ok(requestId, new CatalogDtos.OfferingList(items));
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
