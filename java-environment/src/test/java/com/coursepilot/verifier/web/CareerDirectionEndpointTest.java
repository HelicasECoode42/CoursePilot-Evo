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
 * listCareerDirections（/api/v1/career-directions）的契约形状、过滤、鉴权和参数校验。
 *
 * 演示数据是 SYNTHETIC，这里也检查它们没有被标成真实来源。
 */
@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
    "coursepilot.service-key=test-key",
    "spring.datasource.url=jdbc:h2:mem:careerdirectiontest;DB_CLOSE_DELAY=-1"
})
class CareerDirectionEndpointTest {

    private static final String KEY = "X-Service-Key";
    private static final String SUBJECT = "X-Subject-Id";
    private static final String PATH = "/api/v1/career-directions";

    /** 契约 CareerDirection 的字段集合（additionalProperties=false）。 */
    private static final Set<String> DIRECTION_FIELDS = Set.of(
        "directionId", "subjectTags", "title", "description", "courseCodes", "sourceRefIds");
    /** 演示种子里允许出现的课程号，与 SeedData.DEMO_COURSE_CODES 一致。 */
    private static final Set<String> DEMO_COURSES = Set.of("CS101", "CS102", "GE101", "CS103");

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ObjectMapper mapper;

    private JsonNode getOk(String path, String... kv) throws Exception {
        var req = get(path).header(KEY, "test-key").header(SUBJECT, "S001");
        for (int i = 0; i < kv.length; i += 2) {
            req = req.param(kv[i], kv[i + 1]);
        }
        MvcResult r = mvc.perform(req).andExpect(status().isOk()).andReturn();
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

    @Test
    @DisplayName("正常返回：envelope 为 OK，data 只有 items，每条字段与契约完全一致")
    void normalResponseHasContractShape() throws Exception {
        JsonNode body = getOk(PATH);
        assertThat(body.get("status").asText()).isEqualTo("OK");
        assertThat(keys(body.get("data"))).isEqualTo(Set.of("items"));

        JsonNode items = body.get("data").get("items");
        assertThat(items.isArray()).isTrue();
        assertThat(items.size()).isEqualTo(3);
        for (JsonNode item : items) {
            assertThat(keys(item)).isEqualTo(DIRECTION_FIELDS);
            assertThat(item.get("subjectTags").size()).isGreaterThan(0);
            assertThat(item.get("sourceRefIds").size()).isGreaterThan(0);
        }
    }

    @Test
    @DisplayName("演示方向全部标注为演示数据，sourceRefIds 带 synthetic: 前缀，不冒充真实来源")
    void seedsAreMarkedSyntheticWithSyntheticSourceRefs() throws Exception {
        for (JsonNode item : getOk(PATH).get("data").get("items")) {
            assertThat(item.get("description").asText()).startsWith("【演示数据】");
            for (JsonNode ref : item.get("sourceRefIds")) {
                assertThat(ref.asText()).startsWith("synthetic:career:");
            }
        }
    }

    @Test
    @DisplayName("方向与课程号关联：courseCodes 只引用演示课程，且「后端」方向需要 CS101")
    void directionsLinkToDemoCourses() throws Exception {
        JsonNode items = getOk(PATH).get("data").get("items");
        for (JsonNode item : items) {
            for (JsonNode code : item.get("courseCodes")) {
                assertThat(DEMO_COURSES).contains(code.asText());
            }
        }
        JsonNode backend = null;
        for (JsonNode item : items) {
            if ("DIR_BACKEND_SYSTEMS".equals(item.get("directionId").asText())) {
                backend = item;
            }
        }
        assertThat(backend).isNotNull();
        assertThat(backend.get("courseCodes").get(0).asText()).isEqualTo("CS101");
    }

    @Test
    @DisplayName("subjectTag 过滤只返回带该标签的方向")
    void subjectTagFiltersDirections() throws Exception {
        JsonNode items = getOk(PATH, "subjectTag", "计算机").get("data").get("items");
        Set<String> ids = new HashSet<>();
        for (JsonNode item : items) {
            ids.add(item.get("directionId").asText());
        }
        assertThat(ids).containsExactlyInAnyOrder("DIR_BACKEND_SYSTEMS", "DIR_SYSTEMS_INFRA");
    }

    @Test
    @DisplayName("没有匹配的 subjectTag 时返回 OK 且 items 为空数组，不是错误")
    void emptyResultIsOkNotError() throws Exception {
        mvc.perform(get(PATH).param("subjectTag", "不存在的标签")
                .header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("OK"))
            .andExpect(jsonPath("$.data.items.length()").value(0));
    }

    @Test
    @DisplayName("缺少 X-Subject-Id 返回 400")
    void missingSubjectIsRejected() throws Exception {
        mvc.perform(get(PATH).header(KEY, "test-key"))
            .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("X-Subject-Id 格式不合法返回 400")
    void malformedSubjectIsRejected() throws Exception {
        mvc.perform(get(PATH).header(KEY, "test-key").header(SUBJECT, "bad id!"))
            .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("没有服务密钥返回 401")
    void requiresServiceKey() throws Exception {
        mvc.perform(get(PATH).header(SUBJECT, "S001"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("subjectTag 为空串返回 400 INVALID_QUERY")
    void emptySubjectTagIsRejected() throws Exception {
        mvc.perform(get(PATH).param("subjectTag", "")
                .header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("INVALID_QUERY"))
            .andExpect(jsonPath("$.issues[0].field").value("subjectTag"));
    }

    @Test
    @DisplayName("subjectTag 超过 80 字符返回 400 INVALID_QUERY")
    void overlongSubjectTagIsRejected() throws Exception {
        mvc.perform(get(PATH).param("subjectTag", "x".repeat(81))
                .header(KEY, "test-key").header(SUBJECT, "S001"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[0].code").value("INVALID_QUERY"));
    }
}
