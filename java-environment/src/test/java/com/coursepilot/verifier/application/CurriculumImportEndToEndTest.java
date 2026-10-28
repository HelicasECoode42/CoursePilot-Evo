package com.coursepilot.verifier.application;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.coursepilot.verifier.persistence.repo.CourseRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumCourseRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumImportReceiptRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumSnapshotRepository;
import com.coursepilot.verifier.persistence.repo.RequirementRepository;
import edu.coursepilot.importer.A1WorkbookImporter;
import edu.coursepilot.importer.ImportModels.CurriculumDraft;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** The generated workbook and publisher are explicitly synthetic test data, not a school source. */
@SpringBootTest(
    properties = {
      "spring.datasource.url=jdbc:h2:mem:curriculum-import-e2e;DB_CLOSE_DELAY=-1",
      "spring.jpa.hibernate.ddl-auto=create-drop",
      "coursepilot.service-key=integration-test-key"
    })
class CurriculumImportEndToEndTest {
    private final A1WorkbookImporter importer = new A1WorkbookImporter();
    @Autowired private SyntheticCurriculumPublishPort publisher;
    @Autowired private CurriculumSnapshotRepository snapshots;
    @Autowired private CurriculumCourseRepository memberships;
    @Autowired private CurriculumImportReceiptRepository receipts;
    @Autowired private RequirementRepository requirements;
    @Autowired private CourseRepository courses;
    @Autowired private PlatformTransactionManager transactionManager;

    @TempDir Path tempDir;

    @Test
    void syntheticWorkbookPublishesSnapshotCoursesSourcesAndRequirementsOnce() throws Exception {
        CurriculumDraft draft = draft("CS101", "Synthetic imported CS101");
        assertTrue(draft.publishable());

        var first = importer.publish(draft, publisher);
        var repeated = importer.publish(draft, publisher);

        assertEquals(first.snapshotId(), repeated.snapshotId());
        assertFalse(first.reused());
        assertTrue(repeated.reused());
        var snapshot = snapshots.findById(first.snapshotId()).orElseThrow();
        assertEquals("SYNTHETIC", snapshot.getSourceKind().name());
        assertEquals("SYNTHETIC", snapshot.getSourceValidation().name());

        var membership = memberships
            .findBySnapshot_SnapshotIdAndCourse_CourseCode(first.snapshotId(), "CS101")
            .orElseThrow();
        assertEquals("Synthetic imported CS101", membership.getName());
        assertEquals(3.25, membership.getCredits());
        assertEquals("SYNTHETIC", membership.getSourceReference().getKind());
        assertEquals(first.snapshotId(), membership.getSourceReference().getSnapshotId());
        assertTrue(membership.getSourceReference().getLocator().contains("sha256="));

        var requirement = requirements.findByPlanId(first.snapshotId()).getFirst();
        assertEquals(3.25, requirement.getRequiredCredits());
        assertNotNull(requirement.getSourceReference());
        assertEquals(first.snapshotId(), requirement.getSourceReference().getSnapshotId());
        assertEquals("Java 程序设计", courses.findById("CS101").orElseThrow().getName());
        assertEquals(1, receipts.count());
        assertEquals(1, memberships.findBySnapshot_SnapshotIdAndCourse_CourseCodeIn(
            first.snapshotId(), java.util.List.of("CS101")).size());
    }

    @Test
    void failedTransactionLeavesNoPartialSnapshotOrCourseData() throws Exception {
        CurriculumDraft draft = draft("CS102", "Synthetic rollback course");
        TransactionTemplate transaction = new TransactionTemplate(transactionManager);

        assertThrows(
            AbortImport.class,
            () -> transaction.execute(status -> {
                var result = importer.publish(draft, publisher);
                assertTrue(snapshots.existsById(result.snapshotId()));
                throw new AbortImport();
            }));

        String snapshotId = "SYN_" + draft.idempotencyKey().substring(0, 60);
        assertFalse(snapshots.existsById(snapshotId));
        assertFalse(receipts.existsById(draft.idempotencyKey()));
        assertTrue(requirements.findByPlanId(snapshotId).isEmpty());
        assertTrue(memberships.findBySnapshot_SnapshotIdAndCourse_CourseCodeIn(
            snapshotId, java.util.List.of("CS102")).isEmpty());
    }

    private CurriculumDraft draft(String courseCode, String name) throws Exception {
        Path workbook = tempDir.resolve(courseCode + ".xlsx");
        writeWorkbook(workbook, courseCode, name);
        return importer.prepare(workbook, "cs-general");
    }

    private void writeWorkbook(Path path, String courseCode, String name) throws Exception {
        try (XSSFWorkbook workbook = new XSSFWorkbook()) {
            var sheet = workbook.createSheet("计科学");
            sheet.createRow(0).createCell(0)
                .setCellValue("CoursePilot｜2024级培养计划课程清单｜计科学");
            sheet.createRow(4).createCell(0).setCellValue("一、各专业课程类别学分要求");
            var requirementHeader = sheet.createRow(5);
            requirementHeader.createCell(1).setCellValue("课程类别");
            requirementHeader.createCell(2).setCellValue("要求学分");
            requirementHeader.createCell(3).setCellValue("原表学分文本");
            requirementHeader.createCell(4).setCellValue("原表位置");
            var category = sheet.createRow(6);
            category.createCell(0).setCellValue("计科学");
            category.createCell(1).setCellValue("核心课程");
            category.createCell(2).setCellValue(3.25);
            category.createCell(3).setCellValue("3.25");
            category.createCell(4).setCellValue("source!A1");
            var total = sheet.createRow(7);
            total.createCell(0).setCellValue("计科学");
            total.createCell(1).setCellValue("总计");
            total.createCell(2).setCellValue(3.25);
            total.createCell(3).setCellValue("3.25");

            sheet.createRow(15).createCell(0).setCellValue("二、总体课程与课程组明细");
            var detailHeader = sheet.createRow(16);
            detailHeader.createCell(0).setCellValue("专业路径");
            detailHeader.createCell(1).setCellValue("课程名称/课程组");
            detailHeader.createCell(2).setCellValue("课程编号（原文或规则）");
            detailHeader.createCell(3).setCellValue("课程类别");
            detailHeader.createCell(4).setCellValue("学分");
            detailHeader.createCell(5).setCellValue("建议修读学期");
            detailHeader.createCell(6).setCellValue("原表位置");
            detailHeader.createCell(8).setCellValue("记录性质");
            var course = sheet.createRow(17);
            course.createCell(0).setCellValue("计科学");
            course.createCell(1).setCellValue(name);
            course.createCell(2).setCellValue(courseCode);
            course.createCell(3).setCellValue("核心课程");
            course.createCell(4).setCellValue(3.25);
            course.createCell(5).setCellValue("第一学年");
            course.createCell(6).setCellValue("source!B2");
            course.createCell(8).setCellValue("课程明细");

            sheet.createRow(19).createCell(0).setCellValue("三、备注：无法解释或需确认的规则");
            var ruleHeader = sheet.createRow(20);
            ruleHeader.createCell(1).setCellValue("原表位置");
            ruleHeader.createCell(2).setCellValue("涉及对象/规则");
            ruleHeader.createCell(3).setCellValue("原表说明或待核问题");
            ruleHeader.createCell(4).setCellValue("当前解释与处理状态");
            ruleHeader.createCell(5).setCellValue("来源类型");
            try (OutputStream output = Files.newOutputStream(path)) {
                workbook.write(output);
            }
        }
    }

    private static final class AbortImport extends RuntimeException {}
}
