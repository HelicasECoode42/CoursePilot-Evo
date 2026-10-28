package com.coursepilot.verifier.web;

import com.coursepilot.verifier.persistence.entity.*;
import com.coursepilot.verifier.persistence.repo.*;
import com.coursepilot.verifier.web.dto.CatalogDtos;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/v1")
public class QueryController {

    private final CourseRepository courseRepo;
    private final CourseOfferingRepository offeringRepo;
    private final CatalogAssembler catalog;

    public QueryController(CourseRepository courseRepo,
                           CourseOfferingRepository offeringRepo,
                           CatalogAssembler catalog) {
        this.courseRepo = courseRepo;
        this.offeringRepo = offeringRepo;
        this.catalog = catalog;
    }

    /** 契约 listCourses：data = { items: Course[], nextCursor }。分页未实现，nextCursor 固定为 null。 */
    @GetMapping("/courses")
    public Envelope<CatalogDtos.CourseList> courses(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestParam(required = false) String category) {
        List<Course> rows = (category == null || category.isBlank())
            ? courseRepo.findAll() : courseRepo.findByCategory(category);
        List<CatalogDtos.Course> items = rows.stream().map(catalog::toCourse).toList();
        return Envelope.ok(requestId, new CatalogDtos.CourseList(items, null));
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
}
