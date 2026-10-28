package com.coursepilot.verifier.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.coursepilot.verifier.persistence.repo.CurriculumSnapshotRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.ByteArrayOutputStream;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:h2:mem:curriculum-import-http;DB_CLOSE_DELAY=-1",
    "spring.jpa.hibernate.ddl-auto=create-drop",
    "coursepilot.service-key=test-service-key",
    "coursepilot.admin-key=test-admin-key",
    "coursepilot.import.synthetic.enabled=true"
})
@AutoConfigureMockMvc
class CurriculumImportEndpointTest {
    @Autowired private MockMvc mvc;
    @Autowired private CurriculumSnapshotRepository snapshots;
    @Autowired private ObjectMapper objectMapper;

    @Test
    void multipartImportPublishesSyntheticSnapshotThatCanBeListedAndQueried() throws Exception {
        String courseCode = "00123456";
        MockMultipartFile workbook = workbook(courseCode);

        var first = mvc.perform(upload(workbook, "upload-1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("OK"))
            .andExpect(jsonPath("$.data.state").value("PUBLISHED"))
            .andExpect(jsonPath("$.data.reused").value(false))
            .andExpect(jsonPath("$.provenance[0].kind").value("SYNTHETIC"))
            .andReturn();
        String snapshotId = objectMapper.readTree(first.getResponse().getContentAsString())
            .path("data").path("snapshotId").asText();
        String originalRefId = objectMapper.readTree(first.getResponse().getContentAsString())
            .path("provenance").get(0).path("refId").asText();

        var repeated = mvc.perform(upload(workbook(courseCode, false, true), "upload-2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.snapshotId").value(snapshotId))
            .andExpect(jsonPath("$.data.reused").value(true))
            .andExpect(jsonPath("$.provenance[0].kind").value("SYNTHETIC"))
            .andReturn();
        assertFalse(snapshotId.isBlank());
        assertEquals(snapshotId, objectMapper.readTree(repeated.getResponse().getContentAsString())
            .path("data").path("snapshotId").asText());
        assertEquals(originalRefId, objectMapper.readTree(repeated.getResponse().getContentAsString())
            .path("provenance").get(0).path("refId").asText());

        mvc.perform(get("/api/v1/curriculum-snapshots")
                .header("X-Service-Key", "test-service-key")
                .header("X-Request-Id", "list-after-import")
                .header("X-Subject-Id", "teacher:demo"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.items[?(@.snapshotId=='" + snapshotId + "')].sourceKind")
                .value(org.hamcrest.Matchers.hasItem("SYNTHETIC")))
            .andExpect(jsonPath("$.data.items[?(@.snapshotId=='" + snapshotId + "')].sourceValidation")
                .value(org.hamcrest.Matchers.hasItem("SYNTHETIC")));

        mvc.perform(get("/api/v1/courses")
                .param("curriculumSnapshotId", snapshotId)
                .header("X-Service-Key", "test-service-key")
                .header("X-Request-Id", "list-courses")
                .header("X-Subject-Id", "teacher:demo"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.items[0].courseCode").value(courseCode))
            .andExpect(jsonPath("$.data.items[0].name").value("Synthetic course " + courseCode));
    }

    @Test
    void invalidWorkbookIsRejectedWithoutPublishingAnySnapshot() throws Exception {
        long before = snapshots.count();
        MockMultipartFile invalid = new MockMultipartFile(
            "file", "bad.xlsx", MediaType.APPLICATION_OCTET_STREAM_VALUE, new byte[] {1, 2, 3, 4});

        mvc.perform(upload(invalid, "invalid-upload"))
            .andExpect(status().isUnprocessableEntity())
            .andExpect(jsonPath("$.status").value("ERROR"))
            .andExpect(jsonPath("$.issues[0].code").value("INVALID_OOXML"));

        mvc.perform(upload(workbook("SYNBAD001", true), "unknown-rule-upload"))
            .andExpect(status().isUnprocessableEntity())
            .andExpect(jsonPath("$.issues[0].code").value("UNKNOWN_RULE"));

        assertEquals(before, snapshots.count());
    }

    @Test
    void importRequiresAdminKeyAndLoopbackCaller() throws Exception {
        MockMultipartFile workbook = workbook("SYNSEC01");
        mvc.perform(upload(workbook, "missing-admin").header("X-Admin-Key", "wrong"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.issues[0].code").value("ADMIN_KEY_INVALID"));

        mvc.perform(upload(workbook, "remote-caller").with(remoteAddress("192.0.2.10")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.issues[0].code").value("LOCAL_IMPORT_ONLY"));
    }

    @Test
    void clientCannotSupplyARealSourceClassification() throws Exception {
        long before = snapshots.count();
        mvc.perform(upload(workbook("SYNCLAIM01"), "client-source-claim")
                .param("sourceValidation", "VERIFIED"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("UNSUPPORTED_IMPORT_FIELD"));
        assertEquals(before, snapshots.count());
    }

    @Test
    void invalidCourseCodesAreRejectedBeforeSnapshotPublication() throws Exception {
        long before = snapshots.count();
        for (String code : new String[] {"CS 101", "中文101"}) {
            mvc.perform(upload(workbook(code), "bad-code-" + code.hashCode()))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.issues[0].code").value("INVALID_COURSE_CODE"));
        }
        assertEquals(before, snapshots.count());
    }

    private MockHttpServletRequestBuilder upload(MockMultipartFile file, String requestId) {
        return multipart("/api/v1/curriculum-snapshots/import")
            .file(file)
            .param("schemaVersion", "1.0")
            .param("trackId", "cs-general")
            .header("X-Service-Key", "test-service-key")
            .header("X-Admin-Key", "test-admin-key")
            .header("X-Request-Id", requestId)
            .header("X-Subject-Id", "teacher:demo");
    }

    private static RequestPostProcessor remoteAddress(String address) {
        return request -> {
            request.setRemoteAddr(address);
            return request;
        };
    }

    private static MockMultipartFile workbook(String courseCode) throws Exception {
        return workbook(courseCode, false);
    }

    private static MockMultipartFile workbook(String courseCode, boolean unresolvedRule) throws Exception {
        return workbook(courseCode, unresolvedRule, false);
    }

    private static MockMultipartFile workbook(
        String courseCode, boolean unresolvedRule, boolean addUnselectedSheet) throws Exception {
        try (XSSFWorkbook workbook = new XSSFWorkbook(); ByteArrayOutputStream bytes = new ByteArrayOutputStream()) {
            var sheet = workbook.createSheet("计科学");
            sheet.createRow(0).createCell(0).setCellValue("CoursePilot｜2024级培养计划课程清单｜计科学");
            sheet.createRow(4).createCell(0).setCellValue("一、各专业课程类别学分要求");
            var requirementHeader = sheet.createRow(5);
            requirementHeader.createCell(1).setCellValue("课程类别");
            requirementHeader.createCell(2).setCellValue("要求学分");
            requirementHeader.createCell(3).setCellValue("原表学分文本");
            requirementHeader.createCell(4).setCellValue("原表位置");
            var category = sheet.createRow(6);
            category.createCell(0).setCellValue("计科学");
            category.createCell(1).setCellValue("核心课程");
            category.createCell(2).setCellValue(3.0);
            category.createCell(3).setCellValue("3.0");
            category.createCell(4).setCellValue("source!A1");
            var total = sheet.createRow(7);
            total.createCell(0).setCellValue("计科学");
            total.createCell(1).setCellValue("总计");
            total.createCell(2).setCellValue(3.0);
            total.createCell(3).setCellValue("3.0");
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
            course.createCell(1).setCellValue("Synthetic course " + courseCode);
            course.createCell(2).setCellValue(courseCode);
            course.createCell(3).setCellValue("核心课程");
            course.createCell(4).setCellValue(3.0);
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
            if (unresolvedRule) {
                var rule = sheet.createRow(21);
                rule.createCell(0).setCellValue("计科学");
                rule.createCell(1).setCellValue("source!C3");
                rule.createCell(2).setCellValue("未知课程规则");
                rule.createCell(3).setCellValue("规则说明不完整");
                rule.createCell(4).setCellValue("待确认");
                rule.createCell(5).setCellValue("培养规则");
            }
            if (addUnselectedSheet) {
                workbook.createSheet("unselected-sheet").createRow(0).createCell(0)
                    .setCellValue("format-only difference");
            }
            workbook.write(bytes);
            return new MockMultipartFile("file", "synthetic.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", bytes.toByteArray());
        }
    }
}
