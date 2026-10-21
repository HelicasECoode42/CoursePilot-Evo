package com.coursepilot.verifier.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MissingRequestHeaderException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

@RestControllerAdvice
public class ApiExceptionHandler {

    /** 缺少必填查询参数，例如没传 studentId */
    @ExceptionHandler(MissingServletRequestParameterException.class)
    public ResponseEntity<Envelope<Void>> missingParam(MissingServletRequestParameterException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
            .body(Envelope.error(null, "MISSING_PARAMETER",
                "缺少必填参数：" + ex.getParameterName(),
                ex.getParameterName(), false));
    }

    /** 参数类型不对，例如 studentId 传了数组 */
    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<Envelope<Void>> typeMismatch(MethodArgumentTypeMismatchException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
            .body(Envelope.error(null, "TYPE_MISMATCH",
                "参数类型错误：" + ex.getName(),
                ex.getName(), false));
    }

    /** 请求体不是合法 JSON，或字段类型对不上 */
    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Envelope<Void>> unreadable(HttpMessageNotReadableException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
            .body(Envelope.error(null, "MALFORMED_JSON",
                "请求体不是合法 JSON 或字段类型不匹配",
                null, false));
    }

    /** 路径不存在 */
    @ExceptionHandler(NoResourceFoundException.class)
    public ResponseEntity<Envelope<Void>> notFound(NoResourceFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(Envelope.error(null, "NOT_FOUND",
                "接口不存在：" + ex.getResourcePath(),
                null, false));
    }

    /**
     * 对象级授权失败。契约把 404 定义为「对象不可见或不存在」，403 为
     * 「权限不足」；别人的记录属于不可见，回 403 会暴露该 ID 存在。
     */
    @ExceptionHandler(AccessDenied.class)
    public ResponseEntity<Envelope<Void>> notVisible(AccessDenied ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(Envelope.error(null, "NOT_VISIBLE", ex.getMessage(), null, false));
    }

    /** 身份头缺失或格式不合法，例如没有 X-Subject-Id */
    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Envelope<Void>> badSubject(IllegalArgumentException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
            .body(Envelope.error(null, "INVALID_SUBJECT", ex.getMessage(), "X-Subject-Id", false));
    }

    /** 缺少必填请求头 */
    @ExceptionHandler(MissingRequestHeaderException.class)
    public ResponseEntity<Envelope<Void>> missingHeader(MissingRequestHeaderException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
            .body(Envelope.error(null, "MISSING_HEADER",
                "缺少必填请求头：" + ex.getHeaderName(), ex.getHeaderName(), false));
    }

    /** 兜底：任何未预期的异常 */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<Envelope<Void>> fallback(Exception ex) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(Envelope.error(null, "INTERNAL_ERROR",
                ex.getClass().getSimpleName() + ": " + ex.getMessage(),
                null, true));
    }
}
