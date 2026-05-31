<template>
  <div>
    <h2 class="page-title">批量登录</h2>
    <p class="hint">
      流程：① CSV 导入账号 → ② 批量发码（按间隔自动排队）→ ③ 各手机收短信后在下方填验证码，或 CSV 导入 mobile,vcode 批量登录
    </p>

    <el-row :gutter="16" class="stats-row">
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover"><div class="stat-label">总账号</div><div class="stat-val">{{ stats?.total ?? 0 }}</div></el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover"><div class="stat-label">已登录</div><div class="stat-val ok">{{ stats?.logged_in ?? 0 }}</div></el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover"><div class="stat-label">待登录</div><div class="stat-val warn">{{ stats?.unlogged ?? 0 }}</div></el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover">
          <div class="stat-label">已发码待填</div>
          <div class="stat-val">{{ stats?.vcode_sent_pending_login ?? 0 }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="action-card">
      <template #header>批量操作</template>
      <el-space wrap>
        <el-button type="primary" :loading="sendingVcode" @click="startBatchVcode">
          批量发码（全部未登录）
        </el-button>
        <el-input-number v-model="intervalSec" :min="60" :max="180" :step="10" />
        <span class="hint-inline">发码间隔（秒）</span>
        <el-button @click="exportList(false)">导出待登录 CSV</el-button>
        <el-button @click="exportList(true)">导出已发码 CSV</el-button>
        <el-upload :show-file-list="false" accept=".csv" :http-request="onLoginCsv">
          <el-button type="success">导入 CSV 批量登录</el-button>
        </el-upload>
      </el-space>
      <p class="hint" style="margin-top: 8px">
        登录 CSV 格式：<code>mobile,vcode</code>（示例见 docs/accounts-login.example.csv）
      </p>
    </el-card>

    <el-card v-if="activeJob" class="job-card">
      <template #header>
        <span>任务 #{{ activeJob.id }} · {{ activeJob.status }} · {{ activeJob.progress }}%</span>
        <el-button v-if="activeJob.status === 'running'" size="small" type="danger" link @click="cancelJob">
          取消
        </el-button>
      </template>
      <el-progress :percentage="activeJob.progress" :status="jobProgressStatus" />
      <pre class="log-box">{{ jobLog }}</pre>
    </el-card>

    <el-card>
      <template #header>
        <div class="table-header">
          <span>待登录账号</span>
          <el-checkbox v-model="vcodeSentOnly" @change="loadList">仅已发码</el-checkbox>
        </div>
      </template>
      <el-table :data="list" v-loading="loading" stripe size="small">
        <el-table-column prop="mobile" label="手机号" width="130" />
        <el-table-column prop="city" label="城市" width="90" />
        <el-table-column prop="egress_group" label="出口组" width="90" />
        <el-table-column label="发码时间" width="160">
          <template #default="{ row }">{{ formatTime(row.vcode_sent_at) }}</template>
        </el-table-column>
        <el-table-column prop="last_error" label="最近错误" min-width="120" show-overflow-tooltip />
        <el-table-column label="验证码" width="140">
          <template #default="{ row }">
            <el-input v-model="vcodeMap[row.id]" size="small" maxlength="6" placeholder="4-6位" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link @click="sendOne(row)">发码</el-button>
            <el-button size="small" type="primary" link @click="loginOne(row)">登录</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100, 200]"
        layout="total, sizes, prev, pager, next"
        style="margin-top: 12px"
        @change="loadList"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import type { UploadRequestOptions } from "element-plus";
import {
  accountsApi,
  batchLoginApi,
  jobsApi,
  type BatchLoginStats,
  type JobItem,
  type UnloggedAccount,
} from "@/api";

const stats = ref<BatchLoginStats | null>(null);
const list = ref<UnloggedAccount[]>([]);
const loading = ref(false);
const page = ref(1);
const pageSize = ref(50);
const total = ref(0);
const vcodeSentOnly = ref(false);
const intervalSec = ref(90);
const sendingVcode = ref(false);
const vcodeMap = reactive<Record<number, string>>({});
const activeJob = ref<(JobItem & { log_text?: string }) | null>(null);
const jobLog = ref("");
let pollTimer: ReturnType<typeof setInterval> | null = null;

