import type { Motive } from "../contracts";

export const MOTIVE_OPTIONS: ReadonlyArray<{
  id: Motive;
  label: string;
  detail: string;
}> = [
  { id: "GPA", label: "提高绩点", detail: "优先考虑成绩目标" },
  { id: "LOW_WORKLOAD", label: "减轻课业压力", detail: "关注作业和学习投入" },
  { id: "LOW_ATTENDANCE", label: "减少考勤压力", detail: "关注课程考勤要求" },
  { id: "GOOD_REVIEWS", label: "参考课程评价", detail: "关注有来源的往年反馈" },
  {
    id: "SPECIFIC_TEACHER",
    label: "关注指定教师",
    detail: "教师选项会在后续课程步骤确认",
  },
  { id: "INTEREST", label: "学习感兴趣的内容", detail: "按你填写的主题整理" },
  {
    id: "CAREER",
    label: "了解职业方向",
    detail: "了解可能的方向，之后可留空跳过",
  },
  { id: "POSTGRAD", label: "为继续深造做准备", detail: "作为规划目标一并交接" },
  {
    id: "CREDIT_PROGRESS",
    label: "推进学分进度",
    detail: "毕业要求由后续学业核对提供",
  },
  {
    id: "SCHEDULE",
    label: "安排合适的上课时间",
    detail: "可填写必须避开的时段或偏好",
  },
];

export const MOTIVE_LABELS = Object.fromEntries(
  MOTIVE_OPTIONS.map(({ id, label }) => [id, label]),
) as Record<Motive, string>;
