package com.coursepilot.verifier.web;

/**
 * 对象级授权失败（b-verifier.md B-F6：只允许访问所属记录）。
 *
 * 契约 java.openapi.json 把 404 定义为「对象不可见或不存在」，403 定义为
 * 「权限不足」。别人的记录属于「不可见」，所以一律按 404 回，不回 403——
 * 403 会告诉调用方「这个 ID 存在但不是你的」，本身就是一次信息泄露。
 */
public class AccessDenied extends RuntimeException {
    public AccessDenied(String message) {
        super(message);
    }
}
