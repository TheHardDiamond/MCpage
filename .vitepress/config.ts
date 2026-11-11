import { defineConfig } from 'vitepress'

export default defineConfig({
  srcDir: 'src',
  lang: 'zh-CN',
  title: '服务器纪念站',
  description: '社区纪事、皮肤站监控存档与 Minecraft 服务器状态',
  base: process.env.PAGES_BASE || '/',
  themeConfig: {},
})
