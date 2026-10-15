import type { PlanningRequest } from "../contracts";

export const CLASS_PREFERENCE_OPTIONS = [
  {
    id: "GRADING_FEEDBACK",
    label: "给分反馈更友好",
    detail: "参考评分说明和往年反馈，不代表保证成绩",
    softPreference: {
      dimension: "assessment.grading_feedback",
      value: "prefer_friendly",
      sourceText: "希望参考给分反馈较友好的课程，不代表保证高分",
    },
  },
  {
    id: "LOWER_ATTENDANCE",
    label: "尽量少签到",
    detail: "具体要求仍以本学期课程安排为准",
    softPreference: {
      dimension: "workload.attendance",
      value: "lower_attendance",
      sourceText: "希望参考签到要求较少的课程",
    },
  },
  {
    id: "LOWER_HOMEWORK",
    label: "作业量少一些",
    detail: "作业频率和投入会因课程与学期变化",
    softPreference: {
      dimension: "workload.homework",
      value: "lower_homework",
      sourceText: "希望参考作业投入较少的课程",
    },
  },
  {
    id: "FEWER_GROUP_TASKS",
    label: "少一些小组任务",
    detail: "不想把小组作业作为主要考核方式",
    softPreference: {
      dimension: "assessment.group_tasks",
      value: "fewer_group_tasks",
      sourceText: "希望参考小组任务较少的课程",
    },
  },
  {
    id: "FEWER_PRESENTATIONS",
    label: "少一些汇报和展示",
    detail: "减少频繁的课堂汇报或展示",
    softPreference: {
      dimension: "assessment.presentations",
      value: "fewer_presentations",
      sourceText: "希望参考汇报和展示较少的课程",
    },
  },
  {
    id: "AVOID_CLOSED_BOOK_EXAMS",
    label: "尽量避开闭卷考试",
    detail: "更愿意考虑其他考核方式",
    softPreference: {
      dimension: "assessment.closed_book_exam",
      value: "avoid_closed_book",
      sourceText: "希望尽量避开闭卷考试",
    },
  },
] as const satisfies ReadonlyArray<{
  id: string;
  label: string;
  detail: string;
  softPreference: PlanningRequest["intent"]["softPreferences"][number];
}>;

export type ClassPreferenceId = (typeof CLASS_PREFERENCE_OPTIONS)[number]["id"];

export function collectClassSoftPreferences(
  selected: readonly ClassPreferenceId[],
): PlanningRequest["intent"]["softPreferences"] {
  return selected.flatMap((id) => {
    const option = CLASS_PREFERENCE_OPTIONS.find((item) => item.id === id);
    return option ? [option.softPreference] : [];
  });
}
