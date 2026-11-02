package com.coursepilot.verifier.web;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

/**
 * JSON 请求体大小上限（docs/04：输入大小必须有界）。
 *
 * 只约束 JSON 请求；XLSX 上传是 multipart，由 spring.servlet.multipart.* 与
 * CurriculumImportController 的 10 MiB 检查负责。
 *
 * 上限默认 2 MiB，可由 coursepilot.max-json-body-bytes 覆盖。取值依据：学业进度快照
 * 是一棵课程树加已修课程列表，真实数据通常几十 KB，2 MiB 留出约十倍余量。
 *
 * 两条路径：
 * - Content-Length 已知且超限：直接 413，不读请求体。
 * - Content-Length 未知（chunked 等）：最多读 上限+1 字节，超了 413；没超则把缓存的
 *   字节交给下游，保证下游读到的内容与客户端发出的一致。
 *
 * 拒绝时沿用统一 Envelope，错误码取 contracts 已有的 INVALID_INPUT（docs/04 把 413 映射到它）。
 * 放在最高优先级，让超大请求在 ServiceKeyFilter 之前就被挡住，不进入业务路径。
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestSizeLimitFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(RequestSizeLimitFilter.class);
    static final long DEFAULT_MAX_JSON_BODY_BYTES = 2L * 1024 * 1024;

    private final long maxJsonBodyBytes;
    private final ObjectMapper mapper = new ObjectMapper();

    public RequestSizeLimitFilter(
            @Value("${coursepilot.max-json-body-bytes:" + DEFAULT_MAX_JSON_BODY_BYTES + "}")
            long maxJsonBodyBytes) {
        if (maxJsonBodyBytes <= 0) {
            throw new IllegalArgumentException("coursepilot.max-json-body-bytes 必须为正数");
        }
        this.maxJsonBodyBytes = maxJsonBodyBytes;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        if (!isJson(request)) {
            chain.doFilter(request, response);
            return;
        }
        long declared = request.getContentLengthLong();
        if (declared > maxJsonBodyBytes) {
            reject(request, response);
            return;
        }
        if (declared < 0) {
            byte[] body = readBounded(request.getInputStream());
            if (body == null) {
                reject(request, response);
                return;
            }
            chain.doFilter(new CachedBodyRequest(request, body), response);
            return;
        }
        chain.doFilter(request, response);
    }

    private byte[] readBounded(InputStream in) throws IOException {
        int limit = (int) Math.min(maxJsonBodyBytes + 1, Integer.MAX_VALUE - 8);
        byte[] bytes = in.readNBytes(limit);
        return bytes.length > maxJsonBodyBytes ? null : bytes;
    }

    private static boolean isJson(HttpServletRequest request) {
        String type = request.getContentType();
        if (type == null) {
            return false;
        }
        String lower = type.toLowerCase(Locale.ROOT);
        return lower.startsWith(MediaType.APPLICATION_JSON_VALUE)
            || (lower.startsWith("application/") && lower.contains("+json"));
    }

    private void reject(HttpServletRequest request, HttpServletResponse response) throws IOException {
        // 日志只留定位 ID、阶段、状态，不留请求体（AGENTS.md 安全与 Debug）。
        log.warn("request-size stage=json-body status=413 path={} requestId={}",
            request.getRequestURI(), request.getHeader("X-Request-Id"));
        response.setStatus(HttpStatus.PAYLOAD_TOO_LARGE.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        mapper.writeValue(response.getOutputStream(), Envelope.error(
            request.getHeader("X-Request-Id"), "INVALID_INPUT",
            "请求体超过 " + maxJsonBodyBytes + " 字节上限", null, false));
    }

    /** 已读入内存的请求体，重新以流的形式交给下游。 */
    private static final class CachedBodyRequest extends HttpServletRequestWrapper {
        private final byte[] body;

        CachedBodyRequest(HttpServletRequest request, byte[] body) {
            super(request);
            this.body = body;
        }

        @Override
        public ServletInputStream getInputStream() {
            ByteArrayInputStream in = new ByteArrayInputStream(body);
            return new ServletInputStream() {
                @Override public boolean isFinished() { return in.available() == 0; }
                @Override public boolean isReady() { return true; }
                @Override public void setReadListener(ReadListener listener) {
                    throw new UnsupportedOperationException("同步读取即可");
                }
                @Override public int read() { return in.read(); }
            };
        }

        @Override
        public BufferedReader getReader() {
            return new BufferedReader(new InputStreamReader(getInputStream(), StandardCharsets.UTF_8));
        }

        @Override
        public int getContentLength() { return body.length; }

        @Override
        public long getContentLengthLong() { return body.length; }
    }
}
