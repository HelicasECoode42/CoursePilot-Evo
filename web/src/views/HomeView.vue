<script setup lang="ts">
import { api } from "../api";
</script>

<template>
  <section class="welcome" aria-labelledby="home-title">
    <p v-if="api.mode === 'fixture'" class="notice notice--demo" role="note">
      页面演示 · 以下为虚构资料
    </p>
    <div class="welcome-layout">
      <div class="welcome-copy">
        <p class="eyebrow">让选课有依据</p>
        <h1 id="home-title" tabindex="-1">下学期，<br />选适合你的课。</h1>
        <p class="welcome-lead">
          先看学分进度，再整理你想学的内容、上课偏好和时间安排，找到合适的课程组合。
        </p>
        <div class="welcome-actions">
          <RouterLink class="button button--primary" to="/setup"
            >开始规划 <span aria-hidden="true">↗</span></RouterLink
          >
          <RouterLink class="button button--secondary" to="/me"
            >查看我的学业</RouterLink
          >
        </div>
        <p class="microcopy">
          已有资料会直接沿用。引导中的每一项都可以返回修改。
        </p>
      </div>
      <div class="welcome-journey" aria-label="选课的三个步骤">
        <p class="welcome-journey__title">从学业进度，到一份课程方案</p>
        <ol>
          <li>
            <span class="journey-number">01</span>
            <div>
              <h2>了解目前的进度</h2>
              <p>导入学校学业情况，查看还缺哪些类别。</p>
            </div>
          </li>
          <li>
            <span class="journey-number">02</span>
            <div>
              <h2>说清楚你的取舍</h2>
              <p>成绩、作业、兴趣、职业方向和时间，都可以慢慢选。</p>
            </div>
          </li>
          <li>
            <span class="journey-number">03</span>
            <div>
              <h2>比较并调整方案</h2>
              <p>查看课程理由和评价依据，加入、删除或更换班次。</p>
            </div>
          </li>
        </ol>
      </div>
    </div>
    <div class="welcome-facts">
      <div><strong>学校培养方案</strong><span>课程与要求有来源</span></div>
      <div><strong>完整需求引导</strong><span>帮助你表达想法</span></div>
      <div><strong>可追溯的评价</strong><span>按课程和维度查看</span></div>
    </div>
    <details class="record-help welcome-details">
      <summary>资料来源与使用方式</summary>
      <p>
        课程目录来自导入的培养方案，来源核验状态随资料展示。历史评价不折算成分数或星级。
      </p>
      <p>
        缺少目标学期班次时，先保留课程建议，取得班次资料后再核验课表。CoursePilot
        不替你登录教务系统，不替你提交选课。
      </p>
    </details>
  </section>
</template>

<style scoped>
.welcome {
  padding-top: 1.5rem;
}
.welcome-layout {
  display: grid;
  grid-template-columns: 1.05fr 1fr;
  gap: 4rem;
  align-items: center;
}
.welcome-copy h1 {
  font-size: clamp(2.5rem, 4.5vw, 3.7rem);
  letter-spacing: -0.045em;
  line-height: 1.2;
  margin-block: 1rem 1.5rem;
}
.welcome-lead {
  max-width: 28rem;
  font-size: 1rem;
  color: var(--soft);
  line-height: 1.85;
}
.welcome-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
  margin-top: 1.8rem;
}
.welcome-actions .button {
  gap: 1.5rem;
}
.welcome-journey {
  background: var(--wash);
  border: 1px solid var(--line);
  border-radius: 20px;
  padding: 1.8rem;
}
.welcome-journey__title {
  margin: 0 0 1.6rem;
  font-size: 0.85rem;
  color: var(--soft);
}
.welcome-journey ol {
  list-style: none;
  padding: 0;
  margin: 0;
}
.welcome-journey li {
  display: flex;
  gap: 1rem;
  padding-block: 1.1rem;
  border-top: 1px solid var(--line);
}
.welcome-journey h2 {
  font-size: 1rem;
  margin: 0 0 0.35rem;
}
.welcome-journey li p {
  color: var(--soft);
  margin: 0;
  font-size: 0.85rem;
}
.journey-number {
  color: var(--green);
  font-size: 0.8rem;
  font-variant-numeric: tabular-nums;
  padding-top: 0.15rem;
}
.welcome-facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1.5rem;
  margin-top: 3.5rem;
  border-block: 1px solid var(--line);
  padding-block: 1.5rem;
}
.welcome-facts > div {
  display: grid;
  gap: 0.2rem;
  font-size: 0.9rem;
}
.welcome-facts span {
  color: var(--soft);
  font-size: 0.8rem;
}
.welcome-details {
  margin-top: 1.5rem;
  border: 0;
}
@media (max-width: 760px) {
  .welcome-layout {
    grid-template-columns: 1fr;
    gap: 2rem;
  }
  .welcome {
    padding-top: 0;
  }
  .welcome-facts {
    margin-top: 2rem;
    gap: 0.8rem;
  }
}
@media (max-width: 420px) {
  .welcome-facts {
    grid-template-columns: 1fr;
    gap: 1rem;
  }
  .welcome-journey {
    padding: 1.25rem;
  }
}
</style>
