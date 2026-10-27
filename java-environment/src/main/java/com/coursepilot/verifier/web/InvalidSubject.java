package com.coursepilot.verifier.web;

/**
 * 主体身份头缺失或格式不合法。
 *
 * 用专用异常而不是 IllegalArgumentException：后者在任何地方抛出都会被
 * 统一映射成 400「X-Subject-Id 不合法」，把本该是 500 的内部错误伪装成
 * 调用方的参数问题，排查时会被带偏。
 */
public class InvalidSubject extends RuntimeException {
    public InvalidSubject(String message) {
        super(message);
    }
}
