<script setup lang="ts">
import { inject } from 'vue'

const station = inject<Record<string, any>>('cloudStation')!
const { kbFiles, kbActiveFile, kbContent, kbLoading, kbSaving, kbSaved, loadKnowledgeFiles, openKnowledgeFile, submitKnowledgeSave, formatFileSize } = station
loadKnowledgeFiles()
</script>

<template>
<main class="main main-logs">
      <div class="knowledge-page">
        <div class="knowledge-layout">
          <div class="knowledge-file-list">
            <div class="panel-title">知识库文件</div>
            <div v-if="kbFiles.length" class="kb-file-items">
              <div
                v-for="f in kbFiles"
                :key="f.name"
                class="kb-file-item"
                :class="{ active: kbActiveFile === f.name }"
                @click="openKnowledgeFile(f.name)"
              >
                <span class="kb-file-name">{{ f.name }}</span>
                <span class="kb-file-size">{{ formatFileSize(f.size) }}</span>
              </div>
            </div>
            <div v-else class="empty-state">加载中...</div>
          </div>
          <div class="knowledge-editor">
            <div class="panel-title" style="display:flex;justify-content:space-between;align-items:center">
              <span>{{ kbActiveFile || '选择文件' }}</span>
              <button
                v-if="kbActiveFile"
                class="btn btn-primary"
                type="button"
                :disabled="kbSaving"
                @click="submitKnowledgeSave"
              >
                {{ kbSaving ? '保存中...' : '保存' }}
              </button>
            </div>
            <textarea
              v-if="kbActiveFile"
              v-model="kbContent"
              class="kb-editor-textarea"
              :disabled="kbLoading"
            ></textarea>
            <div v-else class="empty-state" style="margin-top:60px">选择左侧文件以编辑</div>
            <div v-if="kbSaved" class="kb-saved-hint">已保存</div>
          </div>
        </div>
      </div>
    </main>
</template>
