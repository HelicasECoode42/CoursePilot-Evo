package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.repo.CurriculumSnapshotRepository;
import com.coursepilot.verifier.persistence.repo.TranscriptRepository;
import com.coursepilot.verifier.web.InvalidRecordInput;
import com.coursepilot.verifier.web.RecordConflict;
import com.coursepilot.verifier.web.UnknownSnapshot;
import com.coursepilot.verifier.web.dto.RecordDtos;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.TransactionException;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import java.util.regex.Pattern;

/**
 * 学业记录的读取与写入入口。读取只带主体条件查询；写入做输入校验后交给
 * AcademicRecordWriter 在事务里完成。
 */
@Service
public class AcademicRecordService {

    /** 契约 ^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$，最长 120。 */
    private static final Pattern ID = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$");
    private static final int MAX_COURSES = 500;

    private final TranscriptRepository transcripts;
    private final CurriculumSnapshotRepository snapshots;
    private final AcademicRecordWriter writer;

    public AcademicRecordService(TranscriptRepository transcripts,
                                 CurriculumSnapshotRepository snapshots,
                                 AcademicRecordWriter writer) {
        this.transcripts = transcripts;
        this.snapshots = snapshots;
        this.writer = writer;
    }

    @Transactional(readOnly = true)
    public List<RecordDtos.AcademicRecord> listFor(String subjectId) {
        return transcripts.findByStudentId(subjectId).map(AcademicRecordMapper::toDto).stream().toList();
    }

    @Transactional(readOnly = true)
    public Optional<RecordDtos.AcademicRecord> findFor(String subjectId) {
        return transcripts.findByStudentId(subjectId).map(AcademicRecordMapper::toDto);
    }

    public RecordDtos.AcademicRecord submit(String subjectId, String idempotencyKey,
                                            RecordDtos.AcademicRecordInput input) {
        if (idempotencyKey != null) {
            checkId("Idempotency-Key", idempotencyKey);
        }
        validate(input);
        String digest = AcademicRecordMapper.digest(input);
        try {
            return writer.submit(subjectId, idempotencyKey, digest, input);
        } catch (DataAccessException | TransactionException e) {
            // 并发竞争：另一请求同时写入了同键或同主体。若同键同内容已落下则回放它，否则 409。
            return (idempotencyKey == null ? Optional.<RecordDtos.AcademicRecord>empty()
                : writer.replay(subjectId, idempotencyKey, digest))
                .orElseThrow(() -> new RecordConflict("同一主体的学业记录正在被并发写入，请稍后重试"));
        }
    }

    private void validate(RecordDtos.AcademicRecordInput in) {
        if (in == null) {
            throw new InvalidRecordInput("body", "请求体缺失");
        }
        if (!"1.0".equals(in.schemaVersion())) {
            throw new InvalidRecordInput("schemaVersion", "schemaVersion 必须为 1.0");
        }
        checkId("curriculumSnapshotId", in.curriculumSnapshotId());
        if (in.transcriptComplete() == null) {
            throw new InvalidRecordInput("transcriptComplete", "transcriptComplete 必填");
        }
        if (!"USER_IMPORT".equals(in.sourceKind()) && !"SYNTHETIC".equals(in.sourceKind())) {
            throw new InvalidRecordInput("sourceKind", "sourceKind 只能是 USER_IMPORT 或 SYNTHETIC");
        }
        if (in.completedCourses() == null) {
            throw new InvalidRecordInput("completedCourses", "completedCourses 必填");
        }
        if (in.completedCourses().size() > MAX_COURSES) {
            throw new InvalidRecordInput("completedCourses", "completedCourses 最多 " + MAX_COURSES + " 条");
        }
        for (int i = 0; i < in.completedCourses().size(); i++) {
            RecordDtos.CompletedCourse c = in.completedCourses().get(i);
            String f = "completedCourses[" + i + "]";
            if (c == null) {
                throw new InvalidRecordInput(f, "不能为空");
            }
            checkId(f + ".courseCode", c.courseCode());
            if (c.outcome() == null) {
                throw new InvalidRecordInput(f + ".outcome", "outcome 必填");
            }
            if (c.earnedCredits() != null) {
                double v = c.earnedCredits();
                if (!(v >= 0 && v <= 1000)) {
                    throw new InvalidRecordInput(f + ".earnedCredits", "学分必须在 0 到 1000 之间");
                }
                if (BigDecimal.valueOf(v).stripTrailingZeros().scale() > 2) {
                    throw new InvalidRecordInput(f + ".earnedCredits", "学分最多两位小数");
                }
            }
            if (c.completedTerm() != null) {
                checkId(f + ".completedTerm", c.completedTerm());
            }
        }
        if (!snapshots.existsById(in.curriculumSnapshotId())) {
            throw new UnknownSnapshot(in.curriculumSnapshotId());
        }
    }

    private static void checkId(String field, String value) {
        if (value == null || !ID.matcher(value).matches()) {
            throw new InvalidRecordInput(field, field + " 缺失或格式不合法");
        }
    }
}
