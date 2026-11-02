import { createRouter, createWebHistory } from "vue-router";
import { usePlanningStore } from "../stores/planning";
import { resolveQuestion } from "../domain/question-flow";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    // 入口三页。原先 "/" 直接 redirect 到问答向导，一打开就被塞进流程里，
    // 学校数据导入也没有人找得到。现有页面一个都没动，只是前面多了一层入口。
    { path: "/", component: () => import("../views/HomeView.vue") },
    { path: "/setup", component: () => import("../views/SetupView.vue") },
    { path: "/me", component: () => import("../views/DashboardView.vue") },
    {
      path: "/plan/questions/:questionId",
      component: () => import("../views/QuestionView.vue"),
    },
    { path: "/records", component: () => import("../views/RecordsView.vue") },
    {
      path: "/plan/credits",
      component: () => import("../views/CreditPlanView.vue"),
    },
    {
      path: "/plan/result",
      component: () => import("../views/ResultView.vue"),
    },
    // 这两条路由在守卫之外：守卫只管 /plan/questions/，新页面不会被它重定向。
    {
      path: "/plan/teachers",
      component: () => import("../views/TeacherView.vue"),
    },
    {
      path: "/report/runs/:runId",
      component: () => import("../views/ReportView.vue"),
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

router.beforeEach((to) => {
  if (to.path.startsWith("/plan/questions/")) {
    const store = usePlanningStore();
    const safeQuestion = resolveQuestion(String(to.params.questionId), {
      draft: store.draft,
      curricula: store.curricula,
      selectedCurriculumId: store.selectedCurriculumId,
      mode: store.planningMode,
    });
    const safePath = `/plan/questions/${safeQuestion}`;
    if (
      to.path !== safePath &&
      (store.sessionStatus === "ready" || store.curricula.length > 0)
    ) {
      return safePath;
    }
  }
  return true;
});
