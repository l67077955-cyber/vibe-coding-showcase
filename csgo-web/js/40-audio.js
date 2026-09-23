/* CS:GO Web —— WebAudio 合成音效 */
'use strict';

/* ---------------- 音效系统（WebAudio 合成，立体声定位） ---------------- */
let AC = null, masterGain = null;
function audio() {
  if (!AC) {
    const C = window.AudioContext || window.webkitAudioContext;
    if (C) {
      AC = new C();
      masterGain = AC.createGain();
      masterGain.gain.value = 0.9;
      masterGain.connect(AC.destination);
      startAmbient();
    }
  }
  if (AC && AC.state === 'suspended') AC.resume();
  return AC;
}
// 通用噪声爆发（枪声/脚步/机械声）
function burst(o) {
  const ctx = audio(); if (!ctx) return;
  const { dur = 0.2, freq = 1500, q = 0.8, vol = 0.5, pan = 0, type = 'lowpass', decay = 2, delay = 0 } = o;
  const t0 = ctx.currentTime + delay;
  const len = Math.max(1, Math.floor(ctx.sampleRate * dur));
  const buf = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, decay);
  const src = ctx.createBufferSource(); src.buffer = buf;
  const f = ctx.createBiquadFilter(); f.type = type; f.frequency.value = freq; f.Q.value = q;
  const g = ctx.createGain();
  g.gain.setValueAtTime(Math.max(vol, 0.001), t0);
  g.gain.exponentialRampToValueAtTime(0.001, t0 + dur);
  if (ctx.createStereoPanner) {
    const p = ctx.createStereoPanner();
    p.pan.value = clamp(pan, -1, 1);
    src.connect(f).connect(g).connect(p).connect(masterGain);
  } else src.connect(f).connect(g).connect(masterGain);
  src.start(t0); src.stop(t0 + dur + 0.05);
}
function tone(o) {
  const ctx = audio(); if (!ctx) return;
  const { freq = 440, end = 440, dur = 0.1, vol = 0.2, type = 'sine', pan = 0, delay = 0 } = o;
  const t0 = ctx.currentTime + delay;
  const osc = ctx.createOscillator(); osc.type = type;
  osc.frequency.setValueAtTime(freq, t0);
  osc.frequency.exponentialRampToValueAtTime(Math.max(end, 1), t0 + dur);
  const g = ctx.createGain();
  g.gain.setValueAtTime(Math.max(vol, 0.001), t0);
  g.gain.exponentialRampToValueAtTime(0.001, t0 + dur);
  if (ctx.createStereoPanner) {
    const p = ctx.createStereoPanner();
    p.pan.value = clamp(pan, -1, 1);
    osc.connect(g).connect(p).connect(masterGain);
  } else osc.connect(g).connect(masterGain);
  osc.start(t0); osc.stop(t0 + dur + 0.05);
}
// 世界坐标 → 声像/距离
function panFor(pos) {
  const dx = pos.x - camera.position.x, dz = pos.z - camera.position.z;
  const dist = Math.hypot(dx, dz, (pos.y || 0) - camera.position.y);
  const rx = Math.cos(player.yaw), rz = -Math.sin(player.yaw); // 相机右向量
  const pan = dist > 0.01 ? (dx * rx + dz * rz) / dist : 0;
  return { pan: pan * 0.8, dist };
}
const SHOT_CFG = {
  pistol: { freq: 2600, dur: 0.16, thump: 140, vol: 0.5 },
  deagle: { freq: 1300, dur: 0.26, thump: 100, vol: 0.7 },
  ak:     { freq: 1700, dur: 0.18, thump: 120, vol: 0.6 },
  m4:     { freq: 2100, dur: 0.16, thump: 125, vol: 0.55 },
  awp:    { freq: 800,  dur: 0.45, thump: 75,  vol: 0.85 },
};
function shotSound(type, volOrPos, distIn) {
  const c = SHOT_CFG[type] || SHOT_CFG.ak;
  let vol = 1, pan = 0, dist = distIn || 0;
  if (volOrPos && volOrPos.isVector3) { const pf = panFor(volOrPos); pan = pf.pan; dist = pf.dist; }
  else vol = volOrPos || 1;
  const att = vol / (1 + dist * 0.07);
  burst({ dur: c.dur, freq: c.freq * Math.max(0.35, 1 - dist * 0.012), vol: att * c.vol, pan });   // 枪体
  tone({ freq: c.thump, end: 40, dur: c.dur * 0.7, vol: att * 0.4, type: 'triangle', pan });        // 低频砰
  if (dist > 8) burst({ dur: 0.5, freq: 500, vol: att * 0.25, pan, delay: 0.02, decay: 1 });       // 远距尾音
}
function footstep(vol, pos) {
  let pan = 0, dist = 0;
  if (pos) { const pf = panFor(pos); pan = pf.pan; dist = pf.dist; }
  const v = (vol || 0.3) / (1 + dist * 0.25);
  if (v < 0.012) return;
  // 分材质脚步：石板街(脆亮) / 硬质台面(闷实) / 沙地(松散)
  let surf = 'sand';
  if (pos) {
    if (Math.abs(pos.x) < 9.4 && pos.z > 2.7 && pos.z < 29.4) surf = 'stone';
    else if (groundHeightAt(pos.x, pos.z) > 0.25) surf = 'plat';
  } else if (Math.abs(player.pos.x) < 9.4 && player.pos.z > 2.7 && player.pos.z < 29.4) surf = 'stone';
  else if (groundHeightAt(player.pos.x, player.pos.z) > 0.25) surf = 'plat';
  const cfg = {
    stone: { freq: 1500, q: 1.6, dur: 0.06, decay: 3.5 },
    plat:  { freq: 620,  q: 1.1, dur: 0.09, decay: 2.5 },
    sand:  { freq: 760,  q: 0.9, dur: 0.08, decay: 2.8 },
  }[surf];
  burst({ dur: cfg.dur, freq: cfg.freq + Math.random() * 260, q: cfg.q, vol: v * 0.4, pan, type: 'bandpass', decay: cfg.decay });
  if (surf === 'stone') burst({ dur: 0.03, freq: 3400, q: 4, vol: v * 0.1, pan, type: 'bandpass' }); // 硬地轻响
}
function whizSound(pan) {
  burst({ dur: 0.16, freq: 3200, q: 6, vol: 0.16, type: 'bandpass', decay: 1.5, pan: pan || 0 });
}
function reloadSounds(dur, marks) {
  const m = marks || [0.15, 0.55, 0.78];
  burst({ dur: 0.04, freq: 2500, q: 3, vol: 0.25, type: 'bandpass', delay: dur * m[0] });   // 拔匣
  burst({ dur: 0.05, freq: 1800, q: 3, vol: 0.3, type: 'bandpass', delay: dur * m[1] });    // 进匣
  burst({ dur: 0.06, freq: 3200, q: 2, vol: 0.35, type: 'bandpass', delay: dur * m[2] });   // 上膛
}
function drawSound() {
  burst({ dur: 0.05, freq: 2000, q: 2.5, vol: 0.22, type: 'bandpass' });
  burst({ dur: 0.05, freq: 3000, q: 2.5, vol: 0.18, type: 'bandpass', delay: 0.12 });
}
function landSound(hard) {
  burst({ dur: hard ? 0.16 : 0.09, freq: hard ? 300 : 500, vol: hard ? 0.4 : 0.22, decay: 2 });
}
const hitSound = head => tone({ freq: head ? 1550 : 1100, dur: 0.05, vol: 0.22, type: 'square' });
function armorSound() { tone({ freq: 700, end: 500, dur: 0.06, vol: 0.2, type: 'square' }); }
function killSound() {
  tone({ freq: 880, dur: 0.07, vol: 0.22, type: 'square' });
  tone({ freq: 1320, dur: 0.1, vol: 0.22, type: 'square', delay: 0.08 });
}
function startAmbient() { // 环境风声
  const ctx = AC;
  const len = ctx.sampleRate * 2;
  const buf = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
  const src = ctx.createBufferSource(); src.buffer = buf; src.loop = true;
  const f = ctx.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = 400; f.Q.value = 0.4;
  const g = ctx.createGain(); g.gain.value = 0.035;
  src.connect(f).connect(g).connect(masterGain);
  src.start();
}
