/* CS:GO Web —— 准星/HUD/购买菜单 */
'use strict';

/* ---------------- 准星系统（Canvas，间隙=散布锥屏幕投影） ---------------- */
const XHAIR_PRESETS = [
  { name: '经典绿', color: '#3dff5e', len: 7, thick: 2, outline: 1.5, dot: false },
  { name: '青点',   color: '#3de8ff', len: 5, thick: 2, outline: 1.5, dot: true },
  { name: '粗黄',   color: '#ffd34d', len: 9, thick: 3, outline: 2, dot: false },
];
const xh = { preset: 0, hitT: -9, hitHead: false, killT: -9, flashT: -9 };
let xhCtx = null, xhW = 0, xhH = 0;
function sizeXhair() {
  const c = $('xhair');
  if (!c) return;
  const dpr = Math.min(devicePixelRatio, 2);
  xhW = innerWidth; xhH = innerHeight;
  c.width = xhW * dpr; c.height = xhH * dpr;
  c.style.width = xhW + 'px'; c.style.height = xhH + 'px';
  xhCtx = c.getContext('2d');
  xhCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
function drawMark(x, cx, cy, r, color, alpha, bold) {
  x.save();
  x.globalAlpha = alpha;
  x.strokeStyle = color;
  x.lineWidth = bold ? 3 : 2;
  const d = r * Math.SQRT1_2;
  x.beginPath();
  x.moveTo(cx - d, cy - d); x.lineTo(cx - d / 2, cy - d / 2);
  x.moveTo(cx + d, cy - d); x.lineTo(cx + d / 2, cy - d / 2);
  x.moveTo(cx - d, cy + d); x.lineTo(cx - d / 2, cy + d / 2);
  x.moveTo(cx + d, cy + d); x.lineTo(cx + d / 2, cy + d / 2);
  x.stroke();
  x.restore();
}
function drawCrosshair(t) {
  if (!xhCtx) return;
  const x = xhCtx, cx = xhW / 2, cy = xhH / 2;
  x.clearRect(0, 0, xhW, xhH);
  const def = curWeapon().def;
  if (aiming && def.scope && player.alive) return; // 开镜不画
  const p = XHAIR_PRESETS[xh.preset];
  const g = gapCur, L = p.len, T = p.thick, O = p.outline;
  const flashAge = t - xh.flashT;
  const fl = (flashAge >= 0 && flashAge < 0.09) ? 1 - flashAge / 0.09 : 0;
  const rects = [
    [cx - T / 2, cy - g - L, T, L],
    [cx - T / 2, cy + g, T, L],
    [cx - g - L, cy - T / 2, L, T],
    [cx + g, cy - T / 2, L, T],
  ];
  if (p.dot) rects.push([cx - T / 2, cy - T / 2, T, T]);
  for (const [px, py, rw, rh] of rects) {
    if (O > 0) { x.fillStyle = 'rgba(0,0,0,.85)'; x.fillRect(px - O, py - O, rw + O * 2, rh + O * 2); }
    x.fillStyle = p.color; x.fillRect(px, py, rw, rh);
    if (fl > 0) { x.fillStyle = `rgba(255,255,255,${(fl * 0.85).toFixed(3)})`; x.fillRect(px, py, rw, rh); }
  }
  // 命中标记（对角刻痕扩散淡出）与击杀标记（红色 X）
  const hitAge = t - xh.hitT;
  if (hitAge >= 0 && hitAge < 0.22) {
    const k = 1 - hitAge / 0.22;
    drawMark(x, cx, cy, 8 + (1 - k) * 7, xh.hitHead ? '#ff5252' : '#ffffff', k, false);
  }
  const killAge = t - xh.killT;
  if (killAge >= 0 && killAge < 0.5) {
    const k = 1 - killAge / 0.5;
    drawMark(x, cx, cy, 11 + (1 - k) * 15, '#ff3b30', k, true);
  }
}

/* ---------------- HUD / 界面 ---------------- */
function feed(html, hs) {
  const d = document.createElement('div');
  d.className = 'fentry' + (hs ? ' hs' : '');
  d.innerHTML = html;
  const f = $('feed');
  f.prepend(d);
  while (f.children.length > 5) f.removeChild(f.lastChild);
  setTimeout(() => { d.classList.add('out'); setTimeout(() => d.remove(), 350); }, 3800);
}
let toastTimer = 0;
function toast(msg) {
  const el = $('toast');
  el.textContent = msg;
  el.style.opacity = 1;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.style.opacity = 0; }, 1600);
}
function showBanner(title, sub) {
  $('banner').innerHTML = `<h2>${title}</h2>${sub ? `<p>${sub}</p>` : ''}`;
  $('banner').style.display = 'block';
}
function hideBanner() { $('banner').style.display = 'none'; }
const setTxt = (id, s) => { const el = $(id); if (el._t !== s) { el._t = s; el.textContent = s; } };
function updateHUD() {
  // 血/甲分段条（CS2 式动画填充）
  const hpPct = Math.max(0, player.hp) ;
  const hpEl = $('hpfill');
  hpEl.style.width = hpPct + '%';
  hpEl.className = 'statfill' + (hpPct < 30 ? ' low' : hpPct < 62 ? ' mid' : '');
  setTxt('hpNum', String(Math.ceil(Math.max(0, player.hp))));
  $('armorfill').style.width = Math.max(0, player.armor) + '%';
  setTxt('armorNum', String(Math.ceil(player.armor)));
  setTxt('money', '$ ' + player.money);
  const w = curWeapon();
  setTxt('wname', w.def.name + (player.reloadEnd ? ' · 换弹中…' : ''));
  const wc = $('wicon');
  if (wc._t !== w.id) { wc._t = w.id; wc.src = ICONS[w.id] || ''; }
  if (w.def.nade) {
    setTxt('ammoMag', String(player.nades[w.def.nade]));
    setTxt('ammoRes', '');
  } else if (w.def.melee) {
    setTxt('ammoMag', '—');
    setTxt('ammoRes', '');
  } else {
    setTxt('ammoMag', String(w.mag));
    setTxt('ammoRes', '/ ' + (w.reserve === Infinity ? '∞' : w.reserve));
  }
  // 武器栏（5 槽位 + 剪影图标）
  const curKey = player.cur === 'nade' ? (player.nadeType === 'he' ? '4' : '5')
    : player.cur === 'primary' ? '1' : player.cur === 'knife' ? '3' : '2';
  const wb = [
    ['1', 'ak47-slot', player.slots.primary, ''],
    ['2', 'usp-slot', player.slots.secondary, ''],
    ['3', 'knife', null, ''],
    ['4', 'he', null, String(player.nades.he)],
    ['5', 'flash', null, String(player.nades.flash)],
  ].map(([k, ic, slot, a]) => {
    const iconId = k === '1' ? (player.slots.primary ? player.slots.primary.id : null)
      : k === '2' ? player.slots.secondary.id : ic;
    const name = k === '1' ? (player.slots.primary ? player.slots.primary.def.name : '—')
      : k === '2' ? player.slots.secondary.def.name
      : k === '3' ? '军刀' : k === '4' ? '高爆' : '闪光';
    const ammo = k === '1' ? (player.slots.primary ? String(player.slots.primary.mag) : '')
      : k === '2' ? String(player.slots.secondary.mag) : a;
    return `<div class="wslot${k === curKey ? ' on' : ''}"><span class="wk">${k}</span>${iconId ? iconImg(iconId) : ''}<span class="wn">${name}</span>${ammo !== '' ? `<span class="wa">${ammo}</span>` : ''}</div>`;
  }).join('');
  const wbEl = $('wbar');
  if (wbEl._t !== wb) { wbEl._t = wb; wbEl.innerHTML = wb; }
  // 顶部比分条 + 存活点阵
  setTxt('ctScore2', String(ctScore));
  setTxt('tScore2', String(tScore));
  const ctAlive = livingCTs().length + (player.alive ? 1 : 0);
  const tAlive = livingTs().length;
  const ctMax = Math.max(ctAlive, tCountMax || 0);
  const dots = (n, total, cls) => {
    let s = '';
    for (let i = 0; i < Math.max(total, n); i++) s += `<span class="tb-dot${i < n ? ' on ' + cls : ''}"></span>`;
    return s;
  };
  const cd = dots(ctAlive, tCountMax, 'ct'), td = dots(tAlive, tCountMax, 't');
  if ($('ctDots')._t !== cd) { $('ctDots')._t = cd; $('ctDots').innerHTML = cd; }
  if ($('tDots')._t !== td) { $('tDots')._t = td; $('tDots').innerHTML = td; }
  // 低血量：红晕脉冲 + 心跳声
  const lowOn = player.alive && player.hp < 35;
  const lowEl = $('lowhp');
  lowEl.style.opacity = lowOn ? 0.45 + Math.sin(now() * 5) * 0.25 : 0;
  if (lowOn && now() > heartT) {
    heartT = now() + 0.9;
    tone({ freq: 55, end: 38, dur: 0.12, vol: 0.28, type: 'sine' });
    tone({ freq: 50, end: 36, dur: 0.1, vol: 0.2, type: 'sine', delay: 0.16 });
  }
}