const jobProgressStatus = computed(() => {
  const s = activeJob.value?.status;
  if (s === "success") return "success";
  if (s === "failed") return "exception";
  return undefined;
});

function formatTime(iso?: string | null) {
  if (!iso) return "—";
  return iso.replace("T", " ").slice(0, 19);
}

async function loadStats() {
  stats.value = await batchLoginApi.stats();
}

async function loadList() {
  loading.value = true;
  try {
    const res = await batchLoginApi.unlogged(page.value, pageSize.value, vcodeSentOnly.value);
    list.value = res.items;
    total.value = res.total;
  } finally {
    loading.value = false;
  }
}

async function startBatchVcode() {
  sendingVcode.value = true;
  try {
    const res = await batchLoginApi.sendVcode({
      all_unlogged: true,
      interval_seconds: intervalSec.value,
    });
    ElMessage.success(`已启动，共 ${res.total} 个账号`);
    startPoll(res.job_id);
    loadStats();
  } catch (e) {
    ElMessage.error(String(e));
  } finally {
    sendingVcode.value = false;
  }
}

async function sendOne(row: UnloggedAccount) {
  try {
    await accountsApi.sendVcode(row.id);
    ElMessage.success("验证码已发送");
    loadList();
    loadStats();
  } catch (e) {
    ElMessage.error(String(e));
  }
}

async function loginOne(row: UnloggedAccount) {
  const vcode = (vcodeMap[row.id] || "").trim();
  if (vcode.length < 4) {
    ElMessage.warning("请输入验证码");
    return;
  }
  try {
    await accountsApi.login(row.id, vcode);
    ElMessage.success("登录成功");
    vcodeMap[row.id] = "";
    loadList();
    loadStats();
  } catch (e) {
    ElMessage.error(String(e));
  }
}

async function exportList(vcodeOnly: boolean) {
  const blob = await batchLoginApi.exportUnlogged(vcodeOnly);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = vcodeOnly ? "vcode_sent.csv" : "unlogged.csv";
  a.click();
  URL.revokeObjectURL(url);
}

async function onLoginCsv(opt: UploadRequestOptions) {
  try {
    const res = await batchLoginApi.loginCsv(opt.file as File);
    ElMessage.success(`批量登录已启动，共 ${res.total} 条`);
    startPoll(res.job_id);
  } catch (e) {
    ElMessage.error(String(e));
  }
}

function startPoll(jobId: number) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const j = await jobsApi.get(jobId);
    activeJob.value = j;
    jobLog.value = j.log_text || j.log_preview || "";
    if (j.status !== "running" && j.status !== "pending") {
      clearInterval(pollTimer!);
      pollTimer = null;
      loadStats();
      loadList();
    }
  }, 2000);
  jobsApi.get(jobId).then((j) => {
    activeJob.value = j;
    jobLog.value = j.log_text || j.log_preview || "";
  });
}

async function cancelJob() {
  if (!activeJob.value) return;
  await batchLoginApi.cancel(activeJob.value.id);
  ElMessage.info("已请求取消");
}

onMounted(async () => {
  await loadStats();
  await loadList();
});

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer);
});
</script>

<style scoped>
.page-title {
  margin-bottom: 4px;
}
.hint {
  color: #909399;
  font-size: 13px;
  margin-bottom: 16px;
}
.hint-inline {
  color: #909399;
  font-size: 12px;
}
.stats-row {
  margin-bottom: 16px;
}
.stat-label {
  color: #909399;
  font-size: 12px;
}
.stat-val {
  font-size: 24px;
  font-weight: 600;
  margin-top: 4px;
}
.stat-val.ok {
  color: #67c23a;
}
.stat-val.warn {
  color: #e6a23c;
}
.action-card {
  margin-bottom: 16px;
}
.job-card {
  margin-bottom: 16px;
}
.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.log-box {
  max-height: 200px;
  overflow: auto;
  font-size: 12px;
  white-space: pre-wrap;
  background: #1a1d24;
  color: #e6e6e6;
  padding: 12px;
  border-radius: 8px;
  margin-top: 8px;
}
</style>
