package com.coursepilot.verifier.web;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.HashSet;
import java.util.Iterator;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * listTeacherCourseOptions（/api/v1/teacher-course-options）与 searchReviews（/api/v1/reviews/search）
 * 的契约形状、三条硬规则和鉴权/参数校验。
 */
@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
    "coursepilot.service-key=test-key",
    "spring.datasource.url=jdbc:h2:mem:teacherreviewtest;DB_CLOSE_DELAY=-1"
})
class TeacherReviewEndpointTest {

    private static final String KEY = "X-Service-Key";
    private static final String SUBJECT = "X-Subject-Id";
    private static final String OPTIONS = "/api/v1/teacher-course-options";
    private static final String REVIEWS = "/api/v1/reviews/search";
    private static final String SNAPSHOT = "PLAN_CS_2025";

    /** 契约 TeacherCourseOption 的字段集合，与 domain.schema.json 必填项一致（additionalProperties=false）。 */
    private static final Set<String> OPTION_FIELDS = Set.of(
        "courseCode", "teacherKey", "teacherDisplayName", "availability", "reviewNoteIds", "classIds");
    /** 契约 ReviewNote 的字段集合（additionalProperties=false）。 */
    private static final Set<String> REVIEW_FIELDS = Set.of(
        "reviewNoteId", "courseCode", "teacherKey", "termId", "sourceKind", "publishedAt",
        "sourceUrl", "excerpt", "teacherDisplayName", "dimensions", "matchStatus", "sourceRefId");

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ObjectMapper mapper;

