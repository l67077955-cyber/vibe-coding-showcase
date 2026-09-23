/* CS:GO Web —— 武器剪影图标 + 初始化 */
'use strict';

/* ---------------- 程序化武器剪影图标（CS2 风格 UI） ---------------- */
const ICON_RECTS = {
  usp:    [[8,16,52,10],[10,26,28,5],[60,17,30,8],[20,26,11,16],[14,26,4,4],[64,20,3,2]],
  deagle: [[6,12,62,12],[10,9,48,3],[68,14,22,7],[18,24,11,18],[8,14,4,4],[74,17,3,2]],
  ak47:   [[68,16,26,4],[86,10,3,9],[52,12,18,4],[24,10,34,12],[28,22,10,8],[31,30,9,8],[2,13,16,8],[0,10,7,15],[40,22,8,10],[62,13,4,3]],
  m4a1:   [[66,16,26,4],[44,13,22,10],[20,10,26,12],[22,5,20,4],[2,13,10,8],[12,15,8,4],[28,22,9,12],[60,17,4,2]],
  awp:    [[58,16,38,4],[26,4,26,7],[30,11,4,3],[48,11,4,3],[14,12,46,10],[0,13,14,11],[30,22,7,10],[20,22,8,7],[92,14,4,4]],
  knife:  [[34,15,52,5],[78,12,10,3],[12,12,22,9],[6,14,6,5]],
  he:     [[],],
  flash:  [[],],
};
const ICONS = {};
(function buildIcons() {
  for (const id of ['usp', 'deagle', 'ak47', 'm4a1', 'awp', 'knife', 'he', 'flash']) {
    const c = document.createElement('canvas');
    c.width = 100; c.height = 40;
    const x = c.getContext('2d');
    x.fillStyle = '#e8e8e8';
    if (id === 'he') {
      x.beginPath(); x.arc(46, 22, 12, 0, 7); x.fill();
      x.fillRect(44, 6, 4, 6);
      x.beginPath(); x.arc(56, 9, 5, 0, 7); x.lineWidth = 3; x.strokeStyle = '#e8e8e8'; x.stroke();
    } else if (id === 'flash') {
      x.fillRect(38, 8, 16, 24);
      x.fillRect(42, 3, 8, 5);
      x.beginPath(); x.arc(60, 12, 6, 0, 7); x.lineWidth = 3; x.strokeStyle = '#e8e8e8'; x.stroke();
    } else {
      for (const [rx, ry, rw, rh] of ICON_RECTS[id] || []) x.fillRect(rx, ry, rw, rh);
      if (id === 'knife') { // 刀尖
        x.beginPath(); x.moveTo(86, 15); x.lineTo(96, 12); x.lineTo(86, 20); x.fill();
      }
    }
    ICONS[id] = c.toDataURL();
  }
})();
function iconImg(id, cls) {
  return ICONS[id] ? `<img class="${cls || ''}" src="${ICONS[id]}" alt="">` : '';
}
function cprint(s, cls) {
  const log = $('clog');
  const d = document.createElement('div');
  d.className = 'cline' + (cls ? ' ' + cls : '');
  d.textContent = s;
  log.appendChild(d);
  while (log.children.length > 80) log.removeChild(log.firstChild);
  log.scrollTop = log.scrollHeight;
}
function refillAll() {
  for (const k of ['primary', 'secondary']) {
    const w = player.slots[k];
    if (w) { w.mag = w.def.mag; w.reserve = w.def.reserve; }
  }
}
function toggleConsole(force) {
  conOpen = force !== undefined ? force : !conOpen;
  $('console').style.display = conOpen ? 'flex' : 'none';
  if (conOpen) {
    if (locked) document.exitPointerLock();
    setTimeout(() => $('cinput').focus(), 0);
    if (!toggleConsole._hello) { toggleConsole._hello = true; cprint('CS:GO Web 控制台 —— 输入 help 查看命令', 'cmd'); }
  } else if (!locked && playing && player.alive && !softAim && !buyOpen) {
    requestLock();
  }
}
function exec(raw) {
  const line = (raw || '').trim();
  if (!line) return;
  cprint('] ' + line, 'cmd');
  const a = line.split(/\s+/);
  const c = a[0].toLowerCase();
  const n = parseFloat(a[1]);
  const onoff = () => a[1] === undefined ? undefined : (parseFloat(a[1]) > 0 || a[1] === 'on' || a[1] === 'true');
  switch (c) {
    case 'help':
      cprint('god / noclip / impulse 101 / give <usp|deagle|ak47|m4a1|awp> / ammo');
      cprint('hp n / armor n / money n / kill / bot_kill / bot_kick / bot_add <t|ct> / bots_stop');
      cprint('timescale x(0.2-4) / fov n(60-120) / sens n(如 2.2) / gravity n / restart / clear');
      break;
    case 'god': { const v = onoff(); player.god = v === undefined ? !player.god : v; cprint('god = ' + !!player.god); break; }
    case 'noclip': { const v = onoff(); player.noclip = v === undefined ? !player.noclip : v; cprint('noclip = ' + !!player.noclip); break; }
    case 'impulse':
      if (a[1] === '101') { addMoney(16000); player.armor = 100; refillAll(); cprint('金钱+装备已补给'); }
      else cprint('未知 impulse', 'err');
      break;
    case 'give': {
      const id = (a[1] || '').toLowerCase();
      if (!WEAPONS[id]) { cprint('未知武器: ' + (a[1] || '') + '（usp/deagle/ak47/m4a1/awp）', 'err'); break; }
      const slot = (id === 'usp' || id === 'deagle') ? 'secondary' : 'primary';
      player.slots[slot] = makeWeapon(id);
      player.cur = slot;
      player.switchEnd = now() + 0.35;
      aiming = false; awpStage = 0;
      rebuildVM();
      drawSound();
      cprint('已给予 ' + WEAPONS[id].name);
      break;
    }
    case 'ammo': refillAll(); cprint('弹药已补满'); break;
    case 'hp': if (n >= 0 && n <= 100) { player.hp = n; cprint('hp = ' + n); } else cprint('范围 0-100', 'err'); break;
    case 'armor': if (n >= 0 && n <= 100) { player.armor = n; cprint('armor = ' + n); } else cprint('范围 0-100', 'err'); break;
    case 'money': if (n >= 0) { player.money = Math.min(Math.round(n), 16000); cprint('money = ' + player.money); } break;
    case 'kill': if (player.alive) playerDie(null); break;
    case 'bot_kill': {
      let k = 0;
      for (const b of bots.slice()) if (!b.dead) { killBot(b, false, null, null); k++; }
      cprint('击杀 ' + k + ' 个 bot');
      break;
    }
    case 'bot_kick':
      for (const b of bots) scene.remove(b.group);
      bots.length = 0; botMeshes = [];
      cprint('已清空所有 bot');
      break;
    case 'bot_add': {
      const team = (a[1] || 't').toUpperCase() === 'CT' ? 'CT' : 'T';
      const arr = team === 'T' ? BOT_SPAWNS : CT_SPAWNS;
      spawnBot(arr[Math.floor(Math.random() * arr.length)], now(), team);
      cprint('已添加 ' + team + ' bot');
      break;
    }
    case 'bots_stop': { const v = onoff(); botsFrozen = v === undefined ? !botsFrozen : v; cprint('bots_stop = ' + botsFrozen); break; }
    case 'timescale': if (n > 0 && n <= 4) { tscale = n; cprint('timescale = ' + n); } else cprint('范围 0.2-4', 'err'); break;
    case 'fov': if (n >= 60 && n <= 120) { baseFov = n; cprint('fov = ' + n); } else cprint('范围 60-120', 'err'); break;
    case 'sens': if (n > 0 && n <= 10) { sens = n / 1000; cprint('sens = ' + n); } else cprint('范围 0.5-10', 'err'); break;
    case 'gravity': if (n >= 5 && n <= 60) { gravityV = n; cprint('gravity = ' + n); } else cprint('范围 5-60', 'err'); break;
    case 'restart':
      ctScore = 0; tScore = 0; player.kills = 0;
      startRound(1);
      cprint('比赛已重置');
      break;
    case 'clear': $('clog').innerHTML = ''; break;
    default: cprint('未知命令: ' + c + '（输入 help 查看）', 'err');
  }
}
$('cinput').addEventListener('keydown', e => {
  e.stopPropagation();
  if (e.key === 'Enter') {
    const v = $('cinput').value;
    $('cinput').value = '';
    if (v.trim()) { conHist.push(v); conIdx = conHist.length; }
    exec(v);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (conIdx > 0) { conIdx--; $('cinput').value = conHist[conIdx] || ''; }
  } else if (e.key === 'ArrowDown') {
    e.preventDefault();
    if (conIdx < conHist.length) { conIdx++; $('cinput').value = conHist[conIdx] || ''; }
  } else if (e.key === 'Escape' || e.code === 'Backquote') {
    toggleConsole(false);
  }
});

