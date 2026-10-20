package com.coursepilot.verifier.web;

import com.coursepilot.verifier.persistence.entity.*;
import com.coursepilot.verifier.persistence.repo.*;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/v1")
public class QueryController {

    private final CourseRepository courseRepo;
    private final CourseOfferingRepository offeringRepo;
    private final AcademicRecordRepository recordRepo;

    public QueryController(CourseRepository courseRepo,
                           CourseOfferingRepository offeringRepo,
                           AcademicRecordRepository recordRepo) {
        this.courseRepo = courseRepo;
        this.offeringRepo = offeringRepo;
        this.recordRepo = recordRepo;
    }

    @GetMapping("/courses")
    public Envelope<List<Course>> courses(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestParam(required = false) String category) {
        List<Course> items = (category == null || category.isBlank())
            ? courseRepo.findAll() : courseRepo.findByCategory(category);
        return Envelope.ok(requestId, items);
    }

    @GetMapping("/offerings")
    public Envelope<List<CourseOffering>> offerings(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestParam String courseCode) {
        return Envelope.ok(requestId, offeringRepo.findByCourseCode(courseCode));
    }

    @GetMapping("/academic-records")
    public Envelope<List<AcademicRecord>> records(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestParam String studentId) {
        return Envelope.ok(requestId, recordRepo.findByStudentId(studentId));
    }
}
