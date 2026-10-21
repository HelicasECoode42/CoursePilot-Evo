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
 * 没配 COURSEPILOT_SERVICE_KEY 时一律以 503 拒服务，而不是放行。
 * 失败路径只记录阶段和状态，不记录密钥本身，也不记录比对到的值。
 *
 * 这道过滤器**不按路径开豁免口**，对所有请求生效。早先的版本用
 * request.getRequestURI().startsWith("/api/v1/") 判断「是不是 API 请求」，
 * 结果可以被 /api/v1;x=1/courses 绕过：getRequestURI() 返回的原始路径带着
 * 分号后的矩阵变量，不匹配前缀于是跳过校验，而 Spring 的路径匹配会把
 * 这段剥掉照样路由到控制器。于是不带密钥、只自报 X-Subject-Id 就能读到
 * 任意主体的学业数据。编码、点段、双斜杠同理都是这一类写法差异。
 *
 * 所以这里不再做任何路径判断：凡是进到 Servlet 的请求都要有正确的密钥。
 * 代价是未知路径现在回 401 而不是 404——这反而更好，不暴露有哪些路径。
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
