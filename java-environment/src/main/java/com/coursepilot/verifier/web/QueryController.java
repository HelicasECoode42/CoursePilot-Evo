package com.coursepilot.verifier.web;

import com.coursepilot.verifier.persistence.entity.*;
import com.coursepilot.verifier.persistence.repo.*;
import com.coursepilot.verifier.web.dto.TranscriptDto;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/v1")
public class QueryController {

    private final CourseRepository courseRepo;
    private final CourseOfferingRepository offeringRepo;
    private final TranscriptRepository transcriptRepo;
    private final ReviewNoteRepository reviewRepo;

    public QueryController(CourseRepository courseRepo, CourseOfferingRepository offeringRepo,
                           TranscriptRepository transcriptRepo, ReviewNoteRepository reviewRepo) {
        this.courseRepo = courseRepo;
        this.offeringRepo = offeringRepo;
        this.transcriptRepo = transcriptRepo;
        this.reviewRepo = reviewRepo;
    }

    @GetMapping("/courses")
    public Envelope<List<Course>> courses(@RequestHeader(value = "X-Request-Id", required = false) String requestId,
                                          @RequestParam(required = false) String category) {
        List<Course> items = (category == null || category.isBlank()) ? courseRepo.findAll() : courseRepo.findByCategory(category);
        return Envelope.ok(requestId, items);
    }

    @GetMapping("/offerings")
    public Envelope<List<CourseOffering>> offerings(@RequestHeader(value = "X-Request-Id", required = false) String requestId,
                                                    @RequestParam String courseCode) {
        return Envelope.ok(requestId, offeringRepo.findByCourseCode(courseCode));
    }

    @GetMapping("/academic-records")
    public Envelope<List<TranscriptDto>> getTranscripts(@RequestHeader(value = "X-Request-Id", required = false) String requestId,
                                                        @RequestHeader("X-Subject-Id") String subjectId) {
        Transcript t = transcriptRepo.findByStudentId(subjectId);
        if (t == null) return Envelope.ok(requestId, List.of());

        List<TranscriptDto.CompletedCourseDto> courses = t.getCompletedCourses().stream()
            .map(c -> new TranscriptDto.CompletedCourseDto(c.getCourseCode(), c.getCourseName(), c.getCredits(), c.isPassed()))
            .toList();

        TranscriptDto dto = new TranscriptDto(t.getAcademicRecordId(), t.getRevision(), t.getCurriculumSnapshotId(), courses, t.isTranscriptComplete(), t.getSourceKind(), t.getCreatedAt());
        return Envelope.ok(requestId, List.of(dto));
    }

    @GetMapping("/teachers")
    public Envelope<List<String>> listTeachers(@RequestHeader(value = "X-Request-Id", required = false) String requestId,
                                               @RequestParam String courseCode) {
        List<String> teachers = offeringRepo.findByCourseCode(courseCode).stream().map(CourseOffering::getTeacher).distinct().toList();
        return Envelope.ok(requestId, teachers);
    }

    @GetMapping("/evaluations")
    public Envelope<List<ReviewNote>> searchReviews(@RequestHeader(value = "X-Request-Id", required = false) String requestId,
                                                    @RequestParam String teacherName, @RequestParam String courseCode,
                                                    @RequestParam(defaultValue = "10") int limit) {
        List<ReviewNote> notes = reviewRepo.findByTeacherNameAndCourseCode(teacherName, courseCode);
        return Envelope.ok(requestId, notes.stream().limit(limit).toList());
    }
}
