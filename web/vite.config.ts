import { defineConfig } from 'vitest/config'

export default defineConfig({
  // relative asset paths, so the built site works from any subpath
  base: './',
  test: { environment: 'node', css: { include: [/styles\.css/] } }, // fonts.test.ts reads styles.css
})
