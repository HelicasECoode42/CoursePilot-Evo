import type { ReviewNote } from "../contracts";

/**
 * 评价原文的展示拆分。
 *
 * 库内数据已由 scripts/split_glued_review_notes.py 拆成一条一评；这里再做一次防御性拆分，
 * 防止旧数据（PDF 粘连的「Ⅱ」「丨」「』」等分隔符）整段显示。拆分只影响显示，不改库内数据。
 * 原文是用户/学生写的，只做去残留和去 PDF 换行空格，不改写措辞。
 */
const SEPARATOR_RE = /Ⅱ|‖|\|\||｜｜|丨|』/;
const EDGE_ARTIFACTS = "口丨｜|」「『』 \t\u3000";
const CJK_GAP_RE = /(?<=[\u3000-鿿＀-￯])\s+(?=[\u3000-鿿＀-￯])/g;
const MIN_SEGMENT_LENGTH = 2;
export const UNNAMED_TEACHER_LABEL = "未标明老师";

function trimArtifacts(text: string, splitPart: boolean): string {
  let s = text.trim();
  // 分隔符旁孤立的 OCR 字母，如 "ⅡI 老师…"
  if (splitPart) s = s.replace(/^[IⅠ]\s+/, "");
  while (s.length > 0 && EDGE_ARTIFACTS.includes(s[0]!)) s = s.slice(1);
  while (s.length > 0 && EDGE_ARTIFACTS.includes(s[s.length - 1]!))
    s = s.slice(0, -1);
  return s.replace(CJK_GAP_RE, "").trim();
}

/** 把一条评价原文拆成若干条独立评价文本；没有分隔符时返回仅含原文的一项。 */
export function splitReviewExcerpt(excerpt: string): string[] {
  const parts = excerpt.split(SEPARATOR_RE);
  const cleaned = parts
    .map((part, index) => trimArtifacts(part, index > 0))
    .filter((part) => part.length >= MIN_SEGMENT_LENGTH);
  if (cleaned.length > 0) return cleaned;
  const whole = trimArtifacts(excerpt, false);
  return whole.length > 0 ? [whole] : [];
}

/** 「22-秋」这类学期前缀；无学期或格式不认识时返回空串。 */
export function termPrefixLabel(termId: string | null): string {
  const match = /^(\d{4})-(\d{4})-([12])$/.exec(termId ?? "");
  if (!match) return "";
  // 秋季学期取学年起始年（22-秋 = 2022-2023-1）；春季学期取学年结束年（23-春 = 2022-2023-2），与导入脚本的映射一致。
  if (match[3] === "1") return `${match[1]!.slice(2)}-秋`;
  return `${match[2]!.slice(2)}-春`;
}

export interface ReviewItem {
  /** 稳定的展示键：评价编号 + 段序号。 */
  key: string;
  reviewNoteId: string;
  teacherLabel: string;
  termPrefix: string;
  text: string;
  note: ReviewNote;
}

/** 把若干评价展开为「一条一项」，每项带老师名（或「未标明老师」）与学期前缀。 */
export function expandReviewItems(notes: readonly ReviewNote[]): ReviewItem[] {
  return notes.flatMap((note) => {
    const name = note.teacherDisplayName?.trim();
    // 已绑定到具体教师：直接显示名字。未绑定：名字只是原文里的标注，必须注明未核实，不能说成这位老师教过。
    const teacherLabel = !name
      ? UNNAMED_TEACHER_LABEL
      : note.teacherKey
        ? name
        : `来源标注：${name}（未核实）`;
    const termPrefix = termPrefixLabel(note.termId);
    return splitReviewExcerpt(note.excerpt).map((text, index) => ({
      key: `${note.reviewNoteId}#${index}`,
      reviewNoteId: note.reviewNoteId,
      teacherLabel,
      termPrefix,
      text,
      note,
    }));
  });
}
