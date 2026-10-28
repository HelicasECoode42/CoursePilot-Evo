package com.coursepilot.verifier.config;

import com.coursepilot.verifier.persistence.entity.*;
import com.coursepilot.verifier.persistence.repo.*;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

@Configuration
public class SeedData {

    @Bean
    CommandLineRunner init(CourseRepository courseRepo,
                           RequirementRepository reqRepo,
                           CourseOfferingRepository offeringRepo,
                           CurriculumSnapshotRepository snapshotRepo,
                           TranscriptRepository transcriptRepo,
                           TeacherCourseRepository teacherCourseRepo,
                           ReviewNoteRepository reviewNoteRepo) {
        return args -> {
            // 快照种子用自己的「表为空才写」判断，不能放在课程种子的早退之后：
            // 文件库（ddl-auto=update）里课程表已非空时，快照表若仍为空，
            // listCurricula 会永远返回空数组。
            if (snapshotRepo.count() == 0) {
                // 演示种子一律 SYNTHETIC/SYNTHETIC：这些不是真实教学计划，
                // 不能标成 CURRICULUM_FILE 或 VERIFIED（AGENTS.md：REAL 不能用 synthetic）。
                snapshotRepo.save(new CurriculumSnapshot("PLAN_CS_2025",
                    CurriculumSnapshot.Kind.CURRICULUM, CurriculumSnapshot.State.PUBLISHED,
                    CurriculumSnapshot.SourceKind.SYNTHETIC,
                    CurriculumSnapshot.SourceValidation.SYNTHETIC, null,
                    Instant.parse("2025-09-01T00:00:00Z")));
                // 自称来自浏览器快照但尚未核验，用来说明 sourceKind 不决定
                // sourceValidation：上传者给的标签不能让它自动变 VERIFIED。
                snapshotRepo.save(new CurriculumSnapshot("PLAN_CS_2024",
                    CurriculumSnapshot.Kind.CURRICULUM, CurriculumSnapshot.State.PUBLISHED,
                    CurriculumSnapshot.SourceKind.BROWSER_SNAPSHOT,
                    CurriculumSnapshot.SourceValidation.UNVERIFIED, null,
                    Instant.parse("2024-09-01T00:00:00Z")));
                // 已被拒绝的培养方案，listCurricula 不应列出来。创建时间取最早，
                // 即便误列出也只会排在已发布快照之后。
                snapshotRepo.save(new CurriculumSnapshot("PLAN_CS_2023_REJECTED",
                    CurriculumSnapshot.Kind.CURRICULUM, CurriculumSnapshot.State.REJECTED,
                    CurriculumSnapshot.SourceKind.SYNTHETIC,
                    CurriculumSnapshot.SourceValidation.SYNTHETIC, null,
                    Instant.parse("2023-09-01T00:00:00Z")));
                // 开课快照同表不同 kind，listCurricula 不应把它列出来。
                snapshotRepo.save(new CurriculumSnapshot("OFFER_2025_FALL",
                    CurriculumSnapshot.Kind.OFFERING, CurriculumSnapshot.State.PUBLISHED,
                    CurriculumSnapshot.SourceKind.SYNTHETIC,
                    CurriculumSnapshot.SourceValidation.SYNTHETIC, "2025-FALL",
                    Instant.parse("2025-08-15T00:00:00Z")));
            }

            // 学业记录聚合的演示种子：主体 S001，合成数据，记录未声明完整。
            // 只在该主体没有记录时写入，文件库重启时不会重复。
            if (transcriptRepo.findByStudentId("S001").isEmpty()) {
                Transcript t = new Transcript("S001");
                t.revise("PLAN_CS_2025", false, Transcript.SourceKind.SYNTHETIC,
                    Instant.parse("2025-09-01T00:00:00Z"), List.of(
                        new TranscriptCourse("CS101", 1, new BigDecimal("3.00"),
                            TranscriptCourse.Outcome.PASSED, "2024-2025-1"),
                        new TranscriptCourse("CS101", 2, new BigDecimal("3.00"),
                            TranscriptCourse.Outcome.PASSED, "2024-2025-2"), // 重修
                        new TranscriptCourse("CS102", 1, new BigDecimal("4.00"),
                            TranscriptCourse.Outcome.PASSED, "2024-2025-1"),
                        new TranscriptCourse("GE101", 1, new BigDecimal("2.00"),
                            TranscriptCourse.Outcome.PASSED, "2024-2025-2")));
                transcriptRepo.save(t);
            }

            // 教师与评价的演示种子。全部是 SYNTHETIC 的虚构内容，sourceUrl 一律为空，
            // 不编造指向真实教务或网站的来源。放在课程早退之前，独立判断自己的表是否为空。
            //
            // 覆盖：matchStatus 的 COURSE_TEACHER_MATCHED / COURSE_ONLY / UNVERIFIED；
            // availability 的 HISTORICAL_ONLY / UNKNOWN。CURRENT_VERIFIED 故意不种：
            // 没有任何已核验来源说明当期开课，见 TeacherReviewAssembler.availability。
            if (teacherCourseRepo.count() == 0) {
                // CS102 声明了一个当期学期，但来源是 SYNTHETIC，所以仍不能是 CURRENT_VERIFIED。
                teacherCourseRepo.save(new TeacherCourse("PLAN_CS_2025", "CS101", "T_ZHANG", "张老师",
                    null, TeacherCourse.SourceValidation.SYNTHETIC));
                teacherCourseRepo.save(new TeacherCourse("PLAN_CS_2025", "CS102", "T_LI", "李老师",
                    "2025-FALL", TeacherCourse.SourceValidation.SYNTHETIC));
                // 王老师只有绑定，没有任何历史评价，应判为 UNKNOWN。
                teacherCourseRepo.save(new TeacherCourse("PLAN_CS_2025", "CS103", "T_WANG", "王老师",
                    null, TeacherCourse.SourceValidation.SYNTHETIC));
            }
            if (reviewNoteRepo.count() == 0) {
                reviewNoteRepo.save(new ReviewNote("R_CS101_T_ZHANG_01", "CS101", "T_ZHANG", "2024-2025-1",
                    ReviewNote.SourceKind.SYNTHETIC, Instant.parse("2025-01-10T00:00:00Z"), null,
                    "【演示数据】平时作业较多，期末以上机为主。",
                    List.of(ReviewNote.Dimension.GRADING, ReviewNote.Dimension.WORKLOAD)));
                // 课程级评价：没有教师信息，teacherKey 为空，只能说明课程，不能说明某位教师。
                reviewNoteRepo.save(new ReviewNote("R_CS101_COURSE_01", "CS101", null, "2023-2024-2",
                    ReviewNote.SourceKind.SYNTHETIC, null, null,
                    "【演示数据】课程内容稳定，无法确定授课教师。",
                    List.of(ReviewNote.Dimension.OVERALL)));
                reviewNoteRepo.save(new ReviewNote("R_CS102_T_LI_01", "CS102", "T_LI", "2024-2025-2",
                    ReviewNote.SourceKind.SYNTHETIC, Instant.parse("2025-06-20T00:00:00Z"), null,
                    "【演示数据】点名比较频繁，授课节奏偏快。",
                    List.of(ReviewNote.Dimension.ATTENDANCE, ReviewNote.Dimension.TEACHING)));
                // 这条评价提到的教师 T_ZHANG 没有绑定到 CS102，所以是 UNVERIFIED，不能挂到张老师名下。
                reviewNoteRepo.save(new ReviewNote("R_CS102_UNBOUND_01", "CS102", "T_ZHANG", "2024-2025-1",
                    ReviewNote.SourceKind.SYNTHETIC, null, null,
                    "【演示数据】实验较多，教师身份未在本课程绑定中确认。",
                    List.of(ReviewNote.Dimension.WORKLOAD)));
                // CS103 的评价无法匹配到教师：teacherKey 为空，matchStatus 为 COURSE_ONLY。
                reviewNoteRepo.save(new ReviewNote("R_CS103_COURSE_01", "CS103", null, "2023-2024-1",
                    ReviewNote.SourceKind.SYNTHETIC, null, null,
                    "【演示数据】期末展示占比较高，具体授课教师无法从本条评价确认。",
                    List.of(ReviewNote.Dimension.PRESENTATION, ReviewNote.Dimension.EXAM)));
            }

            if (courseRepo.count() > 0) return;

            courseRepo.save(new Course("CS101", "Java 程序设计", 3.0, "必修"));
            courseRepo.save(new Course("CS102", "数据结构", 4.0, "必修"));
            courseRepo.save(new Course("GE101", "通识写作", 2.0, "通识"));
            courseRepo.save(new Course("CS103", "操作系统", null, "必修")); // 学分未知

            reqRepo.save(new Requirement("PLAN_CS_2025", "必修", 10.0));
            reqRepo.save(new Requirement("PLAN_CS_2025", "通识", 4.0));

            offeringRepo.save(new CourseOffering("O_CS101_01", "CS101", "张老师",
                "周一第1-2节{第1-16周}", "SYNTHETIC"));
            offeringRepo.save(new CourseOffering("O_CS102_01", "CS102", "李老师",
                "周一第2-3节{第1-16周}", "SYNTHETIC"));
            offeringRepo.save(new CourseOffering("O_CS103_01", "CS103", "王老师",
                "时间待定", "SYNTHETIC")); // 时间未知
        };
    }
}
