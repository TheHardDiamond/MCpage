<script lang="ts" setup>
import { computed } from 'vue'
import { withBase } from 'vitepress'

const props = withDefaults(
  defineProps<{
    title?: string
    icon?: string
    href?: string
    hoverable?: boolean
  }>(),
  {
    title: '',
    icon: '',
    href: '',
    hoverable: true,
  },
)

const isLink = computed(() => !!props.href)
const tag = computed(() => (isLink.value ? 'a' : 'div'))
</script>

<template>
  <component
    :is="tag"
    class="pixel-card pixel-border"
    :class="{ 'pixel-card--hoverable': hoverable }"
    :href="isLink ? withBase(href) : undefined"
  >
    <div v-if="title || icon" class="pixel-card__header">
      <span v-if="icon" class="pixel-card__icon">{{ icon }}</span>
      <span v-if="title" class="pixel-card__title">{{ title }}</span>
    </div>
    <div class="pixel-card__body">
      <slot />
    </div>
  </component>
</template>

<style scoped>
.pixel-card {
  display: block;
  padding: 16px;
  text-decoration: none;
  color: var(--pixel-color-text);
  transition:
    transform var(--pixel-transition-fast),
    border-color var(--pixel-transition-fast);
}

.pixel-card--hoverable:hover:not(:focus-visible) {
  transform: translateY(-2px);
  border-top-color: var(--pixel-color-accent-light);
  border-left-color: var(--pixel-color-accent-light);
}

.pixel-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.pixel-card__icon {
  font-size: var(--pixel-font-size-m);
  line-height: 1;
}

.pixel-card__title {
  font-family: var(--pixel-font-heading);
  font-size: var(--pixel-font-size-m);
  color: var(--pixel-color-text);
}

.pixel-card__body {
  font-size: var(--pixel-font-size-s);
  color: var(--pixel-color-text-muted);
  line-height: var(--pixel-line-height);
}
</style>
