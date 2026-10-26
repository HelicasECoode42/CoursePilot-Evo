package com.coursepilot.verifier.web;

import com.coursepilot.verifier.persistence.entity.*;
import com.coursepilot.verifier.persistence.repo.*;
import com.coursepilot.verifier.web.dto.CatalogDtos;
import com.coursepilot.verifier.web.dto.RecordDtos;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/v1")
public class QueryController {

    private final CourseRepository courseRepo;
    private final CourseOfferingRepository offeringRepo;
    private final SubjectGuard subjects;
    private final CatalogAssembler catalog;

    public QueryController(CourseRepository courseRepo,
                           CourseOfferingRepository offeringRepo,
                           SubjectGuard subjects,
                           CatalogAssembler catalog) {
        this.courseRepo = courseRepo;
        this.offeringRepo = offeringRepo;
        this.subjects = subjects;
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

    /**
     * 契约端点 listAcademicRecords。
     *
     * 范围由 X-Subject-Id 决定，**不接受** studentId 查询参数——让调用方自报
     * 要查谁的成绩单，等于没有对象级授权（b-verifier.md B-F6）。
     * 契约里这个端点也只声明了 X-Request-Id 与 X-Subject-Id 两个参数。
     *
     * 当前实体缺记录级的 curriculumSnapshotId / createdAt / revision，凑不出
     * 一份合契约的 AcademicRecord，所以返回空 items 并以 UNKNOWN 说明缺口，
     * 而不是拿默认值填出一份看起来成立的记录。契约对 items 为空的定义是
     * 「该主体尚无学业记录」，所以这里必须用 UNKNOWN 封套把两种情况区分开。
     */
    @GetMapping("/academic-records")
    public Envelope<RecordDtos.RecordList> records(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader(value = "X-Subject-Id", required = false) String subjectId) {
        subjects.require(subjectId);
        return Envelope.unknown(requestId, new RecordDtos.RecordList(List.of()),
            "学业记录聚合实体尚未建模（缺 curriculumSnapshotId / createdAt / revision），"
                + "无法返回合契约的记录；空 items 不代表该主体没有已修课程");
    }

    /**
     * 契约端点 getAcademicRecord。先判归属再谈返回：不属于当前主体的记录
     * 一律按不可见处理（404），不回 403，避免暴露「这个 ID 存在」。
     */
    @GetMapping("/academic-records/{recordId}")
    public Envelope<RecordDtos.AcademicRecord> record(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader(value = "X-Subject-Id", required = false) String subjectId,
        @PathVariable String recordId) {
        subjects.requireOwnRecord(subjectId, recordId);
        return Envelope.unknown(requestId, null,
            "学业记录聚合实体尚未建模，无法返回合契约的记录内容");
    }
}
