package com.coursepilot.verifier.web;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

/**
 * 服务密钥校验：/api/v1/** 只接受已认证的 Python 服务（模块 C）。
 *
 * contracts/java.openapi.json 声明 security: serviceKey（X-Service-Key 头）。
 * docs/16 要求 Java 只信任已认证服务、不透传浏览器自报身份，所以这道校验是
 * SubjectGuard 能成立的前提：先证明调用方是 C，X-Subject-Id 才有意义。
 *
 * docs/04：密钥仅在环境变量，不进仓库。所以这里没有内置默认值——
 * 没配 COURSEPILOT_SERVICE_KEY 时整个 /api/v1 以 503 拒服务，而不是放行。
 * 失败路径只记录阶段和状态，不记录密钥本身，也不记录比对到的值。
 */
@Component
public class ServiceKeyFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(ServiceKeyFilter.class);
    private static final String HEADER = "X-Service-Key";

    private final String expectedKey;
    private final ObjectMapper mapper = new ObjectMapper();

    public ServiceKeyFilter(@Value("${coursepilot.service-key:}") String expectedKey) {
        this.expectedKey = expectedKey == null ? "" : expectedKey.trim();
        if (this.expectedKey.isEmpty()) {
            log.warn("未配置 COURSEPILOT_SERVICE_KEY，/api/v1 将一律以 503 拒服务");
        }
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith("/api/v1/");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        if (expectedKey.isEmpty()) {
            // 没有密钥就无法分辨调用方，这时放行等于默认开放，所以报依赖未配置。
            deny(request, response, HttpStatus.SERVICE_UNAVAILABLE,
                "SERVICE_KEY_NOT_CONFIGURED", "服务端未配置服务密钥，拒绝提供接口", true);
            return;
        }
        String presented = request.getHeader(HEADER);
        if (presented == null || !constantTimeEquals(expectedKey, presented)) {
            deny(request, response, HttpStatus.UNAUTHORIZED,
                "SERVICE_KEY_INVALID", "缺少或错误的 " + HEADER, false);
            return;
        }
        chain.doFilter(request, response);
    }

    /** 逐字节比较且不提前返回，避免用响应时间猜密钥。 */
    private static boolean constantTimeEquals(String expected, String presented) {
        byte[] a = expected.getBytes(StandardCharsets.UTF_8);
        byte[] b = presented.getBytes(StandardCharsets.UTF_8);
        return java.security.MessageDigest.isEqual(a, b);
    }

    private void deny(HttpServletRequest request, HttpServletResponse response,
                      HttpStatus status, String code, String message, boolean retryable)
        throws IOException {
        // 日志只留定位 ID、阶段、状态，不留密钥、不留请求体（AGENTS.md 安全与 Debug）。
        log.warn("auth stage=service-key status={} path={} requestId={}",
            status.value(), request.getRequestURI(), request.getHeader("X-Request-Id"));
        response.setStatus(status.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        mapper.writeValue(response.getOutputStream(),
            Envelope.error(request.getHeader("X-Request-Id"), code, message, null, retryable));
    }
}
