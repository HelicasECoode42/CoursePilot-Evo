package com.coursepilot.verifier.web;

import com.coursepilot.verifier.application.SyntheticCurriculumPublishPort;
import com.coursepilot.verifier.persistence.repo.CurriculumCourseRepository;
import com.coursepilot.verifier.web.dto.ImportDtos;
import edu.coursepilot.importer.A1WorkbookImporter;
import edu.coursepilot.importer.ImportModels.CurriculumDraft;
import edu.coursepilot.importer.ImportModels.ImportIssue;
import edu.coursepilot.importer.ImportModels.IssueCode;
import edu.coursepilot.importer.XlsxInputGuard;
import java.io.IOException;
import java.net.InetAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** Local-only curriculum import; CURRICULUM_FILE is published as UNVERIFIED. */
@RestController
@RequestMapping("/api/v1/curriculum-snapshots")
public class CurriculumImportController {
    private static final Pattern ID = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$");

    private final A1WorkbookImporter importer;
    private final SyntheticCurriculumPublishPort publisher;
    private final CurriculumCourseRepository curriculumCourses;
    private final SubjectGuard subjects;
    private final String adminKey;
    private final boolean localImportEnabled;

    public CurriculumImportController(
        A1WorkbookImporter importer,
        SyntheticCurriculumPublishPort publisher,
        CurriculumCourseRepository curriculumCourses,
        SubjectGuard subjects,
        @Value("${coursepilot.admin-key:}") String adminKey,
        @Value("${coursepilot.import.synthetic.enabled:false}") boolean localImportEnabled) {
        this.importer = importer;
        this.publisher = publisher;
        this.curriculumCourses = curriculumCourses;
        this.subjects = subjects;
        this.adminKey = adminKey == null ? "" : adminKey;
        this.localImportEnabled = localImportEnabled;
    }

    @PostMapping(value = "/import", consumes = "multipart/form-data")
    public ResponseEntity<Envelope<ImportDtos.ImportResult>> importCurriculum(
        @RequestHeader("X-Request-Id") String requestId,
        @RequestHeader("X-Subject-Id") String subjectId,
        @RequestHeader(value = "X-Admin-Key", required = false) String presentedAdminKey,
        @RequestParam("schemaVersion") String schemaVersion,
        @RequestParam("trackId") String trackId,
        @RequestParam(value = "sourceKind", defaultValue = "SYNTHETIC") String sourceKind,
        @RequestParam("file") MultipartFile file,
        jakarta.servlet.http.HttpServletRequest request) {
        subjects.require(subjectId);
        if (!ID.matcher(requestId).matches()) {
            return error(HttpStatus.BAD_REQUEST, requestId, "INVALID_REQUEST_ID", "X-Request-Id 格式不合法", "X-Request-Id");
        }
        if (!localImportEnabled) {
            return error(HttpStatus.FORBIDDEN, requestId, "SYNTHETIC_IMPORT_DISABLED", "本地培养方案导入未启用", null);
        }
        if (!isLoopback(request.getRemoteAddr())) {
            return error(HttpStatus.FORBIDDEN, requestId, "LOCAL_IMPORT_ONLY", "培养方案导入仅允许本机调用", null);
        }
        if (adminKey.isBlank()) {
            return error(HttpStatus.SERVICE_UNAVAILABLE, requestId, "ADMIN_KEY_NOT_CONFIGURED", "服务端未配置管理员密钥", null);
        }
        if (presentedAdminKey == null || !constantTimeEquals(adminKey, presentedAdminKey)) {
            return error(HttpStatus.UNAUTHORIZED, requestId, "ADMIN_KEY_INVALID", "缺少或错误的 X-Admin-Key", null);
        }
        if (!"1.0".equals(schemaVersion)) {
            return error(HttpStatus.BAD_REQUEST, requestId, "SCHEMA_VERSION_UNSUPPORTED", "schemaVersion 必须为 1.0", "schemaVersion");
        }
        if (request.getParameterMap().keySet().stream()
            .anyMatch(name -> !Set.of("schemaVersion", "trackId", "sourceKind").contains(name))) {
            return error(HttpStatus.BAD_REQUEST, requestId, "UNSUPPORTED_IMPORT_FIELD", "导入请求包含契约未声明的字段", null);
        }
        if (!Set.of("SYNTHETIC", "CURRICULUM_FILE").contains(sourceKind)) {
            return error(HttpStatus.BAD_REQUEST, requestId, "INVALID_SOURCE_KIND", "不支持的培养资料来源", "sourceKind");
        }
        if (file == null || file.isEmpty()) {
            return error(HttpStatus.BAD_REQUEST, requestId, "IMPORT_FILE_REQUIRED", "必须提供非空 xlsx 文件", "file");
        }
        String filename = file.getOriginalFilename();
        if (filename == null || !filename.toLowerCase(java.util.Locale.ROOT).endsWith(".xlsx")) {
            return error(HttpStatus.UNPROCESSABLE_ENTITY, requestId, "WRONG_EXTENSION", "仅支持 .xlsx 工作簿", "file");
        }
        if (file.getSize() > XlsxInputGuard.MAX_BYTES) {
            return error(HttpStatus.PAYLOAD_TOO_LARGE, requestId, "FILE_TOO_LARGE", "工作簿超过 10 MiB", "file");
        }

        Path temporaryFile = null;
        try {
            temporaryFile = Files.createTempFile("coursepilot-curriculum-", ".xlsx");
            file.transferTo(temporaryFile);
            CurriculumDraft draft = importer.prepare(temporaryFile, trackId);
            if (!draft.publishable()) {
                ImportIssue issue = draft.blockingIssues().getFirst();
                return error(HttpStatus.UNPROCESSABLE_ENTITY, requestId, issue.code().name(),
                    message(issue.code()), "file");
            }
            var published = "CURRICULUM_FILE".equals(sourceKind)
                ? publisher.publishUnverifiedCurriculum(draft) : importer.publish(draft, publisher);
            var membership = curriculumCourses.findBySnapshot_SnapshotIdAndCourse_CourseCodeAndName(
                published.snapshotId(), draft.entries().getFirst().courseCode(),
                draft.entries().getFirst().name()).orElseThrow();
            var source = membership.getSourceReference();
            var responseSource = new Envelope.SourceRef(
                source.getKind(), source.getRefId(), source.getSnapshotId(),
                source.getLocator(), source.getCapturedAt());
            // 可记录问题（如待确认的占位课程号）随成功结果返回，让人看见哪些行待确认。
            var recorded = draft.recordedIssues().stream()
                .map(i -> new Envelope.Issue(i.code().name(),
                    message(i.code()) + "（" + i.sheet() + " 第" + i.row() + "行）",
                    "file", false))
                .toList();
            var result = new ImportDtos.ImportResult(published.snapshotId(), "PUBLISHED", published.reused(), recorded);
            return ResponseEntity.ok(Envelope.ok(requestId, result).withProvenance(List.of(responseSource)));
        } catch (XlsxInputGuard.ImportRejectedException ex) {
            HttpStatus status = ex.code() == IssueCode.FILE_TOO_LARGE
                ? HttpStatus.PAYLOAD_TOO_LARGE : HttpStatus.UNPROCESSABLE_ENTITY;
            return error(status, requestId, ex.code().name(), message(ex.code()), "file");
        } catch (IOException ex) {
            return error(HttpStatus.BAD_REQUEST, requestId, "IMPORT_FILE_UNREADABLE", "无法读取上传的工作簿", "file");
        } finally {
            if (temporaryFile != null) {
                try {
                    Files.deleteIfExists(temporaryFile);
                } catch (IOException ignored) {
                    // The temporary path contains no client-controlled filename or data in logs.
                }
            }
        }
    }

