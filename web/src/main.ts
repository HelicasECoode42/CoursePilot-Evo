import { createPinia } from "pinia";
import { createApp } from "vue";
import App from "./App.vue";
import { router } from "./router";
import { usePlanningStore } from "./stores/planning";
import "./styles.css";

const pinia = createPinia();
const app = createApp(App).use(pinia).use(router);
// 同步还原刷新前的会话、草稿与当前方案，再后台确认令牌是否仍有效（见 restoreSavedSession）。
void usePlanningStore().restoreSavedSession();
app.mount("#app");
