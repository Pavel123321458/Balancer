import tailwindcss from '@tailwindcss/vite'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  const proxy = { '/api': {
    target: env.BALANCER_API_TARGET || 'http://127.0.0.1:8000',
    rewrite: (path: string) => path.replace(/^\/api/, ''),
  } }
  return { plugins: [tailwindcss()], server: { proxy }, preview: { proxy } }
})
