import { createRouter, createWebHistory } from "vue-router";
import QuestionView from "../views/QuestionView.vue";
import ResultView from "../views/ResultView.vue";
import { usePlanningStore } from "../stores/planning";
import { resolveQuestion } from "../domain/question-flow";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/plan/questions/goals" },
    { path: "/plan/questions/:questionId", component: QuestionView },
    { path: "/plan/result", component: ResultView },
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
