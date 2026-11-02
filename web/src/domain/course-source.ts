/** Display curriculum references without interpreting them as review citations. */
export function courseSourceLabel(ref: string): string {
  if (ref.startsWith("synthetic:")) return "合成培养方案资料";
  if (ref.startsWith("curriculum:") || ref.startsWith("src:"))
    return "培养方案资料";
  return "课程来源资料";
}
