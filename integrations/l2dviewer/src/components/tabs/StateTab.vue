<script setup>
import { ref } from 'vue'
import { PanelRightClose, PanelRightOpen, Play } from 'lucide-vue-next'

defineProps({
  /** [{ id, label }] */
  items: { type: Array, required: true },
  /** 最近一次触发的动作组 id，用于高亮反馈 */
  active: { type: String, default: '' },
  title: { type: String, default: '' },
})

defineEmits(['select'])

/** 侧栏默认收起，靠右缘圆钮拉开 */
const collapsed = ref(true)
</script>

<template>
  <aside class="trigger-tabs" :class="{ collapsed }">
    <!-- 面板：蒙板式浮层，收起时整体滑出右缘 -->
    <div class="panel">
      <div class="panel-heading"><div><span class="eyebrow">ACTIONS</span><h2 v-if="title" class="title">{{ title }}</h2></div><span class="count">{{ items.length }}</span></div>
      <ul class="list">
        <li v-for="item in items" :key="item.id">
          <button class="card" :class="{ active: item.id === active }" type="button" @click="$emit('select', item.id)">
            <span class="label">{{ item.label ?? item.id }}</span>
            <span class="id">
              <Play :size="14" />
              {{ item.id }}
            </span>
          </button>
        </li>
      </ul>
      <p v-if="!items.length" class="empty">该模型没有可触发的状态动作</p>
    </div>
    <!-- 把手：垂直居中骑在面板左缘（即侧栏与舞台的分界线），收起后仍留在屏幕内 -->
    <button class="toggle" type="button" :aria-expanded="!collapsed" :aria-label="collapsed ? '展开状态触发' : '收起状态触发'" :title="collapsed ? '展开状态触发' : '收起状态触发'" @click="collapsed = !collapsed">
      <PanelRightClose v-if="!collapsed" :size="19" />
      <PanelRightOpen v-else :size="19" />
    </button>
  </aside>
</template>

<style scoped>
/* 与 SkinTab 镜像：贴右缘、向右滑出收起 */
.trigger-tabs {
  position: absolute;
  top: 0;
  bottom: 0;
  right: 0;
  z-index: 10;
  width: min(330px, calc(100% - 44px));
  transform: translateX(0);
  transition: transform 0.25s ease;
  user-select: none;
}

.trigger-tabs.collapsed {
  transform: translateX(100%);
}

.panel {
  width: 100%;
  height: 100%;
  overflow-y: auto;
  border-left: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(19, 20, 30, 0.94);
  backdrop-filter: blur(12px);
  scrollbar-width: thin;
  scrollbar-color: #535267 transparent;
}

/* 把手骑在面板左缘，随面板一起滑动 */
.toggle {
  position: absolute;
  top: 50%;
  left: -38px;
  transform: translateY(-50%);
  display: grid;
  place-items: center;
  width: 38px;
  height: 54px;
  padding: 0;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px 0 0 12px;
  background: rgba(30, 31, 44, 0.94);
  backdrop-filter: blur(12px);
  color: #8a8a93;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.toggle:hover {
  background: rgba(35, 35, 44, 0.9);
  color: #e8e8ee;
}

/* 左内边距需避开骑在面板左缘的把手（嵌入 32px），否则中段卡片会被盖住 */
.panel-heading { display: flex; align-items: end; justify-content: space-between; padding: 76px 20px 18px; }
.eyebrow { color: #9290aa; font: 700 10px/1 system-ui, sans-serif; letter-spacing: .16em; }
.title { margin-top: 7px; color: #f1f0f7; font: 700 20px/1.3 system-ui, sans-serif; }
.count { color: #9492a5; font: 500 12px system-ui, sans-serif; }

/* 窄栏：纵向单列行式卡片，比左侧大卡片紧凑 */
.list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
  padding: 4px 20px 24px;
  list-style: none;
}

.card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 10px 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
  color: #8a8a93;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}

.card:hover {
  border-color: rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.06);
  color: #c8c8d0;
}

.card.active {
  border-color: #8e83f3;
  background: rgba(126, 112, 229, 0.22);
  color: #e8e8ee;
}

.label {
  overflow: hidden;
  font: 600 15px/1.3 system-ui, sans-serif;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 右侧小字展示原始动作组 id，方便对照 model3.json */
.id {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
  font: 500 11px/1 ui-monospace, monospace;
  color: #55555e;
}

.card.active .id {
  color: #4fc08d;
}

.empty {
  padding: 12px 16px;
  color: #55555e;
  font: 13px/1.6 system-ui, sans-serif;
}
</style>