    private JsonNode getJson(String path) throws Exception {
        MvcResult r = mvc.perform(get(path).header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(status().isOk())
            .andReturn();
        return mapper.readTree(r.getResponse().getContentAsString());
    }

    private static Set<String> keys(JsonNode node) {
        Set<String> out = new HashSet<>();
        Iterator<String> it = node.fieldNames();
        while (it.hasNext()) {
            out.add(it.next());
        }
        return out;
    }

    private JsonNode allOptions() throws Exception {
        return getJson(OPTIONS + "?curriculumSnapshotId=" + SNAPSHOT + "&limit=100").get("data").get("items");
    }

    @Test
    @DisplayName("teacher-course-options 的 data 是 {items, nextCursor}，不是裸数组")
    void optionsDataShape() throws Exception {
        JsonNode data = getJson(OPTIONS + "?curriculumSnapshotId=" + SNAPSHOT).get("data");
        assertThat(keys(data)).isEqualTo(Set.of("items", "nextCursor"));
        assertThat(data.get("items").isArray()).isTrue();
        assertThat(data.get("nextCursor").isNull()).isTrue();
    }

    @Test
    @DisplayName("teacher-course-options 每个条目字段与契约完全一致，没有 id 之类的内部字段")
    void optionItemsHaveExactContractFields() throws Exception {
        JsonNode items = allOptions();
        assertThat(items.size()).isGreaterThan(0);
        for (JsonNode item : items) {
            assertThat(keys(item)).isEqualTo(OPTION_FIELDS);
        }
    }

    @Test
    @DisplayName("searchReviews 的 data 是 {items}，每条字段与契约完全一致，没有实体主键或内部字段")
    void reviewItemsHaveExactContractFields() throws Exception {
        JsonNode data = getJson(REVIEWS + "?courseCode=CS101").get("data");
        assertThat(keys(data)).isEqualTo(Set.of("items", "nextCursor"));
        assertThat(data.get("items").size()).isGreaterThan(0);
        for (JsonNode item : data.get("items")) {
            assertThat(keys(item)).isEqualTo(REVIEW_FIELDS);
        }
    }

    @Test
    void reviewsCanBeReadAcrossPagesWithoutDuplicates() throws Exception {
        JsonNode first = getJson(REVIEWS + "?courseCode=CS101&limit=1").get("data");
        assertThat(first.get("nextCursor").asText()).isEqualTo("1");
        JsonNode second = getJson(REVIEWS + "?courseCode=CS101&limit=1&cursor=1").get("data");
        assertThat(second.get("items").size()).isEqualTo(1);
        assertThat(second.get("items").get(0).get("reviewNoteId").asText())
            .isNotEqualTo(first.get("items").get(0).get("reviewNoteId").asText());
    }

    @Test
    @DisplayName("matchStatus 三种取值都能出现：已匹配、课程级、未核验")
    void matchStatusAllThreeValuesAppear() throws Exception {
        Set<String> seen = new HashSet<>();
        for (String course : new String[] {"CS101", "CS102", "CS103"}) {
            for (JsonNode n : getJson(REVIEWS + "?courseCode=" + course + "&limit=10").get("data").get("items")) {
                seen.add(n.get("matchStatus").asText());
            }
        }
        assertThat(seen).containsExactlyInAnyOrder("COURSE_TEACHER_MATCHED", "COURSE_ONLY", "UNVERIFIED");
    }

    @Test
    @DisplayName("availability 出现 HISTORICAL_ONLY 与 UNKNOWN，且当前没有任何 CURRENT_VERIFIED")
    void availabilityHasNoCurrentVerifiedAndCoversOthers() throws Exception {
        Set<String> seen = new HashSet<>();
        for (JsonNode item : allOptions()) {
            seen.add(item.get("availability").asText());
        }
        assertThat(seen).containsExactlyInAnyOrder("HISTORICAL_ONLY", "UNKNOWN");
    }

    @Test
    @DisplayName("教师 T_WANG 没有任何历史评价，判为 UNKNOWN，且 envelope 为业务 UNKNOWN")
    void unknownAvailabilityUsesUnknownEnvelope() throws Exception {
        mvc.perform(get(OPTIONS).param("curriculumSnapshotId", SNAPSHOT).param("courseCode", "CS103")
                .header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("UNKNOWN"))
            .andExpect(jsonPath("$.data.items[0].teacherKey").value("T_WANG"))
            .andExpect(jsonPath("$.data.items[0].availability").value("UNKNOWN"));
    }

    @Test
    @DisplayName("声明了当期学期但来源是 SYNTHETIC 的教师不会判为 CURRENT_VERIFIED，有历史则 HISTORICAL_ONLY")
    void syntheticCurrentTermIsNotCurrentVerified() throws Exception {
        // CS102 的 T_LI 绑定了 2025-FALL，但来源是 SYNTHETIC，并且有历史评价。
        mvc.perform(get(OPTIONS).param("curriculumSnapshotId", SNAPSHOT).param("courseCode", "CS102")
                .header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(jsonPath("$.data.items[0].teacherKey").value("T_LI"))
            .andExpect(jsonPath("$.data.items[0].availability").value("HISTORICAL_ONLY"))
            .andExpect(jsonPath("$.data.items[0].classIds[0]").value("O_CS102_01"));
    }

    @Test
    @DisplayName("按教师检索时，不把 teacherKey 为空的课程级评价挂到该教师名下")
    void teacherSearchExcludesCourseOnlyNotes() throws Exception {
        JsonNode items = getJson(REVIEWS + "?courseCode=CS101&teacherKey=T_ZHANG").get("data").get("items");
        assertThat(items.size()).isEqualTo(1);
        assertThat(items.get(0).get("reviewNoteId").asText()).isEqualTo("R_CS101_T_ZHANG_01");
        assertThat(items.get(0).get("matchStatus").asText()).isEqualTo("COURSE_TEACHER_MATCHED");
    }

    @Test
    @DisplayName("评价匹配不上教师：teacherKey 为 null 且 matchStatus 不是 COURSE_TEACHER_MATCHED")
    void unmatchedTeacherNotesHaveNullTeacherKey() throws Exception {
        JsonNode items = getJson(REVIEWS + "?courseCode=CS103").get("data").get("items");
        assertThat(items.size()).isEqualTo(1);
        JsonNode note = items.get(0);
        assertThat(note.get("teacherKey").isNull()).isTrue();
        assertThat(note.get("matchStatus").asText()).isNotEqualTo("COURSE_TEACHER_MATCHED");
        assertThat(note.get("matchStatus").asText()).isEqualTo("COURSE_ONLY");
    }

    @Test
    @DisplayName("绑定里没有的教师，即使评价写了他的 teacherKey 也只能是 UNVERIFIED，不能算已匹配")
    void unboundTeacherIsUnverifiedNotMatched() throws Exception {
        JsonNode items = getJson(REVIEWS + "?courseCode=CS102&teacherKey=T_ZHANG").get("data").get("items");
        assertThat(items.size()).isEqualTo(1);
        assertThat(items.get(0).get("teacherKey").asText()).isEqualTo("T_ZHANG");
        assertThat(items.get(0).get("matchStatus").asText()).isEqualTo("UNVERIFIED");
    }

    @Test
    @DisplayName("维度原样保留为契约枚举数组，不合并成一个分数")
    void dimensionsStaySeparate() throws Exception {
        JsonNode items = getJson(REVIEWS + "?courseCode=CS101&teacherKey=T_ZHANG").get("data").get("items");
        assertThat(items.get(0).get("dimensions")).hasSize(2);
        assertThat(items.get(0).get("dimensions").get(0).asText()).isEqualTo("GRADING");
        assertThat(items.get(0).get("dimensions").get(1).asText()).isEqualTo("WORKLOAD");
    }

    @Test
    @DisplayName("演示数据全部是 SYNTHETIC，sourceUrl 为空，sourceRefId 指向库内记录")
    void seedsAreSyntheticWithoutUrls() throws Exception {
        for (String course : new String[] {"CS101", "CS102", "CS103"}) {
            for (JsonNode n : getJson(REVIEWS + "?courseCode=" + course + "&limit=10").get("data").get("items")) {
                assertThat(n.get("sourceKind").asText()).isEqualTo("SYNTHETIC");
                assertThat(n.get("sourceUrl").isNull()).isTrue();
                assertThat(n.get("sourceRefId").asText()).isEqualTo("review:" + n.get("reviewNoteId").asText());
            }
        }
    }

    @Test
    @DisplayName("没有该快照的教师绑定时 items 为空，仍是 OK（业务上没有数据，不是错误）")
    void emptySnapshotIsOkWithEmptyItems() throws Exception {
        mvc.perform(get(OPTIONS).param("curriculumSnapshotId", "PLAN_CS_2024")
                .header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("OK"))
            .andExpect(jsonPath("$.data.items.length()").value(0));
    }

    @Test
    @DisplayName("开课快照不是培养方案，选项查询返回 422")
    void offeringSnapshotIsUnknownSnapshot() throws Exception {
        mvc.perform(get(OPTIONS).param("curriculumSnapshotId", "OFFER_2025_FALL")
                .header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(status().isUnprocessableEntity());
    }

    @Test
    @DisplayName("偏移量游标可以翻完全部教师，最后一页 nextCursor 为 null")
    void optionsPaginateByOffset() throws Exception {
        JsonNode first = getJson(OPTIONS + "?curriculumSnapshotId=" + SNAPSHOT + "&limit=2");
        assertThat(first.get("data").get("items").size()).isEqualTo(2);
        assertThat(first.get("data").get("nextCursor").asText()).isEqualTo("2");

        JsonNode second = getJson(OPTIONS + "?curriculumSnapshotId=" + SNAPSHOT + "&limit=2&cursor=2");
        assertThat(second.get("data").get("items").size()).isEqualTo(1);
        assertThat(second.get("data").get("nextCursor").isNull()).isTrue();
    }

    @Test
    @DisplayName("teacher-course-options 没有服务密钥返回 401")
    void optionsRequireServiceKey() throws Exception {
        mvc.perform(get(OPTIONS).param("curriculumSnapshotId", SNAPSHOT).header(SUBJECT, "S001"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("reviews/search 没有服务密钥返回 401")
    void reviewsRequireServiceKey() throws Exception {
        mvc.perform(get(REVIEWS).param("courseCode", "CS101").header(SUBJECT, "S001"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("teacher-course-options 缺必填的 curriculumSnapshotId 返回 400")
    void optionsRequireSnapshotId() throws Exception {
        mvc.perform(get(OPTIONS).header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("MISSING_PARAMETER"));
    }

    @Test
    @DisplayName("reviews/search 缺必填的 courseCode 返回 400")
    void reviewsRequireCourseCode() throws Exception {
        mvc.perform(get(REVIEWS).header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("MISSING_PARAMETER"));
    }

    @Test
    @DisplayName("limit 超出契约范围、cursor 非数字、teacherKey 含非法字符都返回 400 INVALID_QUERY")
    void invalidQueryValuesAreRejected() throws Exception {
        mvc.perform(get(REVIEWS).param("courseCode", "CS101").param("limit", "11")
                .header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("INVALID_QUERY"));
        mvc.perform(get(OPTIONS).param("curriculumSnapshotId", SNAPSHOT).param("cursor", "abc")
                .header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("INVALID_QUERY"));
        mvc.perform(get(REVIEWS).param("courseCode", "CS101").param("teacherKey", "张老师")
                .header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("INVALID_QUERY"));
    }

    @Test
    @DisplayName("缺少 X-Subject-Id 返回 400")
    void missingSubjectIsRejected() throws Exception {
        mvc.perform(get(REVIEWS).param("courseCode", "CS101").header(KEY, "test-key"))
            .andExpect(status().isBadRequest());
    }
}
