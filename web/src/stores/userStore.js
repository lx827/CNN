import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useUserStore = defineStore('user', () => {
  // ========== State ==========
  const token = ref(localStorage.getItem('access_token') || '')

  // ========== Getters ==========
  const isLoggedIn = computed(() => !!token.value)

  // ========== Actions ==========
  function setToken(newToken) {
    token.value = newToken
    if (newToken) {
      localStorage.setItem('access_token', newToken)
    } else {
      localStorage.removeItem('access_token')
    }
  }

  function logout() {
    token.value = ''
    localStorage.removeItem('access_token')
  }

  return {
    token,
    isLoggedIn,
    setToken,
    logout,
  }
})
