package com.coursepilot.verifier.web;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import java.io.PrintWriter;

@Component
public class ApiSecurityInterceptor implements HandlerInterceptor {

    // 读取环境变量，如果没有配置，默认空字符串
    @Value("${COURSEPILOT_SERVICE_KEY:}")
    private String expectedKey;

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
        // 1. 检查服务端是否配置了环境变量，没配置直接 503
        if (expectedKey == null || expectedKey.isBlank()) {
            writeError(response, 503, "Service Unavailable: 缺少 COURSEPILOT_SERVICE_KEY 环境变量");
            return false;
        }

        // 2. 检查请求头里的 X-Service-Key，不匹配直接 401
        String clientKey = request.getHeader("X-Service-Key");
        if (!expectedKey.equals(clientKey)) {
            writeError(response, 401, "Unauthorized: X-Service-Key 错误或缺失");
            return false;
        }

        // 3. 检查请求头里的 X-Subject-Id，缺失直接 400
        String subjectId = request.getHeader("X-Subject-Id");
        if (subjectId == null || subjectId.isBlank()) {
            writeError(response, 400, "Bad Request: 缺少 X-Subject-Id");
            return false;
        }

        return true; // 校验通过，放行
    }

    private void writeError(HttpServletResponse response, int status, String message) throws Exception {
        response.setStatus(status);
        response.setContentType("application/json;charset=UTF-8");
        try (PrintWriter writer = response.getWriter()) {
            // 简单返回一个符合 Envelope 格式的 JSON
            writer.write("{\"schemaVersion\":\"1.0\",\"status\":\"ERROR\",\"issues\":[{\"code\":\"AUTH_ERROR\",\"message\":\"" + message + "\"}]}");
        }
    }
}
