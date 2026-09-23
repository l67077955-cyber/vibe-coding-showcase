/* CS:GO Web —— 武器数据/玩家对象/全局状态 */
'use strict';

/* ---------------- 武器 ---------------- */
// 数值对齐 CS:GO：pen 穿甲率 / fall 每10m距离衰减 / mv 持枪移速 / reward 击杀奖励 / zooms AWP 双段变焦
const WEAPONS = {
  usp:    { name: 'USP-S',   dmg: 35,  hs: 4, mag: 12, reserve: Infinity, rpm: 352, reload: 2.2, auto: false, price: 0,    recoil: 0.0035, snd: 'pistol', zoom: 1.10,
            pen: 0.505, fall: 0.84, mv: 0.96, reward: 300,
            inacc: { stand: 0.0040, move: 0.012, jump: 0.035, crouch: 0.7, fire: 0.0035, decay: 7 } },
  deagle: { name: '沙漠之鹰', dmg: 53,  hs: 4, mag: 7,  reserve: 35,      rpm: 267, reload: 2.2, auto: false, price: 700,  recoil: 0.009,  snd: 'deagle', zoom: 1.15,
            pen: 0.932, fall: 0.86, mv: 0.92, reward: 300,
            inacc: { stand: 0.0050, move: 0.022, jump: 0.060, crouch: 0.75, fire: 0.012, decay: 4.5 } },
  ak47:   { name: 'AK-47',   dmg: 36,  hs: 4, mag: 30,  reserve: 90,      rpm: 600, reload: 2.4, auto: true,  price: 2700, recoil: 0.0055, snd: 'ak', zoom: 1.18,
            pen: 0.775, fall: 0.98, mv: 0.86, reward: 300,
            inacc: { stand: 0.0045, move: 0.045, jump: 0.080, crouch: 0.75, fire: 0.0038, decay: 5.5 } },
  m4a1:   { name: 'M4A4',    dmg: 33,  hs: 4, mag: 30,  reserve: 90,      rpm: 666, reload: 3.1, auto: true,  price: 3100, recoil: 0.0045, snd: 'm4', zoom: 1.20,
            pen: 0.70, fall: 0.98, mv: 0.90, reward: 300,
            inacc: { stand: 0.0040, move: 0.040, jump: 0.075, crouch: 0.7, fire: 0.0034, decay: 6 } },
  awp:    { name: 'AWP',     dmg: 115, hs: 4, mag: 5,   reserve: 30,      rpm: 41,  reload: 3.7, auto: false, price: 4750, recoil: 0.02,   snd: 'awp', scope: true, zooms: [1, 2.5, 6.8],
            pen: 0.975, fall: 0.99, mv: 0.80, reward: 100,
            inacc: { stand: 0.045, move: 0.09, jump: 0.12, crouch: 0.6, fire: 0.02, decay: 2.5 } },
  knife:  { name: '军刀',   dmg: 40,  hs: 2, mag: Infinity, reserve: Infinity, rpm: 180, reload: 0.1, auto: false, price: 0,    recoil: 0.001, snd: 'knife', melee: true, zoom: 1,
            pen: 1, fall: 1, mv: 1.0, reward: 1500,
            inacc: { stand: 0.001, move: 0.001, jump: 0.001, crouch: 1, fire: 0, decay: 1 } },
  he:     { name: '高爆手雷', nade: 'he', dmg: 0, hs: 1, mag: Infinity, reserve: Infinity, rpm: 60, reload: 0.1, auto: false, price: 300, recoil: 0.002, snd: 'knife', zoom: 1,
            pen: 1, fall: 1, mv: 0.95, reward: 300,
            inacc: { stand: 0.001, move: 0.001, jump: 0.001, crouch: 1, fire: 0, decay: 1 } },
  flash:  { name: '闪光弹', nade: 'flash', dmg: 0, hs: 1, mag: Infinity, reserve: Infinity, rpm: 60, reload: 0.1, auto: false, price: 200, recoil: 0.002, snd: 'knife', zoom: 1,
            pen: 1, fall: 1, mv: 0.97, reward: 300,
            inacc: { stand: 0.001, move: 0.001, jump: 0.001, crouch: 1, fire: 0, decay: 1 } },
};
// 确定性可学习弹道（Source 式压枪曲线）：前几发直线 → 垂直爬升 → 左右摆动
const SPRAY = {};
(function buildSprays() {
  const mk = (n, climb, hAmp, phase) => {
    const arr = []; let y = 0;
    for (let i = 1; i <= n; i++) {
      y += i <= 8 ? climb * (0.35 + i * 0.13) : climb * 1.39 * Math.exp(-(i - 8) * 0.18);
      const hx = i > 6 ? Math.sin((i - 6) * 0.55 + phase) * hAmp * Math.min(1, (i - 6) / 5) : 0;
      arr.push({ x: hx, y });
    }
    return arr;
  };
  SPRAY.ak47 = mk(30, 0.0072, 0.012, 0);
  SPRAY.m4a1 = mk(30, 0.0058, 0.009, 1.2);
  SPRAY.deagle = mk(7, 0.012, 0.006, 0.5);
  SPRAY.usp = mk(12, 0.004, 0.004, 2);
  SPRAY.awp = mk(5, 0.01, 0, 0);
})();
// 每枪换弹动画关键帧（k: 0→1，姿态偏移：rx 前倾 / ry 内转 / rz 侧滚 / y z 位移）
const Z0 = { rx: 0, ry: 0, rz: 0, y: 0, z: 0 };
const RELOAD_KEY = {
  usp: [ // 侧倾拔匣 → 倒匣 → 进匣上抬 → 拉套筒
    [0, Z0], [0.12, { rx: -0.5, ry: 0, rz: 0.4, y: -0.03, z: 0 }],
    [0.38, { rx: -0.55, ry: 0, rz: 0.42, y: -0.09, z: 0 }],
    [0.56, { rx: -0.5, ry: 0, rz: 0.35, y: -0.02, z: 0 }],
    [0.7, { rx: -0.62, ry: 0, rz: 0.2, y: -0.05, z: 0.03 }],
    [0.82, { rx: -0.25, ry: 0, rz: 0.08, y: 0, z: -0.01 }],
    [1, Z0],
  ],
  deagle: [ // 同手枪但动作更大更沉
    [0, Z0], [0.12, { rx: -0.55, ry: 0, rz: 0.5, y: -0.04, z: 0 }],
    [0.4, { rx: -0.6, ry: 0, rz: 0.52, y: -0.12, z: 0 }],
    [0.58, { rx: -0.52, ry: 0, rz: 0.4, y: -0.02, z: 0 }],
    [0.72, { rx: -0.68, ry: 0, rz: 0.2, y: -0.06, z: 0.04 }],
    [0.85, { rx: -0.2, ry: 0, rz: 0.06, y: 0, z: -0.015 }],
    [1, Z0],
  ],
  ak47: [ // 内翻拔匣 → 下拉倒匣 → 顶入新匣 → 拉机匣（后拉前推）
    [0, Z0], [0.1, { rx: -0.4, ry: 0.3, rz: 0.1, y: -0.04, z: 0 }],
    [0.35, { rx: -0.45, ry: 0.35, rz: 0.15, y: -0.11, z: 0 }],
    [0.55, { rx: -0.4, ry: 0.3, rz: 0.1, y: -0.01, z: 0 }],
    [0.68, { rx: -0.52, ry: 0.24, rz: 0, y: -0.02, z: 0.06 }],
    [0.8, { rx: -0.12, ry: 0.08, rz: 0, y: 0, z: -0.02 }],
    [1, Z0],
  ],
  m4a1: [ // 与 AK 同族，更利落
    [0, Z0], [0.1, { rx: -0.42, ry: -0.28, rz: -0.1, y: -0.04, z: 0 }],
    [0.32, { rx: -0.48, ry: -0.32, rz: -0.14, y: -0.1, z: 0 }],
    [0.52, { rx: -0.42, ry: -0.26, rz: -0.08, y: -0.01, z: 0 }],
    [0.66, { rx: -0.55, ry: -0.2, rz: 0, y: -0.02, z: 0.055 }],
    [0.78, { rx: -0.1, ry: -0.06, rz: 0, y: 0, z: -0.02 }],
    [1, Z0],
  ],
  awp: [ // 慢速大动作：旋枪拔匣 → 换匣 → 压实 → 上膛
    [0, Z0], [0.14, { rx: -0.32, ry: 0.45, rz: 0.2, y: -0.05, z: 0 }],
    [0.42, { rx: -0.38, ry: 0.5, rz: 0.22, y: -0.14, z: 0 }],
    [0.68, { rx: -0.32, ry: 0.4, rz: 0.15, y: -0.03, z: 0 }],
    [0.84, { rx: -0.5, ry: 0.3, rz: 0.05, y: -0.04, z: 0.05 }],
    [0.93, { rx: -0.1, ry: 0.1, rz: 0, y: 0, z: -0.015 }],
    [1, Z0],
  ],
};
function reloadPose(id, k) {
  const kf = RELOAD_KEY[id] || RELOAD_KEY.ak47;
  for (let i = 1; i < kf.length; i++) {
    if (k <= kf[i][0]) {
      const [t0, p0] = kf[i - 1], [t1, p1] = kf[i];
      const u = (k - t0) / Math.max(t1 - t0, 1e-6);
      const o = {};
      for (const key2 of ['rx', 'ry', 'rz', 'y', 'z']) o[key2] = (p0[key2] || 0) + ((p1[key2] || 0) - (p0[key2] || 0)) * u;
      return o;
    }
  }
  return Z0;
}
function reloadMarks(id) { // 三段音效时机取自关键帧（拔匣/进匣/上膛）
  const kf = RELOAD_KEY[id] || RELOAD_KEY.ak47;
  return [kf[1][0], kf[3][0], kf[4][0]];
}
const BUY = [
  { key: '1', id: 'deagle', slot: 'secondary', label: '沙漠之鹰',   price: 700 },
  { key: '2', id: 'ak47',   slot: 'primary',   label: 'AK-47',     price: 2700 },
  { key: '3', id: 'm4a1',   slot: 'primary',   label: 'M4A4',      price: 3100 },
  { key: '4', id: 'awp',    slot: 'primary',   label: 'AWP',       price: 4750 },
  { key: '5', armor: true,                   label: '防弹衣+头盔', price: 1000 },
  { key: '6', sell: true,                    label: '卖出主武器（返还半价）', price: 0 },
  { key: '7', nade: 'he',                    label: '高爆手雷（最多1）',  price: 300 },
  { key: '8', nade: 'flash',                 label: '闪光弹（最多2）',   price: 200 },
];
function makeWeapon(id) {
  const d = WEAPONS[id];
  return { id, def: d, mag: d.mag, reserve: d.reserve, _seed: Math.random() * 10 };
}

