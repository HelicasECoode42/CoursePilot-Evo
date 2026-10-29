import { describe, expect, it, vi } from "vitest";
import { createSchoolProgressBridge } from "./school-progress-bridge";

function bridge(save = vi.fn(async () => {})) {
  const posted: unknown[] = [];
  let counter = 0;
  const b = createSchoolProgressBridge({
    save,
    post: (m) => posted.push(m),
    newRequestId: () => `req-${++counter}`,
  });
  return { b, posted, save };
}

const deliver = (requestId: string, payload: unknown = { any: "thing" }) => ({
  type: "CP_DELIVER_PROGRESS",
  requestId,
  payload,
});

describe("学业进度接收", () => {
  it("登记时发出 CP_START_IMPORT 并返回 requestId", () => {
    const { b, posted } = bridge();
    const id = b.requestImport();
    expect(id).toBe("req-1");
    expect(posted).toEqual([{ type: "CP_START_IMPORT", requestId: "req-1" }]);
  });

  it("收到数据就存，并带着原 requestId 回执 ok:true", async () => {
    const save = vi.fn(async () => {});
    const { b, posted } = bridge(save);
    const id = b.requestImport();
    const outcome = await b.handle(deliver(id, { nodes: [] }));
    expect(outcome.kind).toBe("saved");
    expect(save).toHaveBeenCalledWith({ nodes: [] });
    expect(posted.at(-1)).toEqual({
      type: "CP_IMPORT_ACCEPTED",
      requestId: id,
      ok: true,
    });
  });

  it("保存失败时回执 ok:false，并把服务端的原因给学生看", async () => {
    const save = vi.fn(async () => {
      throw new Error("请先选择培养方案。");
    });
    const { b, posted } = bridge(save);
    const id = b.requestImport();
    const outcome = await b.handle(deliver(id));
    expect(outcome).toEqual({ kind: "failed", message: "请先选择培养方案。" });
    expect(posted.at(-1)).toEqual({
      type: "CP_IMPORT_ACCEPTED",
      requestId: id,
      ok: false,
    });
  });

  it("requestId 对不上不处理也不回执，免得抢别的标签页的回执", async () => {
    const save = vi.fn(async () => {});
    const { b, posted } = bridge(save);
    b.requestImport();
    const before = posted.length;
    const outcome = await b.handle(deliver("req-999"));
    expect(outcome).toEqual({ kind: "ignored" });
    expect(save).not.toHaveBeenCalled();
    expect(posted.length).toBe(before);
  });

  it("没登记过就收到数据，不处理", async () => {
    const save = vi.fn(async () => {});
    const { b } = bridge(save);
    expect(await b.handle(deliver("req-1"))).toEqual({ kind: "ignored" });
    expect(save).not.toHaveBeenCalled();
  });

  it("存成功后清掉 pending，重放同一条不会存第二次", async () => {
    const save = vi.fn(async () => {});
    const { b } = bridge(save);
    const id = b.requestImport();
    await b.handle(deliver(id));
    expect(await b.handle(deliver(id))).toEqual({ kind: "ignored" });
    expect(save).toHaveBeenCalledTimes(1);
  });

  it("CP_IMPORT_READY 的 ok 为假也算扩展在场", async () => {
    const { b } = bridge();
    const outcome = await b.handle({ type: "CP_IMPORT_READY", ok: false });
    expect(outcome.kind).toBe("ready");
    expect((outcome as { message: string }).message).toContain("扩展已连接");
  });

  it("别的消息一律忽略", async () => {
    const { b } = bridge();
    expect(await b.handle({ type: "SOMETHING" })).toEqual({ kind: "ignored" });
    expect(await b.handle(null)).toEqual({ kind: "ignored" });
    expect(await b.handle("CP_DELIVER_PROGRESS")).toEqual({ kind: "ignored" });
  });
});
