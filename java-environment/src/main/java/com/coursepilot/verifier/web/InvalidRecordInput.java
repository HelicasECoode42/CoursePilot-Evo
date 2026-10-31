package com.coursepilot.verifier.web;

/** 学业记录写入的输入不合法（契约 400）。field 指向出错的字段，便于上游定位。 */
public class InvalidRecordInput extends RuntimeException {
    private final String field;

    public InvalidRecordInput(String field, String message) {
        super(message);
        this.field = field;
    }

    public String getField() { return field; }
}