    private static String message(IssueCode code) {
        return switch (code) {
            case FILE_TOO_LARGE -> "工作簿超过允许大小";
            case WRONG_EXTENSION -> "仅支持 .xlsx 工作簿";
            case TRACK_NOT_ALLOWED -> "不支持所选培养路径";
            case TEMPLATE_MISMATCH -> "工作簿格式与所选培养路径不匹配";
            case INVALID_COURSE_CODE -> "课程编号必须符合接口格式：以字母或数字开头，且只包含字母、数字、点、下划线、冒号或连字符";
            case COURSE_CODE_TOO_LONG -> "课程编号超过当前数据库支持的 32 个字符";
            case UNKNOWN_RULE -> "工作簿包含尚未解释的培养规则";
            case UNSUPPORTED_ENTRY -> "工作簿包含当前系统无法表示的课程组或规则行";
            case COURSE_CODE_PENDING -> "课程编号为占位值，真实编号待确认";
            case COURSE_CODE_RANGE_EXPANDED -> "连号课程编号已按工作簿展开为多门课";
            case CREDITS_UNSPLIT -> "连号课程组只有整组学分，成员学分未拆分，记为未知";
            case GROUP_REQUIREMENT_ROW -> "课程组要求行不是单门课程，未作为课程入库，其学分要求见类别表";
            default -> "工作簿内容不符合导入要求";
        };
    }

    private static boolean constantTimeEquals(String expected, String presented) {
        return MessageDigest.isEqual(
            expected.getBytes(StandardCharsets.UTF_8), presented.getBytes(StandardCharsets.UTF_8));
    }

    private static boolean isLoopback(String remoteAddress) {
        try {
            return InetAddress.getByName(remoteAddress).isLoopbackAddress();
        } catch (Exception ex) {
            return false;
        }
    }

    private static <T> ResponseEntity<Envelope<T>> error(
        HttpStatus status, String requestId, String code, String message, String field) {
        return ResponseEntity.status(status).body(Envelope.error(requestId, code, message, field, false));
    }
}
