package com.coursepilot.verifier.web;

import com.coursepilot.verifier.persistence.entity.AcademicRecord;
import com.coursepilot.verifier.persistence.entity.Course;
import com.coursepilot.verifier.persistence.entity.CourseOffering;
import com.coursepilot.verifier.persistence.repo.AcademicRecordRepository;
import com.coursepilot.verifier.persistence.repo.CourseOfferingRepository;
import com.coursepilot.verifier.persistence.repo.CourseRepository;
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

    // 补1：查学业记录（真实查库）
    @GetMapping("/academic-records")
    public Envelope<List<AcademicRecord>> records(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader("X-Subject-Id") String subjectId) {
        return Envelope.ok(requestId, recordRepo.findByStudentId(subjectId));
    }

    // 学业记录写入
    @PostMapping("/academic-records")
    public Envelope<AcademicRecord> addRecord(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader("X-Subject-Id") String subjectId, // <-- 加上这一行
        @RequestBody AcademicRecord record) {

        // 为了安全，强制使用 Header 里的 SubjectId
        record.setStudentId(subjectId);
        return Envelope.ok(requestId, recordRepo.save(record));
    }

    // 补3：教师课程
    @GetMapping("/teachers/{teacherName}/courses")
    public Envelope<List<CourseOffering>> teacherCourses(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @PathVariable String teacherName) {
        // 这里简化处理，因为 Repository 里没写按老师查，先用 findAll 过滤
        List<CourseOffering> all = offeringRepo.findAll();
        List<CourseOffering> result = all.stream()
            .filter(o -> teacherName.equals(o.getTeacher()))
            .toList();
        return Envelope.ok(requestId, result);
    }

    // 补4：评价搜索（占位，目前返回空数组，等 A 侧提供表结构）
    @GetMapping("/evaluations")
    public Envelope<List<Object>> searchEvaluations(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestParam String keyword) {
        return Envelope.ok(requestId, List.of());
    }
}
