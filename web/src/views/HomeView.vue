<script setup lang="ts">
/**
 * 欢迎页。
 *
 * 这一页不发任何请求、不建会话：它只是入口，让人先知道这是什么，
 * 再决定去配置还是直接进控制台。原先 `/` 直接 redirect 到问答向导，
 * 一打开就被塞进流程里，学校数据导入也没人找得到。
 */
import { api } from "../api";
</script>

<template>
  <section class="question-card" aria-labelledby="home-title">
    <p v-if="api.mode === 'fixture'" class="notice notice--demo" role="note">
      当前是演示模式：页面里的内容是虚构示例，不是真实教务数据。
    </p>
    <p class="eyebrow">CoursePilot</p>
    <h1 id="home-title">按你的培养方案，把下学期的课想清楚</h1>

    <div class="home-intro">
      <p>
        把培养方案和你已修的课对上，算出每个类别还差多少学分，
        再结合同学留下的课程评价，帮你挑下学期要上的课。
      </p>
      <p>
        课程、学分、要求类别都来自学校的培养方案；课程评价来自真实的
        学生记录，只给条数和维度标签，<strong>不折算成分数或星级</strong>。
      </p>
      <p class="home-intro__limit">
        做不到的也说清楚：<strong>不替你登录教务系统，不替你提交选课。</strong>
        本学期「谁上课、周几第几节」只在选课开放后才公开，现在拿不到，
        所以课表功能是用演示班次跑的。
      </p>
    </div>

    <div class="home-actions">
      <RouterLink class="button button--primary" to="/setup"
        >开始配置</RouterLink
      >
      <RouterLink class="button button--secondary" to="/me">
        我已配置过，进入控制台
      </RouterLink>
    </div>

    <p class="microcopy">
      配置一共三步：装浏览器插件、在学校页面登录、导入你的学业记录。
    </p>
  </section>
</template>

<style scoped>
.home-intro {
  display: grid;
  gap: 0.75rem;
  margin: 1.25rem 0 1.5rem;
  max-width: 46rem;
}

.home-intro p {
  margin: 0;
  line-height: 1.7;
}

.home-intro__limit {
  padding: 0.85rem 1rem;
  border-radius: 12px;
  background: var(--wash);
  border: 1px solid var(--line);
  color: var(--soft);
}

.home-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

@media (max-width: 540px) {
  .home-actions {
    flex-direction: column;
  }

  .home-actions > * {
    width: 100%;
    text-align: center;
  }
}
</style>
