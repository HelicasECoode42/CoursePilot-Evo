package com.coursepilot.verifier.web;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

/** 端到端：超限请求在认证之前就被 413 拒绝，错误信封与契约一致。 */
@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
    "coursepilot.service-key=test-key",
    "coursepilot.max-json-body-bytes=512",
    "spring.datasource.url=jdbc:h2:mem:requestsizetest;DB_CLOSE_DELAY=-1"
})
class RequestSizeLimitEndpointTest {
    @Autowired private MockMvc mvc;

    @Test
    void oversizeJsonIsRejectedBeforeAuthWithEnvelope() throws Exception {
        String big = "{\"pad\":\"" + "x".repeat(1024) + "\"}";
        mvc.perform(put("/api/v1/school-progress")
                .header("X-Request-Id", "size-1")
                .contentType(MediaType.APPLICATION_JSON).content(big))
            .andExpect(status().isPayloadTooLarge())
            .andExpect(jsonPath("$.status").value("ERROR"))
            .andExpect(jsonPath("$.requestId").value("size-1"))
            .andExpect(jsonPath("$.issues[0].code").value("INVALID_INPUT"));
    }
}
