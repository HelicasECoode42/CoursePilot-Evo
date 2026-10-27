package com.coursepilot.verifier;

import com.coursepilot.verifier.web.dto.AuditDtos;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {"COURSEPILOT_SERVICE_KEY=test-key"}
)
class ModuleIntegrationTest {

    @Autowired
    private TestRestTemplate restTemplate;

    // 统一生成鉴权请求头
    private HttpHeaders getHeaders() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Service-Key", "test-key");
        headers.set("X-Subject-Id", "S001");
        headers.set("X-Request-Id", "test-req-1");
        return headers;
    }

    @Test
    void testAuditEndpointReturnsUnknown() {
        // 使用 SeedData 中真实存在的 academicRecordId
        AuditDtos.AuditRequest request = new AuditDtos.AuditRequest("REC-2026-001", "PLAN_CS_2025");
        HttpEntity<AuditDtos.AuditRequest> entity = new HttpEntity<>(request, getHeaders());

        ResponseEntity<String> response = restTemplate.postForEntity(
            "/api/v1/requirements/audit", entity, String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        String json = response.getBody();

        // 断言返回的 JSON 包含必要字段，而非报错
        assertTrue(json != null && json.contains("\"status\":\"OK\""));
        assertTrue(json.contains("\"unknowns\"") || json.contains("\"items\""));
    }

    @Test
    void testParseTimeEndpoint() {
        String req = "{\"meetingTextRaw\":\"周一第1-2节{第1-16周}\"}";
        HttpEntity<String> entity = new HttpEntity<>(req, getHeaders());

        ResponseEntity<String> response = restTemplate.postForEntity(
            "/api/v1/verification/parse-time", entity, String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertTrue(response.getBody() != null && response.getBody().contains("\"status\":\"OK\""));
    }

    @Test
    void testValidatePlanFindsConflict() {
        String req = """
                {
                    "snapshotId": "SNAP-2025",
                    "term": "2026-Fall",
                    "planItems": [
                        {"courseCode": "CS101", "classId": "O_CS101_01", "meetingTextRaw": "周一第1-2节{第1-16周}"},
                        {"courseCode": "CS102", "classId": "O_CS102_01", "meetingTextRaw": "周一第2-3节{第1-16周}"}
                    ],
                    "hardConstraints": []
                }
                """;
        HttpEntity<String> entity = new HttpEntity<>(req, getHeaders());

        ResponseEntity<String> response = restTemplate.postForEntity(
            "/api/v1/verification/plans/validate", entity, String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        String json = response.getBody();
        // 验证返回的是 INVALID（因为 1-2 和 2-3 在第 2 节冲突）
        assertTrue(json != null && json.contains("\"verdict\":\"INVALID\""));
    }
}
