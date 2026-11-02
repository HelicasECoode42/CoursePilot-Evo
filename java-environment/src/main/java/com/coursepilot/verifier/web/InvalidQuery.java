package com.coursepilot.verifier.web;

/**
 * 查询参数格式或范围不合法（契约 400）。与 MISSING_PARAMETER 区分：这里是参数存在但值不合法。
 */
public class InvalidQuery extends RuntimeException {

    private final String field;

    public InvalidQuery(String field, String message) {
        super(message);
        this.field = field;
    }

    public String getField() {
        return field;
    }
}
