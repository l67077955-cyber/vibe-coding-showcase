/* CS:GO Web —— 键鼠输入/指针锁定/控制台 */
'use strict';

/* ---------------- 输入 ---------------- */
document.addEventListener('keydown', e => {
  if (e.code === 'Backquote') { e.preventDefault(); toggleConsole(); return; }
  if (conOpen) return;
  keys[e.code] = true;
  if (['Space', 'Tab', 'F1'].includes(e.code)) e.preventDefault();
  if (e.code === 'F1') {
    xh.preset = (xh.preset + 1) % XHAIR_PRESETS.length;
    toast('准星样式：' + XHAIR_PRESETS[xh.preset].name);
  }
  if (!playing) return;
  if (e.code === 'KeyB' && player.alive) {
    buyOpen ? closeBuy() : openBuy();
  } else if (buyOpen && /^Digit[1-8]$/.test(e.code)) {
    buyItem(BUY[+e.code.slice(5) - 1]);
  } else if (!buyOpen) {
    if (e.code === 'Digit1') switchSlot('primary');
    else if (e.code === 'Digit2') switchSlot('secondary');
    else if (e.code === 'Digit3') switchSlot('knife');
    else if (e.code === 'Digit4') switchNade('he');
    else if (e.code === 'Digit5') switchNade('flash');
    else if (e.code === 'KeyQ') switchSlot(player.lastSlot);
    else if (e.code === 'KeyR') startReload(now());
    else if (e.code === 'KeyE') tryPickup();
    else if (e.code === 'KeyF') { // 检视武器
      if (player.alive && !player.reloadEnd && now() >= player.switchEnd) {
        inspectT = now();
        burst({ dur: 0.08, freq: 900, q: 2, vol: 0.1, type: 'bandpass' });
      }
    }
    else if (e.code === 'KeyM' && roundState !== 'menu') {
      softAim = !softAim;
      localStorage.setItem('csgo_aimmode', softAim ? 'soft' : 'lock');
      if (softAim) {
        if (locked) document.exitPointerLock();
        playing = true; lastMX = null;
        $('menu').style.display = 'none';
        toast('鼠标可见模式（光标到屏幕边缘会转不动）');
      } else {
        toast('标准指针锁定模式');
        requestLock();
      }
    }
    else if (e.code === 'KeyP') {
      if (locked) document.exitPointerLock();
      else if (playing) {
        playing = false;
        $('menu').style.display = 'flex';
        $('playBtn').textContent = '点击继续';
      }
    }
    else if (e.code === 'BracketLeft') { sens = Math.max(0.0006, sens * 0.85); toast('灵敏度 ' + (sens * 1000).toFixed(1)); }
    else if (e.code === 'BracketRight') { sens = Math.min(0.008, sens * 1.18); toast('灵敏度 ' + (sens * 1000).toFixed(1)); }
  }
});
document.addEventListener('keyup', e => { keys[e.code] = false; });
function applyLook(dx, dy) {
  // 开镜灵敏度随当前 FOV 动态匹配（变焦过程手感一致）
  const s = sens * (aiming ? camera.fov / baseFov : 1);
  player.yaw -= dx * s;
  player.pitch = clamp(player.pitch - dy * s, -1.55, 1.55);
  swayVX = swayVX * 0.5 + dx * 0.5;
  // 立即应用到相机，保证瞄准跟手（即使某帧卡顿）
  camera.rotation.y = player.yaw + punch.y;
  camera.rotation.x = player.pitch + punch.x;
}
document.addEventListener('mousemove', e => {
  if (!playing || buyOpen || !player.alive) { lastMX = null; return; }
  if (locked) {
    applyLook(e.movementX, e.movementY);
    lastMX = null;
  } else if (softAim) {
    // 鼠标可见模式：用屏幕位移增量转视角（光标到屏幕边缘会转不动）
    if (lastMX !== null) applyLook(e.clientX - lastMX, e.clientY - lastMY);
    lastMX = e.clientX; lastMY = e.clientY;
    const m = 40;
    if ((e.clientX < m || e.clientX > innerWidth - m) && now() - lastEdgeHint > 8) {
      lastEdgeHint = now();
      toast('光标到屏幕边缘转不动了 —— 按 M 切换锁定模式（无限旋转）');
    }
  }
});
document.addEventListener('mousedown', e => {
  if (conOpen) return;
  if (!locked && !softAim) return;
  if (e.button === 0) { mouseHeld = true; triggerEdge = true; }
  else if (e.button === 2 && player.alive) {
    const def = curWeapon().def;
    if (def.scope) { awpStage = (awpStage + 1) % 3; aiming = awpStage > 0; } // CS 式循环变焦：腰射→2.5×→6.8×
    else aiming = true; // 按住右键据枪（所有枪）
  }
});
document.addEventListener('mouseup', e => {
  if (e.button === 0) mouseHeld = false;
  else if (e.button === 2 && !curWeapon().def.scope) aiming = false;
});
document.addEventListener('contextmenu', e => e.preventDefault());

function startSoft() {
  softAim = true;
  playing = true;
  lastMX = null;
  document.body.classList.remove('locked');
  $('menu').style.display = 'none';
  if (roundState === 'menu') startRound(1);
}
function enableSoftAim(reason) {
  startSoft();
  toast((reason || '指针锁定不可用') + '，已切换鼠标可见模式（M 切换 / P 暂停）');
}
function requestLock() {
  const p = renderer.domElement.requestPointerLock();
  if (p && p.catch) p.catch(() => enableSoftAim('浏览器拒绝指针锁定'));
}
// 失焦/切标签页时释放鼠标，避免光标"消失"（系统级被游戏占用）
addEventListener('blur', () => { if (locked) document.exitPointerLock(); });
document.addEventListener('visibilitychange', () => {
  if (document.hidden && locked) document.exitPointerLock();
});
document.addEventListener('pointerlockerror', () => enableSoftAim('指针锁定失败'));
$('menu').addEventListener('click', () => { audio(); if (softAim) startSoft(); else requestLock(); });
renderer.domElement.addEventListener('click', () => { if (!locked && !softAim && playing && !buyOpen) requestLock(); });
document.addEventListener('pointerlockchange', () => {
  locked = document.pointerLockElement === renderer.domElement;
  document.body.classList.toggle('locked', locked); // 仅锁定时隐藏光标
  if (locked) {
    softAim = false;
    lastMX = null;
    playing = true;
    buyMode = false;
    $('menu').style.display = 'none';
    if (roundState === 'menu') startRound(1);
  } else if (!buyMode) {
    // 买菜单主动解锁时不弹暂停菜单，游戏继续
    playing = false;
    buyOpen = false;
    $('buy').style.display = 'none';
    $('menu').style.display = 'flex';
    $('playBtn').textContent = '点击继续';
  }
});
