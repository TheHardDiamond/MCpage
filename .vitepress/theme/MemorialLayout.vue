<script setup>
import { Content, withBase } from 'vitepress'
</script>

<template>
  <header class="site-header">
    <a :href="withBase('/')">服务器纪念站</a>
    <nav aria-label="主导航">
      <a :href="withBase('/')">主页</a>
      <a :href="withBase('/chronicle.html')">纪事</a>
      <a :href="withBase('/status.html')">服务状态</a>
      <a :href="withBase('/wiki.html')">Mod Wiki</a>
    </nav>
  </header>
  <main><Content /></main>
  <footer>服务器纪念站 · Pixel Eco</footer>
</template>
