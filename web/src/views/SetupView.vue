<script setup lang="ts">
/**
 * 配置三步：装插件 → 在学校页面登录 → 导入学业记录。
 *
 * 三条边界：
 *  1. 不代学生登录学校系统、不碰学校密码、不存 cookie。第 2 步只是打开
 *     学校页面，登录由学生自己在那个页面上完成。
 *  2. 导入逻辑不在这里重写——第 3 步链到 /records?import=school，
 *     用的还是那一套已经跑通的 postMessage 链路。
 *  3. 插件探测不把「已有导入正在进行」当成「没装插件」。background.js
 *     在五分钟内重复收到 CP_START_IMPORT 会回 ok:false，所以只要有
 *     CP_IMPORT_READY 回来，不论 ok 真假，插件就是装着的。
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { api } from "../api";
import {
  describeExtensionPresent,
  describePortMismatch,
  isExtensionReply,
} from "../domain/extension-probe";

/** 学校学业情况页面。插件的 content script 只匹配这一个地址。 */
const SCHOOL_PAGE_URL =
  "https://jwxt.shu.edu.cn/jwglxt/xsxy/xsxyqk_cxXsxyqkIndex.html";

/**
 * 页面端口。默认读 location.port；允许注入是因为 jsdom 的 location.port
 * 不可改写，不注入就测不到「端口不对」这条分支。
 */
const props = defineProps<{ pagePort?: string }>();

type ProbeState = "idle" | "probing" | "present" | "silent";

const probe = ref<ProbeState>("idle");
const probeNote = ref("");
const openedSchoolPage = ref(false);
const detectedPort = ref("");

const pagePort = computed(() => props.pagePort ?? detectedPort.value);

let probeRequestId = "";
let probeTimer: ReturnType<typeof setTimeout> | null = null;

function probeExtension() {
  const mismatch = describePortMismatch(pagePort.value);
  if (mismatch !== null) {
    probe.value = "silent";
    probeNote.value = mismatch;
    return;
  }
  probeRequestId = crypto.randomUUID();
  probe.value = "probing";
  probeNote.value = "正在向插件发一次连接请求…";
  globalThis.window.postMessage(
    { type: "CP_START_IMPORT", requestId: probeRequestId },
    globalThis.location.origin,
  );
  if (probeTimer) clearTimeout(probeTimer);
  probeTimer = setTimeout(() => {
    if (probe.value !== "probing") return;
    probe.value = "silent";
    probeNote.value =
      "插件没有回应。可能是还没加载，也可能是加载后本页没刷新——装好后请刷新本页再探测。";
  }, 2500);
}

// eslint-disable-next-line no-undef
function receiveProbeReply(event: MessageEvent) {
  if (
    event.source !== globalThis.window ||
    event.origin !== globalThis.location.origin
  )
    return;
  if (!isExtensionReply(event.data)) return;
  if (probeTimer) clearTimeout(probeTimer);
  // ok 为假也说明插件在：五分钟内已有一次导入占着位，这不是「没装」。
  probe.value = "present";
  probeNote.value = describeExtensionPresent(event.data.ok);
}

function openSchoolPage() {
  openedSchoolPage.value = true;
  globalThis.window.open(SCHOOL_PAGE_URL, "_blank", "noopener,noreferrer");
}

onMounted(() => {
  detectedPort.value = globalThis.location.port;
  globalThis.window.addEventListener("message", receiveProbeReply);
});

onUnmounted(() => {
  if (probeTimer) clearTimeout(probeTimer);
  globalThis.window.removeEventListener("message", receiveProbeReply);
});
</script>

<template>
  <section class="question-card" aria-labelledby="setup-title">
    <p v-if="api.mode === 'fixture'" class="notice notice--demo" role="note">
      当前是演示模式：导入学校数据需要真实服务模式，这一页的第 3
      步在演示模式下不会真的写入。
    </p>
    <p class="eyebrow">配置 · 共三步</p>
    <h1 id="setup-title">接上你的学校数据</h1>

    <p class="notice" role="note">
      <strong>不替你登录。</strong>
      插件只在你自己已经登录的学校页面上，读那一页已经显示出来的文字；
      不读密码、不读 Cookie、不执行学校页面的代码，自己也不往任何地方上传。
    </p>

    <ol class="setup-steps">
      <li class="setup-step">
        <h2>第 1 步 · 装浏览器插件</h2>
        <p class="microcopy">
          插件在仓库的
          <code>browser-adapter/academic-progress/</code> 目录，用 Chrome
          的「加载已解压的扩展程序」装进去。安装说明在同目录的 README。
        </p>
        <button
          class="button button--secondary"
          type="button"
          :disabled="probe === 'probing'"
          @click="probeExtension"
        >
          {{ probe === "probing" ? "正在探测…" : "探测插件是否已装" }}
        </button>
        <p
          v-if="probeNote"
          class="setup-step__note"
          :class="
            probe === 'present'
              ? 'setup-step__note--ok'
              : probe === 'silent'
                ? 'setup-step__note--warn'
                : ''
          "
          role="status"
        >
          {{ probeNote }}
        </p>
      </li>

      <li class="setup-step">
        <h2>第 2 步 · 在学校页面登录</h2>
        <p class="microcopy">
          点下面的按钮，会在新标签打开学校的「学业情况查询」页面。
          <strong>在那一页用你自己的账号登录</strong>，登录完回到这里继续。
        </p>
        <button
          class="button button--secondary"
          type="button"
          @click="openSchoolPage"
        >
          打开学校学业情况页面
        </button>
        <p v-if="openedSchoolPage" class="setup-step__note" role="status">
          已在新标签打开。登录后那一页会出现插件的导入浮窗。
        </p>
      </li>

      <li class="setup-step">
        <h2>第 3 步 · 导入我的学业记录</h2>
        <p class="microcopy">
          这一步导入的是<strong>你学过哪些课、过没过</strong>。
          学校开设哪些课（培养方案）已经导好了，不用你再导；
          本学期「谁上课、周几第几节」要等选课开放才公开，现在拿不到。
        </p>
        <RouterLink class="button button--primary" to="/records?import=school">
          去导入学业记录
        </RouterLink>
      </li>
    </ol>

    <div class="setup-footer">
      <RouterLink class="button button--secondary" to="/me">
        配置好了，进入控制台
      </RouterLink>
      <RouterLink class="button button--quiet" to="/">返回首页</RouterLink>
    </div>
  </section>
</template>

<style scoped>
.setup-steps {
  list-style: none;
  margin: 1.25rem 0;
  padding: 0;
  display: grid;
  gap: 0.9rem;
}

.setup-step {
  padding: 1rem 1.1rem;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--wash);
}

.setup-step h2 {
  margin: 0 0 0.4rem;
  font-size: 1rem;
}

.setup-step .microcopy {
  margin: 0 0 0.75rem;
  line-height: 1.65;
}

.setup-step__note {
  margin: 0.6rem 0 0;
  font-size: 0.85rem;
  color: var(--soft);
  line-height: 1.6;
}

.setup-step__note--ok {
  color: var(--green);
}

.setup-step__note--warn {
  color: #8a5a12;
}

.setup-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}

@media (max-width: 540px) {
  .setup-footer {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
