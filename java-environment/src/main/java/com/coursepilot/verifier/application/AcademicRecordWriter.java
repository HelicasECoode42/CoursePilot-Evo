package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.entity.IdempotencyEntry;
import com.coursepilot.verifier.persistence.entity.Transcript;
import com.coursepilot.verifier.persistence.repo.IdempotencyEntryRepository;
import com.coursepilot.verifier.persistence.repo.TranscriptRepository;
import com.coursepilot.verifier.web.RecordConflict;
import com.coursepilot.verifier.web.dto.RecordDtos;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Optional;

/**
 * 学业记录写入的事务边界。子表、幂等记录、revision 要么一起落，要么一起不落，
 * 否则会留下子表写一半的坏数据。
 *
 * 和 AcademicRecordService 分开：@Transactional 只在代理调用时生效，同类内部调用不走代理。
 */
@Component
public class AcademicRecordWriter {

    private final TranscriptRepository transcripts;
    private final IdempotencyEntryRepository idempotency;
    private final ObjectMapper mapper;

    public AcademicRecordWriter(TranscriptRepository transcripts,
                                IdempotencyEntryRepository idempotency,
                                ObjectMapper mapper) {
        this.transcripts = transcripts;
        this.idempotency = idempotency;
        this.mapper = mapper;
    }

    /**
     * 写入。同 (主体, 键) 且摘要相同：原样回放上次答复，不写库。
     * 同键不同摘要：409。createdAt 用服务端时间。
     */
    @Transactional
    public RecordDtos.AcademicRecord submit(String subjectId, String key, String digest,
                                            RecordDtos.AcademicRecordInput input) {
        Optional<RecordDtos.AcademicRecord> prior = key == null ? Optional.empty() : replayFrom(subjectId, key, digest);
        if (prior.isPresent()) {
            return prior.get();
        }

        Transcript t = transcripts.findByStudentId(subjectId).orElseGet(() -> new Transcript(subjectId));
        t.revise(input.curriculumSnapshotId(), input.transcriptComplete(),
            Transcript.SourceKind.valueOf(input.sourceKind()),
            Instant.now().truncatedTo(ChronoUnit.SECONDS),
            AcademicRecordMapper.toCourses(input.completedCourses()));
        transcripts.save(t);

        RecordDtos.AcademicRecord response = AcademicRecordMapper.toDto(t);
        if (key != null) {
            idempotency.save(new IdempotencyEntry(subjectId, key, digest, writeJson(response), Instant.now()));
        }
        return response;
    }

    /** 并发竞争失败后的回放查找，在新的只读事务里执行。 */
    @Transactional(readOnly = true)
    public Optional<RecordDtos.AcademicRecord> replay(String subjectId, String key, String digest) {
        return replayFrom(subjectId, key, digest);
    }

    private Optional<RecordDtos.AcademicRecord> replayFrom(String subjectId, String key, String digest) {
        return idempotency.findByStudentIdAndIdemKey(subjectId, key).map(prior -> {
            if (!prior.getRequestDigest().equals(digest)) {
                throw new RecordConflict("同一幂等键已用于不同内容，请换一个新的 Idempotency-Key");
            }
            return readJson(prior.getResponseJson());
        });
    }

    private String writeJson(RecordDtos.AcademicRecord dto) {
        try {
            return mapper.writeValueAsString(dto);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("学业记录序列化失败", e);
        }
    }

    private RecordDtos.AcademicRecord readJson(String json) {
        try {
            return mapper.readValue(json, RecordDtos.AcademicRecord.class);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("幂等回放记录损坏", e);
        }
    }
}
