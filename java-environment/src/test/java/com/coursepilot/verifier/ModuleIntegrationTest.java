package com.coursepilot.verifier;

import com.coursepilot.verifier.web.dto.AuditDto;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.*;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

// 模拟环境变量：告诉测试类，密钥是 test-key
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
    "COURSEPILOT_SERVICE_KEY=test-key"
})
class ModuleIntegrationTest {

    @Autowired
    private TestRestTemplate restTemplate;

    // 提取一个生成请求头的方法
    private HttpHeaders getHeaders() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Service-Key", "test-key"); // 匹配环境变量
        headers.set("X-Subject-Id", "S001");      // 必填的学号
        headers.set("X-Request-Id", "test-req-1");
        return headers;
    }

    @Test
    void testAuditEndpointReturnsUnknown() {
        AuditDto.AuditRequest request = new AuditDto.AuditRequest("S001", "PLAN_CS_2025");
        HttpEntity<AuditDto.AuditRequest> entity = new HttpEntity<>(request, getHeaders());

        ResponseEntity<String> response = restTemplate.postForEntity(
            "/api/v1/requirements/audit", entity, String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        String json = response.getBody();
        assertTrue(json != null && json.contains("\"status\":\"OK\""));
        assertTrue(json.contains("\"status\":\"UNKNOWN\""));
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
                    "snapshotId": "snap-123",
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
        // 验证返回的是 INVALID（因为 1-2 和 2-3 在第2节冲突）
        assertTrue(json != null && json.contains("\"verdict\":\"INVALID\""));
    }
}

