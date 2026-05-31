<template>
  <div>
    <h2 class="page-title">系统设置</h2>
    <el-row :gutter="16">
      <el-col :xs="24" :md="12">
        <el-card header="预约参数">
          <el-form v-if="form" label-width="140px">
            <el-form-item label="申购时间">
              <el-input v-model="form.schedule_target_time" placeholder="09:00:00" />
            </el-form-item>
            <el-form-item label="提前秒数">
              <el-input-number v-model="form.schedule_advance_seconds" :min="0" :max="30" />
            </el-form-item>
            <el-form-item label="默认选店">
              <el-select v-model="form.shop_strategy_default" style="width: 100%">
                <el-option label="库存最大" value="max_inventory" />
                <el-option label="低竞争" value="min_competition" />
                <el-option label="距离最近" value="nearest" />
              </el-select>
            </el-form-item>
            <el-form-item label="重试次数">
              <el-input-number v-model="form.retry_count" :min="1" :max="10" />
            </el-form-item>
            <el-divider content-position="left">大规模预约</el-divider>
            <el-form-item label="按出口组并行">
              <el-switch v-model="form.reserve_parallel_by_egress" />
            </el-form-item>
            <el-form-item label="最大并行组数">
              <el-input-number v-model="form.reserve_max_workers" :min="1" :max="64" />
            </el-form-item>
            <el-form-item label="定时分片大小">
              <el-input-number v-model="form.reserve_shard_size" :min="0" :max="200" />
              <span class="hint-inline">0=不分片；超此数量拆多个子任务</span>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="save">保存到 config.yaml</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="12">
        <el-card header="健康检查">
          <el-button @click="loadHealth" :loading="healthLoading">刷新</el-button>
          <ul class="health-list">
            <li v-for="(item, i) in healthItems" :key="i" :class="item.level">
              [{{ item.category }}] {{ item.message }}
            </li>
          </ul>
        </el-card>
      </el-col>
    </el-row>

    <el-card header="代理池 (proxy_pools)" style="margin-top: 16px">
      <el-space wrap style="margin-bottom: 12px">
        <el-button @click="loadProxies">刷新</el-button>
        <el-button @click="syncProxyKeys">从账号同步出口组</el-button>
        <el-button type="primary" :loading="testingProxy" @click="testProxies">检测全部代理</el-button>
        <el-button type="success" :loading="savingProxy" @click="saveProxies">保存代理配置</el-button>
        <el-button @click="addProxyRow">新增一行</el-button>
      </el-space>
      <el-table :data="proxyRows" size="small" stripe max-height="320">
        <el-table-column label="出口组" width="120">
          <template #default="{ row }">
            <el-input v-model="row.name" size="small" placeholder="ip001" />
          </template>
        </el-table-column>
        <el-table-column label="代理 URL" min-width="280">
          <template #default="{ row }">
            <el-input v-model="row.url" size="small" placeholder="http://或 socks5://" />
          </template>
        </el-table-column>
        <el-table-column label="账号数" width="80">
          <template #default="{ row }">{{ usageMap[row.name] ?? "—" }}</template>
        </el-table-column>
        <el-table-column label="检测" width="100">
          <template #default="{ row }">
            <el-tag v-if="testMap[row.name]" :type="testMap[row.name].ok ? 'success' : 'danger'" size="small">
              {{ testMap[row.name].ok ? `${testMap[row.name].latency_ms}ms` : "失败" }}
            </el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column width="60">
          <template #default="{ $index }">
            <el-button type="danger" link @click="proxyRows.splice($index, 1)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p class="hint">账号 <code>egress_group</code> 须与出口组名一致；组内账号串行、不同组并行预约。</p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { settingsApi, type ProxyTestItem } from "@/api";

const form = ref<Record<string, unknown> | null>(null);
const saving = ref(false);
const healthItems = ref<{ level: string; category: string; message: string }[]>([]);
const healthLoading = ref(false);
const proxyRows = ref<{ name: string; url: string }[]>([]);
const proxyUsage = ref<{ egress_group: string; account_count: number }[]>([]);
const testMap = ref<Record<string, ProxyTestItem>>({});
const savingProxy = ref(false);
const testingProxy = ref(false);

const usageMap = computed(() => {
  const m: Record<string, number> = {};
  for (const u of proxyUsage.value) {
    m[u.egress_group] = u.account_count;
  }
  return m;
});

async function load() {
  form.value = await settingsApi.get();
}

async function save() {
  if (!form.value) return;
  saving.value = true;
  try {
    await settingsApi.put(form.value);
    ElMessage.success("已保存");
  } finally {
    saving.value = false;
  }
}

async function loadHealth() {
  healthLoading.value = true;
  try {
    const res = await settingsApi.health();
    healthItems.value = res.items;
  } finally {
    healthLoading.value = false;
  }
}

async function loadProxies() {
  const res = await settingsApi.proxyPools();
  proxyRows.value = Object.entries(res.pools).map(([name, url]) => ({ name, url }));
  proxyUsage.value = res.usage;
}

async function syncProxyKeys() {
  const r = await settingsApi.syncProxyFromAccounts();
  ElMessage.success(`已同步，新增 ${r.added} 个出口组占位`);
  loadProxies();
}

async function saveProxies() {
  savingProxy.value = true;
  try {
    const pools: Record<string, string> = {};
    for (const r of proxyRows.value) {
      if (r.name.trim()) pools[r.name.trim()] = r.url.trim();
    }
    await settingsApi.putProxyPools(pools);
    ElMessage.success("代理池已保存到 config.yaml");
  } finally {
    savingProxy.value = false;
  }
}

async function testProxies() {
  testingProxy.value = true;
  try {
    const res = await settingsApi.testProxies();
    const m: Record<string, ProxyTestItem> = {};
    for (const item of res.items) m[item.name] = item;
    testMap.value = m;
    ElMessage.success(`检测完成：${res.ok_count}/${res.total} 可用`);
  } finally {
    testingProxy.value = false;
  }
}

function addProxyRow() {
  proxyRows.value.push({ name: "", url: "" });
}

onMounted(() => {
  load();
  loadHealth();
  loadProxies();
});
</script>

<style scoped>
.health-list {
  list-style: none;
  padding: 0;
  margin-top: 12px;
  font-size: 13px;
}
.health-list .ok {
  color: #67c23a;
}
.health-list .warn {
  color: #e6a23c;
}
.health-list .fail {
  color: #f56c6c;
}
.hint {
  color: #909399;
  font-size: 12px;
  margin-top: 8px;
}
.hint-inline {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}
</style>
