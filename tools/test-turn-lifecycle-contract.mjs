import fs from 'node:fs';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');

function extractTopLevelFunction(name) {
  const re = new RegExp(`^(?:async\\s+)?function\\s+${name}\\s*\\(`, 'm');
  const match = re.exec(html);
  if (!match) throw new Error(`missing function: ${name}`);
  const rest = html.slice(match.index + match[0].length);
  const next = /^(?:async\s+)?function\s+[A-Za-z_$][\w$]*\s*\(/m.exec(rest);
  return html.slice(match.index, next ? match.index + match[0].length + next.index : html.length).trim();
}

function baseSnapshotContext() {
  return {
    SAVE_SCHEMA_VERSION: 2,
    HIST: [{ role: 'user', content: '原始输入' }],
    TOKENS: 12,
    WORLD: 'fantasy',
    PACE: 'long',
    QUESTS: { main: [{ title: '找工作' }], side: [] },
    INVENTORY: [{ name: '面包', count: 1 }],
    SKILLS: [],
    PINS: [],
    PLAYER_CANON: { name: '测试者' },
    WORLD_CLOCK: 3,
    EVENT_THRESHOLD: 8,
    LOREBOOK: [],
    TURNS: 2,
    _lastMemTurn: 0,
    OUTLINE: '',
    STORY_RUNTIME: { current_scene: { id: 'scene-1' } },
    GAME_STATE: { hp: 10, attrs: { 体质: 2 } },
    STATE_ACTIVE: true,
    TURN_BACKUPS: [],
    SHEET_INIT_ARMED: false,
    PREMISE_STATE: { kind: 'none' },
    OPENING_TEXT: '',
    OPENING_PICK: '',
    STORY_DNA: '',
    EFFECTIVE_SETUP: {},
    STORY_TONE: '生活冒险',
    TONE_DESC: '',
    TONE_TRANS: '',
    NAMES: '',
    CHATPATH: '/chat/completions',
    WORLD_PRESET: '',
    PREFS: {},
    WORLDS: { __custom__: null },
    LORE: { sid: 'save-1' },
    LORE_PENDING: [{ turn: 2, text: '待写入事实' }],
    getDesc: () => '测试存档',
    structuredClone,
  };
}

function snapshotIsDetached() {
  const context = vm.createContext(baseSnapshotContext());
  vm.runInContext(`${extractTopLevelFunction('snapshot')}\nresult = snapshot();`, context);
  const saved = context.result;
  context.HIST[0].content = '后来被改写';
  context.GAME_STATE.hp = 1;
  context.LORE_PENDING[0].text = '后来被覆盖';
  return saved.history[0].content === '原始输入'
    && saved.gstate.hp === 10
    && saved.lorePending[0].text === '待写入事实';
}

async function failedTurnLeavesNoPartialCommit() {
  const context = vm.createContext({
    LOADING: false,
    TURN_BACKUPS: [],
    GAME_STATE: { revealed: true },
    QUESTS: { main: [], side: [] },
    INVENTORY: [],
    SKILLS: [],
    TOKENS: 30,
    _lastMemTurn: 4,
    EVENT_THRESHOLD: 8,
    OUTLINE: '旧大纲',
    STORY_RUNTIME: { current_scene: { id: 'old' } },
    STORY_AGENT: { busy: false, lastError: '', lastAttemptTurn: 7 },
    NAMES: '老板',
    STATE_ACTIVE: true,
    SHEET_INIT_ARMED: false,
    PREMISE_STATE: { kind: 'none' },
    LORE_PENDING: [{ turn: 7, text: '旧批次' }],
    LORE: { ctx: '旧上下文', names: [], conflicts: [], trace: [], counts: {} },
    BK: 'ds',
    addBlk: () => {},
    HIST: [{ role: 'assistant', content: '上一回合' }],
    WORLD_CLOCK: 4,
    TURNS: 7,
    renderCharacterSheet: () => {},
    syncStateCollections: () => {},
    renderQuests: () => {},
    renderInventory: () => {},
    renderSkills: () => {},
    renderNpcs: () => {},
    rebuildLog: () => {},
    freshGameState: () => ({}),
    migrateGameState: (state) => state,
    document: { getElementById: () => ({ textContent: '', focus: () => {} }) },
    _runTurn: async () => { throw new Error('simulated request failure'); },
  });
  vm.runInContext([
    extractTopLevelFunction('runtimeBackup'),
    extractTopLevelFunction('beginTurnTransaction'),
    extractTopLevelFunction('commitTurnTransaction'),
    extractTopLevelFunction('rollbackTurnTransaction'),
    extractTopLevelFunction('restoreRuntime'),
    extractTopLevelFunction('send'),
  ].join('\n'), context);
  const result = await context.send('这一回合会失败', false);
  return result === false
    && context.LOADING === false
    && context.TURNS === 7
    && context.WORLD_CLOCK === 4
    && context.HIST.length === 1
    && context.TURN_BACKUPS.length === 0;
}

async function undoWaitsForServerRollback() {
  let release;
  const context = vm.createContext({
    LOADING: false,
    TURN_BACKUPS: [{ turns: 0, wclock: 0 }],
    HIST: [
      { role: 'user', content: '去茶馆' },
      { role: 'assistant', content: '你到了茶馆。' },
    ],
    TURNS: 1,
    LORE: { on: true },
    addBlk: () => {},
    restoreRuntime: () => {},
    rebuildLog: () => {},
    autoSaved: false,
    autoSave: () => { context.autoSaved = true; },
    document: { getElementById: () => ({ focus: () => {} }) },
    loreRollback: () => new Promise((resolve) => { release = resolve; }),
  });
  vm.runInContext(extractTopLevelFunction('undoTurn'), context);
  const pending = context.undoTurn();
  await Promise.resolve();
  const waits = Boolean(pending && typeof pending.then === 'function')
    && context.LOADING === true
    && context.HIST.length === 2
    && context.TURN_BACKUPS.length === 1;
  if (release) release({ facts: 1 });
  if (pending && typeof pending.then === 'function') await pending;
  return waits && context.LOADING === false && context.autoSaved
    && context.HIST.length === 0 && context.TURN_BACKUPS.length === 0;
}

function conflictQueueUsesTwoPhaseConsume() {
  const context = vm.createContext({
    LORE: { conflicts: [{ description: '旧冲突' }] },
    TURN_BACKUPS: [],
  });
  vm.runInContext([
    extractTopLevelFunction('loreConflictNote'),
    extractTopLevelFunction('commitTurnTransaction'),
  ].join('\n'), context);
  const note = context.loreConflictNote();
  const retainedBeforeCommit = note.includes('旧冲突') && context.LORE.conflicts.length === 1;
  context.LORE.conflicts.push({ description: '生成期间到达的新冲突' });
  context.commitTurnTransaction({ conflictCount: 1, committed: false });
  return retainedBeforeCommit
    && context.LORE.conflicts.length === 1
    && context.LORE.conflicts[0].description === '生成期间到达的新冲突';
}

function durableLedgerPrecedesAutosave() {
  const run = extractTopLevelFunction('_runTurn');
  const ledger = Math.max(
    run.lastIndexOf('await commitCompletedTurnServer(tx,TURNS,reply,lastUser)'),
    run.lastIndexOf('await loreRecordLedger(TURNS,reply,lastUser)'),
  );
  const save = run.lastIndexOf('autoSave()');
  return ledger >= 0 && save > ledger;
}

function pendingCommitHasRecoveryPath() {
  return html.includes("var PENDING_TURN_KEY='pending_turn_commit'")
    && html.includes("await idbPut(PENDING_TURN_KEY,pending)")
    && html.includes("async function recoverPendingTurnCommit()")
    && html.includes("applySnapshot(payload,{skipLoreResume:true})")
    && html.includes("if(recovered)return false;");
}

function saveConflictHasExplicitChoices() {
  return html.includes('function showSaveConflict(slot,localSnapshot,e,automatic)')
    && html.includes("modalAction('保留本机版本并覆盖服务端'")
    && html.includes("modalAction('读取服务端版本'")
    && html.includes("showSaveConflict('auto',localSnapshot,e,true)")
    && html.includes("showSaveConflict('sv_'+i,localSnapshot,e,false)");
}

function monitorTracksCommitLifecycle() {
  return html.includes("monitorStart('commit','提交第 '+turn+' 回合'")
    && html.includes("monitorStart('commit','恢复待提交回合'")
    && html.includes("monitorStart('commit','等待处理存档冲突'")
    && html.includes("monitorFail(commitMonitor,e,{pendingCommit:true");
}

function monitorUsesTraceableIds() {
  return html.includes('runId:id,parentId:String')
    && html.includes('sessionId:String(opt.sessionId===undefined?')
    && html.includes('turnId:Number(opt.turnId===undefined?TURNS:opt.turnId)')
    && html.includes('session_id=')
    && html.includes('parent_id=')
    && html.includes('MONITOR_PARENT_ID=pipelineRun');
}

function monitorCallSitesCarryContext() {
  return html.includes('sessionId:callMeta.sessionId===undefined?')
    && html.includes('parentId:callMeta.parentId===undefined?MONITOR_PARENT_ID')
    && html.includes("var commitMonitor=monitorStart('commit','提交第 '+turn+' 回合',{sessionId:LORE.sid")
    && html.includes("var recoveryMonitor=monitorStart('commit','恢复待提交回合',{sessionId:LORE.sid")
    && html.includes("var conflictMonitor=monitorStart('commit','等待处理存档冲突',{sessionId:LORE.sid");
}

const cases = [
  ['存档快照必须与运行时对象彻底脱离', snapshotIsDetached()],
  ['模型请求失败不能提交半个回合', await failedTurnLeavesNoPartialCommit()],
  ['撤销必须等待服务端回滚成功后再改本地历史', await undoWaitsForServerRollback()],
  ['冲突提示必须在回合提交成功后才从队列消费', conflictQueueUsesTwoPhaseConsume()],
  ['服务端结构化账本提交必须早于本地自动存档', durableLedgerPrecedesAutosave()],
  ['服务端提交断响应后必须保留并恢复 pending commit', pendingCommitHasRecoveryPath()],
  ['存档冲突必须提供本机/服务端/稍后处理选择', saveConflictHasExplicitChoices()],
  ['监视器必须记录提交、恢复和冲突生命周期', monitorTracksCommitLifecycle()],
  ['AgentRun 必须带 session/turn/run/parent 可追踪 ID', monitorUsesTraceableIds()],
  ['AgentRun 调用点必须显式携带会话、回合和父运行上下文', monitorCallSitesCarryContext()],
];

for (const [name, passed] of cases) assert.equal(passed, true, name);
console.log(`turn lifecycle contract: ${cases.length} cases passed`);
