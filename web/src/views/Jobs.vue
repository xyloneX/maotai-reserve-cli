<template>
  <div>
    <div class="toolbar">
      <h2 class="page-title">任务中心</h2>
      <el-button type="primary" @click="openCreate(false)">创建预约任务</el-button>
      <el-button @click="openCreate(true)">试跑</el-button>
    </div>
    <el-table :data="list" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="进度" width="100">
        <template #default="{ row }">
          <el-progress :percentage="row.progress" :stroke-width="8" />
        </template>
      </el-table-column>
      <el-table-column label="试跑" width="70">
        <template #default="{ row }">{{ row.dry_run ? "是" : "否" }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" :disabled="row.status === 'running'" @click="run(row)">
            执行
          </el-button>
          <el-button size="small" @click="viewLog(row)">日志</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showCreate" :title="createDry ? '试跑任务' : '预约任务'" width="90%" style="max-width: 480px">
      <el-form label-width="120px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item v-if="!createDry" label="等到 9 点再抢">
          <el-switch v-model="form.waitUntilReserve" />
          <span class="hint">开启后使用完整定时+捡漏波次（服务器需保持运行）</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="create">创建并执行</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showLog"
      title="任务日志（实时）"
      width="90%"
      style="max-width: 720px"
      @closed="stopStream"
    >
      <div v-if="streamStatus" class="stream-meta">
        <el-tag size="small">{{ streamStatus }}</el-tag>
        <el-progress :percentage="streamProgress" :stroke-width="6" style="flex: 1; max-width: 200px" />
      </div>
      <pre ref="logBoxRef" class="log-box">{{ logText }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { jobsApi, type JobItem } from "@/api";

const list = ref<JobItem[]>([]);
const showCreate = ref(false);
const createDry = ref(false);
const form = ref({ name: "每日申购", waitUntilReserve: false });
const showLog = ref(false);
const logText = ref("");
const streamStatus = ref("");
const streamProgress = ref(0);
const logBoxRef = ref<HTMLElement | null>(null);
const streamAbort = ref<AbortController | null>(null);

async function load() {
  list.value = await jobsApi.list();
}

function openCreate(dry: boolean) {
  createDry.value = dry;
  form.value.name = dry ? "试跑" : "正式预约";
  showCreate.value = true;
}

async function create() {
  const body = {
    name: form.value.name,
    type: "manual",
    dry_run: createDry.value,
    wait_until_reserve: form.value.waitUntilReserve,
  };
  const job = createDry.value ? await jobsApi.dryRun(body) : await jobsApi.create(body);
  showCreate.value = false;
  await jobsApi.run(job.id);
  ElMessage.success("任务已启动");
  load();
  viewLog(job);
}

async function run(row: JobItem) {
  await jobsApi.run(row.id);
  ElMessage.success("已启动");
  viewLog(row);
}

function scrollLogToBottom() {
  nextTick(() => {
    const el = logBoxRef.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

function stopStream() {
  streamAbort.value?.abort();
  streamAbort.value = null;
}

async function viewLog(row: JobItem) {
  stopStream();
  logText.value = "";
  streamStatus.value = row.status;
  streamProgress.value = row.progress;
  showLog.value = true;

  const j = await jobsApi.get(row.id);
  logText.value = j.log_text || j.log_preview || "";
  streamStatus.value = j.status;
  streamProgress.value = j.progress;
  scrollLogToBottom();

  if (j.status === "running" || j.status === "pending") {
    startStream(row.id);
  }
}

function startStream(jobId: number) {
  stopStream();
  const ac = new AbortController();
  streamAbort.value = ac;
  jobsApi.streamLogs(
    jobId,
    (chunk) => {
      if (chunk.error) return;
      streamStatus.value = chunk.status || "";
      streamProgress.value = chunk.progress ?? 0;
      if (chunk.delta) {
        logText.value += chunk.delta;
      } else if (chunk.log_text) {
        logText.value = chunk.log_text;
      }
      scrollLogToBottom();
      load();
    },
    ac.signal
  ).catch(() => {});
}

onMounted(load);
onUnmounted(stopStream);
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  align-items: center;
}
.hint {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
}
.stream-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.log-box {
  max-height: 400px;
  overflow: auto;
  font-size: 12px;
  white-space: pre-wrap;
  background: #1a1d24;
  color: #e6e6e6;
  padding: 12px;
  border-radius: 8px;
}
</style>
