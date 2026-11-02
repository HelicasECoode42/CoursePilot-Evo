package com.coursepilot.verifier.web;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import jakarta.servlet.ServletException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

/** 单元层：不依赖 Spring 上下文，直接验证过滤器的两条路径。 */
class RequestSizeLimitFilterUnitTest {

    private static final byte[] SMALL = "{\"a\":1}".getBytes(StandardCharsets.UTF_8);

    private static MockHttpServletRequest jsonRequest(byte[] body, boolean lengthKnown) {
        MockHttpServletRequest request = lengthKnown
            ? new MockHttpServletRequest("PUT", "/api/v1/school-progress")
            : new MockHttpServletRequest("PUT", "/api/v1/school-progress") {
                // 模拟 chunked：容器不给 Content-Length。
                @Override public long getContentLengthLong() { return -1L; }
                @Override public int getContentLength() { return -1; }
            };
        request.setContentType(MediaType.APPLICATION_JSON_VALUE);
        request.setContent(body);
        return request;
    }

    @Test
    void rejectsKnownOversizeWithoutReadingBody() throws Exception {
        RequestSizeLimitFilter filter = new RequestSizeLimitFilter(16);
        MockHttpServletRequest request = jsonRequest(new byte[64], true);
        MockHttpServletResponse response = new MockHttpServletResponse();
        MockFilterChain chain = new MockFilterChain();
        filter.doFilter(request, response, chain);
        assertEquals(413, response.getStatus());
        assertEquals(null, chain.getRequest());
        assertEquals("INVALID_INPUT", extractCode(response.getContentAsString()));
    }

    @Test
    void passesKnownSmallBodyThrough() throws Exception {
        RequestSizeLimitFilter filter = new RequestSizeLimitFilter(16);
        MockHttpServletRequest request = jsonRequest(SMALL, true);
        MockHttpServletResponse response = new MockHttpServletResponse();
        MockFilterChain chain = new MockFilterChain();
        filter.doFilter(request, response, chain);
        assertNotEquals(413, response.getStatus());
        assertEquals(request, chain.getRequest());
    }

    @Test
    void boundsUnknownLengthAndRejectsOversize() throws Exception {
        RequestSizeLimitFilter filter = new RequestSizeLimitFilter(16);
        MockHttpServletRequest request = jsonRequest(new byte[17], false);
        MockHttpServletResponse response = new MockHttpServletResponse();
        MockFilterChain chain = new MockFilterChain();
        filter.doFilter(request, response, chain);
        assertEquals(413, response.getStatus());
        assertEquals(null, chain.getRequest());
    }

    @Test
    void replaysUnknownLengthBodyToDownstreamUnchanged() throws Exception {
        RequestSizeLimitFilter filter = new RequestSizeLimitFilter(16);
        MockHttpServletRequest request = jsonRequest(SMALL, false);
        MockHttpServletResponse response = new MockHttpServletResponse();
        final byte[][] seen = new byte[1][];
        MockFilterChain chain = new MockFilterChain() {
            @Override
            public void doFilter(jakarta.servlet.ServletRequest req, jakarta.servlet.ServletResponse res)
                    throws IOException, ServletException {
                seen[0] = req.getInputStream().readAllBytes();
            }
        };
        filter.doFilter(request, response, chain);
        assertArrayEquals(SMALL, seen[0]);
    }

    @Test
    void ignoresNonJsonRequests() throws Exception {
        RequestSizeLimitFilter filter = new RequestSizeLimitFilter(4);
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/v1/x");
        request.setContentType(MediaType.MULTIPART_FORM_DATA_VALUE);
        request.setContent(new byte[100]);
        MockHttpServletResponse response = new MockHttpServletResponse();
        MockFilterChain chain = new MockFilterChain();
        filter.doFilter(request, response, chain);
        assertEquals(request, chain.getRequest());
    }

    @Test
    void rejectsNonPositiveLimit() {
        org.junit.jupiter.api.Assertions.assertThrows(IllegalArgumentException.class,
            () -> new RequestSizeLimitFilter(0));
    }

    private static String extractCode(String json) {
        int i = json.indexOf("\"code\":\"");
        if (i < 0) return "";
        int start = i + 8;
        return json.substring(start, json.indexOf('"', start));
    }
}
