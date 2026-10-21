package com.coursepilot.verifier.web;

import org.springframework.stereotype.Component;

import java.util.regex.Pattern;

/**
 * 主体身份与归属校验。
 *
 * docs/16：Java 信任的是已认证的 Python 服务，不能透传浏览器自报的身份头。
 * 所以 X-Subject-Id 只有在 ServiceKeyFilter 验过 X-Service-Key 之后才可信——
 * 服务密钥证明「调用方是 C」，X-Subject-Id 是 C 代为断言的主体。
 *
 * 当前数据模型里一个主体只有一份学业记录，academicRecordId 就等于主体标识
 * （见 AuditResultAssembler 的说明）。等聚合实体落地后，这里换成查记录表的
 * owner 字段，调用方不用改。
 */
@Component
public class SubjectGuard {

    /** 契约 java.openapi.json 对 X-Subject-Id 的约束。 */
    private static final Pattern SUBJECT_ID = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$");

    /** 取出并校验主体标识；缺失或格式不合法都是 400，不往下走。 */
    public String require(String subjectId) {
        if (subjectId == null || !SUBJECT_ID.matcher(subjectId).matches()) {
            throw new IllegalArgumentException("X-Subject-Id 缺失或格式不合法");
        }
        return subjectId;
    }

    /**
     * 校验这份学业记录属于该主体。不属于就当作不存在。
     *
     * 注意这里不是先查到数据再判断能不能看，而是先定归属——查询本身就带上
     * 主体条件，避免「越权读」退化成「查出来再过滤」时漏掉一条分支。
     */
    public void requireOwnRecord(String subjectId, String academicRecordId) {
        if (!require(subjectId).equals(academicRecordId)) {
            throw new AccessDenied("学业记录 " + academicRecordId + " 对当前主体不可见");
        }
    }
}
