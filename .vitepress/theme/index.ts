import type { Theme } from 'vitepress'
import Layout from './MemorialLayout.vue'
import Memorial from './Memorial.vue'
import './styles/fonts.css'
import './styles/vars.css'
import './memorial.css'

export default {
  Layout,
  enhanceApp({ app }) {
    app.component('Memorial', Memorial)
  },
} satisfies Theme
