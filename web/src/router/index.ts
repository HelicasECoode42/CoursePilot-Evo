import { createRouter, createWebHistory } from "vue-router";
import QuestionView from "../views/QuestionView.vue";
import RecordsView from "../views/RecordsView.vue";
import CreditPlanView from "../views/CreditPlanView.vue";
import ResultView from "../views/ResultView.vue";
import TeacherView from "../views/TeacherView.vue";
import ReportView from "../views/ReportView.vue";
import { usePlanningStore } from "../stores/planning";
import { resolveQuestion } from "../domain/question-flow";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/plan/questions/goals" },
    { path: "/plan/questions/:questionId", component: QuestionView },
    { path: "/records", component: RecordsView },
    { path: "/plan/credits", component: CreditPlanView },
    { path: "/plan/result", component: ResultView },
    // 这两条路由在守卫之外：守卫只管 /plan/questions/，新页面不会被它重定向。
    { path: "/plan/teachers", component: TeacherView },
    { path: "/report/runs/:runId", component: ReportView },
    { path: "/:pathMatch(.*)*", redirect: "/plan/questions/goals" },
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