/* ---------------- 玩家 ---------------- */
const player = {
  pos: PLAYER_SPAWN.clone(), vel: new THREE.Vector3(),
  yaw: 0, pitch: 0,
  hp: 100, armor: 0, money: 800, kills: 0,
  alive: true, grounded: true, crouch: false, walk: false,
  slots: { primary: null, secondary: makeWeapon('usp'), knife: makeWeapon('knife') },
  cur: 'secondary', lastSlot: 'secondary',
  nades: { he: 0, flash: 0 }, nadeType: 'he',
  lastShotT: -9, consec: 0, reloadEnd: 0, switchEnd: 0, deadAt: 0, fireInacc: 0,
  dmgDealt: 0, roundKillBase: 0,
  wasGrounded: true, fallSpeed: 0,
};
const curWeapon = () => player.cur === 'nade'
  ? { id: player.nadeType, def: WEAPONS[player.nadeType], _seed: 0 }
  : player.slots[player.cur];
const eyeH = () => (player.crouch ? 1.15 : 1.62);
const playerHeight = () => (player.crouch ? 1.35 : 1.8);
function addMoney(n) {
  player.money = clamp(player.money + n, 0, 16000);
  if (n > 0) { // 金钱飘字
    const mf = $('moneyfloat');
    mf.textContent = '+$' + n;
    mf.classList.remove('go');
    void mf.offsetWidth;
    mf.classList.add('go');
  }
}

