/* CS:GO Web —— 回合流程/MVP */
'use strict';

/* ---------------- 回合流程 ---------------- */
function startRound(n) {
  roundNo = n;
  $('dead').textContent = '你已阵亡';
  $('dead').style.display = 'none';
  $('deadreport').style.display = 'none';
  player.dmgDealt = 0;
  player.roundKillBase = player.kills;
  for (const b of bots) b.kills = 0;
  tCountMax = Math.min(4 + Math.floor((n - 1) / 2), 7);
  lastTickSec = -1;
  setTxt('rphase', '购买阶段');
  clearGroundGuns();
  clearDecals();
  for (const s of shells) scene.remove(s.m);
  shells.length = 0;
  for (const b of bots) scene.remove(b.group);
  bots.length = 0; botMeshes = [];
  const tCount = Math.min(4 + Math.floor((n - 1) / 2), 7);
  const ctCount = tCount - 1; // 玩家 + 队友，与敌人兵力对等
  const tsp = BOT_SPAWNS.slice().sort(() => Math.random() - 0.5);
  const csp = CT_SPAWNS.slice().sort(() => Math.random() - 0.5);
  const t = now();
  roundStartT = t;
  for (let i = 0; i < tCount; i++) spawnBot(tsp[i % tsp.length], t, 'T');
  for (let i = 0; i < ctCount; i++) spawnBot(csp[i % csp.length], t, 'CT');
  player.pos.copy(PLAYER_SPAWN);
  player.vel.set(0, 0, 0);
  player.yaw = 0; player.pitch = 0;
  player.hp = 100; player.alive = true;
  if (!lastWon && n > 1) {
    player.slots.primary = null;
    player.slots.secondary = makeWeapon('usp');
    player.cur = 'secondary';
    player.armor = 0;
    player.nades = { he: 0, flash: 0 };
    toast('阵亡失去全部装备');
  }
  restoreWalls();
  rebuildVM();
  roundState = 'grace';
  stateT = t + 2;
  showBanner(`第 ${n} 回合`, `敌人 ${tCount} · 队友 ${ctCount}`);
  if (buyOpen) renderBuy();
}
function endRound(winner) {
  if (roundState !== 'live' && roundState !== 'grace') return;
  roundState = 'end';
  stateT = now() + 3;
  setTxt('rphase', '回合结束');
  const teamName = winner === 'ct' ? '反恐精英' : '恐怖分子';
  if (winner === 'ct') {
    ctScore++; lastWon = true; addMoney(3250);
    showBanner(teamName + '获胜', '回合奖励 +$3250');
  } else {
    tScore++; lastWon = false; addMoney(1400);
    showBanner(teamName + '获胜', '安慰奖 +$1400');
  }
  // 回合 MVP
  let mvpName = '你', mvpKills = player.kills - player.roundKillBase;
  for (const b of bots) {
    if ((b.kills || 0) > mvpKills) { mvpKills = b.kills || 0; mvpName = b.name; }
  }
  const mvpEl = $('mvp');
  mvpEl.innerHTML = `<div class="mvp-star">★ MVP ★</div><div class="mvp-name">${mvpName}</div><div class="mvp-sub">${mvpKills} 击杀 · ${teamName}</div>`;
  mvpEl.style.display = 'block';
  mvpEl.style.animation = 'none'; void mvpEl.offsetWidth; mvpEl.style.animation = '';
  clearTimeout(mvpEl._t);
  mvpEl._t = setTimeout(() => { mvpEl.style.display = 'none'; }, 2900);
  tone({ freq: winner === 'ct' ? 660 : 330, end: winner === 'ct' ? 990 : 220, dur: 0.4, vol: 0.2, type: 'triangle' });
}
