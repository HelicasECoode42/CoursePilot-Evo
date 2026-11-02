/** 将评价来源定位转换为可读名称，同时保留原始标识供查证。 */
export function reviewSourceLabel(ref: string): string {
  const faculty = /^faculty-pdf:p(\d+):l(\d+)$/.exec(ref);
  if (faculty)
    return `计算机学院评价资料 · 第${Number(faculty[1])}页第${Number(faculty[2])}行`;
  const winter = /^winter-pdf:[^:]+:p(\d+)-p(\d+):l(\d+)-l(\d+)$/.exec(ref);
  if (winter) {
    const start = Number(winter[1]);
    const end = Number(winter[2]);
    return `冬季刊评价资料 · ${start === end ? `第${start}页` : `第${start}–${end}页`}`;
  }
  return "评价来源资料";
}