/* ---------------- 主循环 ---------------- */
rebuildVM();
renderBuy();
sizeXhair();
updateHUD();

let last = now();
function loop() {
  requestAnimationFrame(loop);
  const t = now();
  let dt = Math.min(t - last, 0.05);
  dt *= tscale; // 控制台 timescale
  last = t;
  if (playing) {
    if (roundState === 'grace' && t >= stateT) { roundState = 'live'; hideBanner(); setTxt('rphase', '战斗'); }
    if (roundState === 'end' && t >= stateT) startRound(roundNo + 1);
    if (!player.alive && roundState === 'live' && livingCTs().length === 0 && t >= player.deadAt + 2.5) endRound('t');
    // 回合倒计时（115s，耗尽判 CT 坚守成功）
    if (roundState === 'live') {
      const rem = Math.max(0, 115 - (t - roundStartT));
      const ss = Math.floor(rem % 60);
      const tstr = Math.floor(rem / 60) + ':' + String(ss).padStart(2, '0');
      const rtEl = $('rtime');
      if (rtEl._t !== tstr) { rtEl._t = tstr; rtEl.textContent = tstr; }
      rtEl.classList.toggle('low', rem <= 10 && rem > 0);
      if (rem <= 10 && rem > 0 && ss !== lastTickSec) { lastTickSec = ss; tone({ freq: 1300, dur: 0.04, vol: 0.1, type: 'square' }); }
      if (rem <= 0) { setTxt('rphase', '回合结束'); endRound('ct'); }
    }
    updatePlayer(dt);
    updateBots(dt, t);
    updateWeapon(dt, t);
    updateEffects(dt);
    updateShells(dt);
    updateDebris(dt);
    updateNades(dt, t);
    updateChunks(dt);
    P2.update(dt);
    updateHUD();
  }
  // 天空云漂移 + 动态灯衰减（暂停时也保持场景鲜活）
  skyMat.uniforms.uTime.value = t;
  updateDust(t);
  for (const cs2 of clothSigns) cs2.m.rotation.z = Math.sin(t * 0.8 + cs2.ph) * 0.05;
  botFlashLight.intensity *= Math.max(0, 1 - dt * 14);
  for (const L of impactLights) if (L.intensity > 0.01) L.intensity *= Math.max(0, 1 - dt * 10);
  renderer.render(scene, camera);
}
loop();
