import { defineStore } from "pinia";
import { ref } from "vue";
import { authApi } from "@/api";

const TOKEN_KEY = "mt_admin_token";

export const useAuthStore = defineStore("auth", () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || "");
  const username = ref("");
  const role = ref("");
  const isSuperadmin = ref(false);

  async function login(user: string, pass: string) {
    const data = await authApi.login(user, pass);
    token.value = data.access_token;
    localStorage.setItem(TOKEN_KEY, data.access_token);
    const me = await authApi.me();
    username.value = me.username;
    role.value = me.role || "";
    isSuperadmin.value = !!me.is_superadmin;
  }

  async function fetchMe() {
    if (!token.value) return;
    try {
      const me = await authApi.me();
      username.value = me.username;
      role.value = me.role || "";
      isSuperadmin.value = !!me.is_superadmin;
    } catch {
      logout();
    }
  }

  function logout() {
    token.value = "";
    username.value = "";
    role.value = "";
    isSuperadmin.value = false;
    localStorage.removeItem(TOKEN_KEY);
  }

  return { token, username, role, isSuperadmin, login, logout, fetchMe };
});