/* ---------------- 全局状态 ---------------- */
let locked = false, playing = false, buyOpen = false, buyMode = false;
// 默认标准锁定模式（视角可无限旋转）；按 M 切换"鼠标可见模式"并记住选择
let softAim = localStorage.getItem('csgo_aimmode') === 'soft';
let lastMX = null, lastMY = null, lastEdgeHint = 0;
let mouseHeld = false, triggerEdge = false, aiming = false, aimT = 0, awpStage = 0;
let vmKick = 0, bobPhase = 0, muzzleFlashT = 0, gapCur = 6, gapVel = 0, swayVX = 0;
let sens = 0.0022;
let tscale = 1, gravityV = 22, botsFrozen = false, baseFov = 75; // 控制台可调参数
let conOpen = false, conHist = [], conIdx = 0;
const punch = { x: 0, vx: 0, y: 0, vy: 0 }; // 视角弹簧（后坐/受击/落地）
let vmRecoil = 0, vmRecoilV = 0;             // 武器后坐弹簧
let camRoll = 0, bobStep = 0, fovKick = 0, heartT = 0;
let trauma = 0, landDip = 0, landDipV = 0;   // 创伤抖动 / 落地下沉弹簧
let yawVelS = 0, lastYaw = 0, turnLag = 0;   // 转身惯性
let roundNo = 1, ctScore = 0, tScore = 0;
let roundState = 'menu', stateT = 0, lastWon = true;
let roundStartT = 0, tCountMax = 0, lastTickSec = -1; // 回合计时
let scopeHideUntil = 0, inspectT = -9;