/* ---------------- 购买 ---------------- */
function renderBuy() {
  const it = (i) => {
    const b = BUY[i];
    const ic = b.id || (b.nade === 'he' ? 'he' : b.nade === 'flash' ? 'flash' : '');
    return `<div class="bitem" data-i="${i}">${ic ? iconImg(ic) : ''}<span>${b.key}. ${b.label}</span><span class="p">${b.sell ? '' : '$' + b.price}</span></div>`;
  };
  let html = '<div class="btitle">购买装备（数字键或点击）</div>';
  html += '<div class="bcat">手枪</div>' + it(0);
  html += '<div class="bcat">主武器</div>' + it(1) + it(2) + it(3);
  html += '<div class="bcat">装备</div>' + it(4) + it(6) + it(7);
  html += '<div class="bcat">其他</div>' + it(5);
  html += `<div class="bclose" data-i="-1">关闭 [B]</div>`;
  html += `<div class="btitle" style="margin-top:10px">余额</div><div class="bitem"><span></span><span class="p">$${player.money}</span></div>`;
  $('buy').innerHTML = html;
}
function openBuy() {
  buyOpen = true; buyMode = true;
  renderBuy();
  $('buy').style.display = 'block';
  if (locked) document.exitPointerLock(); // 释放鼠标以便点击菜单
}
function closeBuy() {
  buyOpen = false; buyMode = false;
  $('buy').style.display = 'none';
  if (!locked && playing && player.alive) requestLock();
}
$('buy').addEventListener('click', e => {
  const item = e.target.closest('[data-i]');
  if (!item) return;
  const i = +item.dataset.i;
  if (i < 0) { closeBuy(); return; }
  buyItem(BUY[i]);
});
function buyItem(it) {
  if (!player.alive) return toast('阵亡后无法购买');
  if (it.nade) {
    const max = it.nade === 'he' ? 1 : 2;
    if (player.nades[it.nade] >= max) return toast('已达到携带上限');
    if (player.money < it.price) { toast('资金不足'); renderBuy(); return; }
    player.money -= it.price;
    player.nades[it.nade]++;
    toast('已购买 ' + (it.nade === 'he' ? '高爆手雷' : '闪光弹'));
    renderBuy();
    return;
  }
  if (it.sell) {    const pw = player.slots.primary;
    if (!pw) { toast('没有主武器可卖'); renderBuy(); return; }
    const refund = Math.floor(pw.def.price / 2);
    addMoney(refund);
    player.slots.primary = null;
    if (player.cur === 'primary') { player.cur = 'secondary'; rebuildVM(); }
    toast(`卖出 ${pw.def.name} +$${refund}`);
    renderBuy();
    return;
  }
  if (player.money < it.price) { toast('资金不足'); renderBuy(); return; }
  if (it.armor) {
    player.money -= it.price;
    player.armor = 100;
    toast('已购买 防弹衣+头盔');
  } else {
    player.money -= it.price;
    const w = makeWeapon(it.id);
    player.slots[it.slot] = w;
    player.cur = it.slot;
    player.switchEnd = now() + 0.35;
    aiming = false; awpStage = 0;
    rebuildVM();
    toast('已购买 ' + w.def.name);
  }
  renderBuy();
}
