<template>
  <v-hover v-slot="{ isHovering, props }">
    <div v-bind="props" class="hover-wrapper" ref="wrapperRef">
      <span :class="{ 'has-image': !!imageUrl }">
        {{ slotText }}
      </span>

      <div
        v-if="isHovering && imageUrl"
        class="hover-content"
        :style="hoverStyle"
      >
        <v-img
          :src="fullImageUrl"
          class="hover-image"
          contain
        />
      </div>
      <!-- 无预览图 -->
      <!-- <span 
        v-else-if="isHovering && !imageUrl" 
        class="no-image-text"
        :style="hoverStyle">
        无预览图
      </span> -->
    </div>
  </v-hover>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { BASE_URL } from '@/constant/filePathBase'

const props = defineProps<{
  imageUrl?: string
  slotText?: string
}>()

const wrapperRef = ref<HTMLElement | null>(null)

const fullImageUrl = computed(() => {
  if (!props.imageUrl) return ''
  if (/^https?:\/\//.test(props.imageUrl)) return props.imageUrl
  return `${ BASE_URL }${ props.imageUrl }`
})

const hoverStyle = ref<Record<string, string>>({})

const updateHoverPosition = () => {
  if (!wrapperRef.value) return
  const rect = wrapperRef.value.getBoundingClientRect()
  const popupHeight = 110

  const tableEl = wrapperRef.value.closest('.vxe-table') as HTMLElement
  let headerBottom = 0
  if (tableEl) {
    const thead = tableEl.querySelector('thead')
    if (thead) {
      const thRect = thead.getBoundingClientRect()
      headerBottom = thRect.bottom
    }
  }

  const spaceAbove = rect.top - headerBottom

  if (spaceAbove >= popupHeight) {
    hoverStyle.value = { bottom: '100%', top: 'auto', left: '50%', transform: 'translateX(-50%)' }
  } else {
    hoverStyle.value = { top: '100%', bottom: 'auto', left: '50%', transform: 'translateX(-50%)' }
  }
}

onMounted(() => {
  if (wrapperRef.value) {
    wrapperRef.value.addEventListener('mouseenter', updateHoverPosition)
  }
})

onUnmounted(() => {
  if (wrapperRef.value) {
    wrapperRef.value.removeEventListener('mouseenter', updateHoverPosition)
  }
})
</script>

<style scoped>
.hover-wrapper {
  position: relative;
  display: inline-block;
}

.hover-content {
  position: absolute;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #ccc;
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
  background-color: #fff;
  padding: 4px;
  width: 110px;
  height: 110px;
}

.hover-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}
 
.no-image-text {
  position: absolute;
  z-index: 1000;
  width: 110px;
  height: 110px;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
  border: 1px solid #ccc;
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  left: 50%;
  transform: translateX(-50%);
}
.has-image {
  color: #1a73e8;
  text-decoration: underline;
  cursor: pointer;
}

</style>
