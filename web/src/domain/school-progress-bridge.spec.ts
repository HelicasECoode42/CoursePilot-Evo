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
  it("重复连接保留登记中的请求号，回到资料页后仍能接收", async () => {
    const { b, save } = bridge();
    const id = b.requestImport();
    expect(b.requestImport()).toBe(id);
    expect((await b.handle(deliver(id))).kind).toBe("saved");
    expect(save).toHaveBeenCalledOnce();
    expect(b.requestImport()).not.toBe(id);
  });

  it("保存尚未完成时的重复投递共用同一次保存", async () => {
    let finish!: () => void;
    const save = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
    );
    const { b, posted } = bridge(save);
    const id = b.requestImport();
    const first = b.handle(deliver(id));
    const second = b.handle(deliver(id));
    expect(save).toHaveBeenCalledOnce();
    expect(posted).not.toContainEqual({
      type: "CP_IMPORT_ACCEPTED",
      requestId: id,
      ok: true,
    });
    finish();
    expect((await first).kind).toBe("saved");
    expect((await second).kind).toBe("saved");
  });
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

  it("连接被另一个待处理导入占用时明确提示返回原页面", async () => {
    const { b } = bridge();
    const outcome = await b.handle({ type: "CP_IMPORT_READY", ok: false });
    expect(outcome).toEqual({
      kind: "failed",
      message:
        "另一个 CoursePilot 页面有待完成的导入，请返回原页面，或完成后再连接。",
    });
  });

  it("别的消息一律忽略", async () => {
    const { b } = bridge();
    expect(await b.handle({ type: "SOMETHING" })).toEqual({ kind: "ignored" });
    expect(await b.handle(null)).toEqual({ kind: "ignored" });
    expect(await b.handle("CP_DELIVER_PROGRESS")).toEqual({ kind: "ignored" });
  });
});
