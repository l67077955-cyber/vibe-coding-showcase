/* CS:GO Web —— 弹道/射击/近战手雷/碎片 */
'use strict';

/* ---------------- 不精确度模型（Source 式连续状态） ---------------- */
function currentInacc() {
  const def = curWeapon().def;
  const d = def.inacc;
  const spd = Math.hypot(player.vel.x, player.vel.z);
  let v = d.stand + d.move * clamp(spd / 5.4, 0, 1);
  if (!player.grounded) v += d.jump;
  if (player.crouch) v *= d.crouch;
  v += player.fireInacc;
  if (aiming) v = def.scope ? Math.min(v, 0.0008) : v * 0.65; // 据枪收紧散布，AWP 开镜近乎完美
  return v;
}

/* ---------------- 射击 ---------------- */
const rayShot = new THREE.Raycaster();
function fire(t) {
  const w = curWeapon(); const def = w.def;
  if (def.nade) { throwNade(def.nade, t); return; }
  if (def.melee) { meleeAttack(t); return; }
  w.mag--; player.lastShotT = t; player.consec++;
  player.fireInacc = Math.min(player.fireInacc + def.inacc.fire, def.inacc.fire * 6);
  const spread = currentInacc();

  // 确定性弹道表 + 每弹匣相位微差（可学习、可压枪）
  const si = Math.min(Math.max(1, Math.round(player.consec)), 30) - 1;
  const pat = (SPRAY[w.id] || SPRAY.ak47)[si];
  const patY = pat.y, patX = pat.x * (0.85 + w._seed * 0.03);

  const dir = new THREE.Vector3(); camera.getWorldDirection(dir);
  const right = new THREE.Vector3().crossVectors(dir, new THREE.Vector3(0, 1, 0)).normalize();
  const up = new THREE.Vector3().crossVectors(right, dir).normalize();
  const gs = () => (Math.random() + Math.random() - 1); // 近高斯，弹着点更集中
  dir.addScaledVector(right, patX + gs() * spread)
     .addScaledVector(up, patY + gs() * spread)
     .normalize();

  rayShot.set(camera.position, dir); rayShot.far = 150;
  const hits = rayShot.intersectObjects(staticTargets.concat(botMeshes), false);
  let end = camera.position.clone().addScaledVector(dir, 120);
  if (hits.length) {
    const h = hits[0];
    end = h.point;
    const ud = h.object.userData;
    if (ud && ud.bot && !ud.bot.dead) {
      // 按命中点高度判定分区（头>1.45 / 腿<0.85），兼容蒙皮与程序化模型
      const relY = h.point.y - (ud.bot.group.position.y || 0);
      const zone = relY > 1.45 ? 'head' : (relY < 0.85 ? 'legs' : 'body');
      const mult = zone === 'head' ? def.hs : (zone === 'legs' ? 0.75 : 1);
      hitBot(ud.bot, def.dmg * mult, zone === 'head', h.point, dir);
    } else {
      addSpark(h.point, 0xd8c193, 0.35);
      if (h.object.userData.destr) damageWall(h.object.userData.destr, def.dmg * 0.8); // 可破坏墙
      if (h.face) {
        const n = h.face.normal.clone().transformDirection(h.object.matrixWorld);
        const metal = h.object.userData.kind === 'barrel';
        addDecal(h.point, n);
        burstDebris(h.point, n, metal);
        impactFlash(h.point, metal ? 0xffdd99 : 0xffc080);
        if (metal) tone({ freq: 2400, end: 900, dur: 0.08, vol: 0.15, type: 'square', pan: panFor(h.point).pan });
      }
    }
  }
  const mzl = vmTipWorld();
  addTracer(mzl, end);
  addSmoke(mzl);
  spawnShell();
  flashLight.position.copy(mzl);
  flashLight.intensity = 2.4;
  punch.vx += def.recoil * 22;                       // 视角弹簧后坐（自动回弹）
  punch.vy += (Math.random() - 0.5) * def.recoil * 6;
  vmRecoilV += def.recoil * 90;                      // 武器后坐弹簧
  gapVel += 55 + def.inacc.fire * 5500;              // 准星弹开冲量（若即若离的来源）
  xh.flashT = t;                                     // 线体闪白
  trauma = Math.min(1, trauma + def.recoil * 6);     // 创伤抖动累积
  fovKick = Math.min(fovKick + 0.6, 1.6);
  vmKick = 1;
  muzzleFlashT = t + 0.045;
  shotSound(def.snd, 1, 0);
  if (def.scope && aiming) { // AWP 开镜射击：拉栓循环（镜片短暂落下）
    scopeHideUntil = t + 0.32;
    vmRecoilV += 2.2;
    punch.vx += 0.02;
    setTimeout(() => { if (now() - muzzleFlashT < 0.5) burst({ dur: 0.06, freq: 2400, q: 3, vol: 0.2, type: 'bandpass', delay: 0.12 }); }, 180);
  }
  if (w.mag === 0) startReload(t);
}
function startReload(t) {
  if (player.reloadEnd) return;
  const w = curWeapon();
  if (w.mag >= w.def.mag || w.reserve <= 0) return;
  player.reloadEnd = t + w.def.reload;
  aiming = false; awpStage = 0;
  reloadSounds(w.def.reload, reloadMarks(w.id));
}
function switchSlot(k) {
  if (k === 'nade') { switchNade(player.nadeType); return; }
  if (!player.slots[k] || player.cur === k || !player.alive) return;
  player.lastSlot = player.cur;
  player.cur = k;
  player.switchEnd = now() + 0.35;
  player.reloadEnd = 0;
  aiming = false; awpStage = 0;
  rebuildVM();
  drawSound();
}
function switchNade(type) {
  if (!player.alive) return;
  if (player.nades[type] <= 0) return toast(type === 'he' ? '没有高爆手雷（B 购买）' : '没有闪光弹（B 购买）');
  if (player.cur === 'nade' && player.nadeType === type) return;
  player.lastSlot = player.cur;
  player.cur = 'nade';
  player.nadeType = type;
  player.switchEnd = now() + 0.3;
  player.reloadEnd = 0;
  aiming = false; awpStage = 0;
  rebuildVM();
  drawSound();
}

/* ---------------- 军刀 / 手雷 ---------------- */
function meleeAttack(t) {
  const dir = new THREE.Vector3(); camera.getWorldDirection(dir);
  rayShot.set(camera.position, dir); rayShot.far = 2.3;
  const hits = rayShot.intersectObjects(staticTargets.concat(botMeshes), false);
  vmKick = 1;
  punch.vx += 0.4;
  burst({ dur: 0.06, freq: 1600, q: 2, vol: 0.15, type: 'bandpass' }); // 挥刀风声
  if (hits.length) {
    const h = hits[0];
    const ud = h.object.userData;
    if (ud && ud.bot && !ud.bot.dead) {
      hitBot(ud.bot, 40, false, h.point, dir);
    } else {
      addSpark(h.point, 0xd8c193, 0.3);
      if (h.face) burstDebris(h.point, h.face.normal.clone().transformDirection(h.object.matrixWorld), false);
      if (ud.destr) damageWall(ud.destr, 55);
      burst({ dur: 0.05, freq: 3200, q: 4, vol: 0.2, type: 'bandpass' }); // 砍中
    }
  }
}
const nades = [];
const nadeGeo = new THREE.SphereGeometry(0.09, 10, 8);
const nadeMatHE = new THREE.MeshStandardMaterial({ color: 0x3d4a35, roughness: 0.5, metalness: 0.3 });
const nadeMatFL = new THREE.MeshStandardMaterial({ color: 0x8b9298, roughness: 0.35, metalness: 0.7 });
const boomLight = new THREE.PointLight(0xffa050, 0, 20);
scene.add(boomLight);
const flashLightW = new THREE.PointLight(0xffffff, 0, 24);
scene.add(flashLightW);
/* ---------------- 投掷轨迹预览（蓝色透水管） ---------------- */
const nadeArcMat = new THREE.MeshBasicMaterial({ color: 0x38a0ff, transparent: true, opacity: 0.4, depthWrite: false });
const nadeArc = new THREE.Mesh(new THREE.BufferGeometry(), nadeArcMat);
nadeArc.visible = false;
nadeArc.frustumCulled = false;
scene.add(nadeArc);
const nadeArcDot = new THREE.Mesh(new THREE.SphereGeometry(0.07, 12, 10), new THREE.MeshBasicMaterial({ color: 0x38a0ff, transparent: true, opacity: 0.55, depthWrite: false }));
nadeArcDot.visible = false;
scene.add(nadeArcDot);
function updateNadeArc() {
  const show = player.alive && playing && player.cur === 'nade' && player.nades[player.nadeType] > 0;
  nadeArc.visible = nadeArcDot.visible = show;
  if (!show) return;
  // 与 throwNade 完全一致的初速：dir*16 + 上抛 3.2 + 侧偏 0.8
  const dir = new THREE.Vector3(); camera.getWorldDirection(dir);
  const rt = new THREE.Vector3(Math.cos(player.yaw), 0, -Math.sin(player.yaw));
  const vel = dir.clone().multiplyScalar(16).add(new THREE.Vector3(0, 3.2, 0)).addScaledVector(rt, 0.8);
  const p = camera.position.clone().addScaledVector(dir, 0.5);
  const pts = [p.clone()];
  const step = 1 / 30;
  for (let i = 0; i < 66; i++) { // ~2.2s，覆盖到爆点
    vel.y -= 16 * step;
    p.addScaledVector(vel, step);
    if (p.y < 0.09) { p.y = 0.09; pts.push(p.clone()); break; } // 落点
    pts.push(p.clone());
  }
  nadeArc.geometry.dispose();
  nadeArc.geometry = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), Math.min(64, pts.length * 2), 0.028, 6, false);
  nadeArcDot.position.copy(pts[pts.length - 1]);
}
function throwNade(type, t) {
  if (player.nades[type] <= 0) return;
  player.nades[type]--;
  player.lastShotT = t;
  const dir = new THREE.Vector3(); camera.getWorldDirection(dir);
  const rt = new THREE.Vector3(Math.cos(player.yaw), 0, -Math.sin(player.yaw));
  const m = new THREE.Mesh(nadeGeo, type === 'he' ? nadeMatHE : nadeMatFL);
  m.castShadow = true;
  m.position.copy(camera.position).addScaledVector(dir, 0.5);
  scene.add(m);
  nades.push({
    m, type, born: t,
    vel: dir.clone().multiplyScalar(16).add(new THREE.Vector3(0, 3.2, 0)).addScaledVector(rt, 0.8),
  });
  burst({ dur: 0.04, freq: 3000, q: 3, vol: 0.2, type: 'bandpass' }); // 拉环
  const left = player.nades[type];
  toast((type === 'he' ? '高爆手雷' : '闪光弹') + ` 剩 ${left}`);
  setTimeout(() => {
    if (player.cur === 'nade' && player.nades[type] <= 0) switchSlot(player.lastSlot === 'nade' ? 'secondary' : player.lastSlot);
  }, 400);
}
function nadeCollide(n, axis, delta) {
  if (!delta) return;
  const r = 0.09, p = n.m.position;
  p[axis] += delta;
  for (const s of solids) {
    if (p.x + r > s.min.x && p.x - r < s.max.x &&
        p.y + r > s.min.y && p.y - r < s.max.y &&
        p.z + r > s.min.z && p.z - r < s.max.z) {
      if (axis === 'x') { p.x = delta > 0 ? s.min.x - r : s.max.x + r; n.vel.x *= -0.42; }
      else if (axis === 'y') { p.y = delta > 0 ? s.min.y - r : s.max.y + r; n.vel.y *= -0.42; n.vel.x *= 0.75; n.vel.z *= 0.75; }
      else { p.z = delta > 0 ? s.min.z - r : s.max.z + r; n.vel.z *= -0.42; }
      if (Math.abs(delta) > 0.02) burst({ dur: 0.03, freq: 4200, q: 4, vol: 0.06, type: 'bandpass', pan: panFor(p).pan });
    }
  }
}
function boomSound(pos) {
  const pf = panFor(pos);
  const att = 1 / (1 + pf.dist * 0.05);
  burst({ dur: 0.6, freq: 260, vol: 0.9 * att, pan: pf.pan, decay: 1.2 });
  tone({ freq: 70, end: 24, dur: 0.5, vol: 0.7 * att, type: 'triangle', pan: pf.pan });
  burst({ dur: 0.9, freq: 700, vol: 0.25 * att, pan: pf.pan, delay: 0.05, decay: 1 });
}
function losClear(from, to) { // 两点间无墙
  const d = to.clone().sub(from);
  const len = d.length();
  rayShot.set(from, d.normalize());
  rayShot.far = len;
  const hs = rayShot.intersectObjects(rayWalls, false);
  return !(hs.length && hs[0].distance < len - 0.2);
}
function explodeHE(pos) {
  boomSound(pos);
  boomLight.position.copy(pos); boomLight.intensity = 7;
  for (let i = 0; i < 10; i++) addSpark(pos.clone().add(new THREE.Vector3(rand(-.5, .5), rand(0, .8), rand(-.5, .5))), 0xffb060, rand(0.4, 0.9));
  for (let i = 0; i < 4; i++) addSmoke(pos.clone().add(new THREE.Vector3(rand(-.6, .6), rand(0, 1), rand(-.6, .6))));
  const scorch = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: 0x14100a, transparent: true, opacity: 0.8, depthWrite: false }));
  scorch.position.set(pos.x, 0.02, pos.z);
  scorch.scale.setScalar(rand(1.6, 2.2));
  scene.add(scorch);
  decals.push(scorch);
  if (decals.length > 40) { const old = decals.shift(); scene.remove(old); old.material.dispose(); }
  // 玩家：伤害 + 震屏
  const pd = pos.distanceTo(camera.position);
  if (pd < 7 && losClear(pos, camera.position)) {
    damagePlayer(78 * (1 - pd / 7), null, 1.0);
  }
  const prox = clamp(1 - pd / 14, 0, 1);
  punch.vx += 2.2 * prox; punch.vy += rand(-0.8, 0.8) * prox;
  fovKick = Math.min(fovKick + 2.2 * prox, 2.5);
  trauma = Math.min(1, trauma + 0.7 * prox);
  // Bot（双方）伤害 + 致盲
  for (const b of bots) {
    if (b.dead) continue;
    const bp = b.group.position;
    const d = Math.hypot(bp.x - pos.x, bp.y + 1.2 - pos.y, bp.z - pos.z);
    if (d < 16) b.blindT = Math.max(b.blindT || 0, now() + 1.2);
    if (d < 7 && losClear(pos, new THREE.Vector3(bp.x, bp.y + 1.2, bp.z))) {
      damageBotDirect(b, 98 * (1 - d / 7), null);
    }
  }
  // 可破坏墙
  for (const rec of destructibles) {
    if (rec.dead) continue;
    const c = rec.center;
    const d = Math.hypot(c.x - pos.x, c.y - pos.y, c.z - pos.z);
    if (d < 7) damageWall(rec, 170 * (1 - d / 7));
  }
}
let flashAmt = 0;
function explodeFlash(pos) {
  const pf = panFor(pos);
  burst({ dur: 0.1, freq: 5200, q: 1, vol: 0.55 * (1 / (1 + pf.dist * 0.04)), pan: pf.pan, type: 'bandpass' });
  tone({ freq: 1900, end: 700, dur: 0.18, vol: 0.35, pan: pf.pan, type: 'square' });
  flashLightW.position.copy(pos); flashLightW.intensity = 8;
  addSpark(pos, 0xffffff, 1.2);
  // 玩家致盲：面向程度 + 距离 + 视线
  const pd = pos.distanceTo(camera.position);
  if (pd < 18 && losClear(pos, camera.position)) {
    const vd = new THREE.Vector3(); camera.getWorldDirection(vd);
    const toF = pos.clone().sub(camera.position).normalize();
    const facing = clamp((vd.dot(toF) + 0.6) / 1.2, 0, 1);
    flashAmt = Math.max(flashAmt, clamp((1 - pd / 18) * (0.3 + 0.7 * facing), 0, 1));
    trauma = Math.min(1, trauma + 0.2);
  }
  // Bot 致盲（双方）
  for (const b of bots) {
    if (b.dead) continue;
    const bp = b.group.position;
    const d = Math.hypot(bp.x - pos.x, bp.z - pos.z);
    if (d < 16 && losClear(pos, new THREE.Vector3(bp.x, bp.y + 1.5, bp.z))) {
      b.blindT = Math.max(b.blindT || 0, now() + rand(2.2, 3.2));
    }
  }
}
function updateNades(dt, t) {
  updateNadeArc();
  boomLight.intensity *= Math.max(0, 1 - dt * 6);
  flashLightW.intensity *= Math.max(0, 1 - dt * 8);
  flashAmt = Math.max(0, flashAmt - dt * 0.45);
  $('flashwhite').style.opacity = flashAmt > 0.02 ? Math.min(1, flashAmt + 0.25).toFixed(2) : 0;
  for (let i = nades.length - 1; i >= 0; i--) {
    const n = nades[i];
    n.vel.y -= 16 * dt;
    n.m.rotation.x += dt * 6;
    nadeCollide(n, 'x', n.vel.x * dt);
    nadeCollide(n, 'z', n.vel.z * dt);
    nadeCollide(n, 'y', n.vel.y * dt);
    if (n.m.position.y < 0.09 && n.vel.y < 0) {
      n.m.position.y = 0.09;
      if (Math.abs(n.vel.y) > 0.6) burst({ dur: 0.03, freq: 4200, q: 4, vol: 0.07, type: 'bandpass', pan: panFor(n.m.position).pan });
      n.vel.y *= -0.42; n.vel.x *= 0.75; n.vel.z *= 0.75;
    }
    if (t - n.born > 1.6) {
      const pos = n.m.position.clone();
      scene.remove(n.m);
      nades.splice(i, 1);
      if (n.type === 'he') explodeHE(pos); else explodeFlash(pos);
    }
  }
}
/* ---------------- 可破坏墙体碎片 ---------------- */
const chunks = [];
const chunkMat = new THREE.MeshStandardMaterial({ color: 0xb59a6c, roughness: 0.95 });
function chunkBurst(pos, size) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(size, size * rand(0.6, 1.2), size * rand(0.6, 1.2)), chunkMat);
  m.position.copy(pos);
  m.castShadow = true;
  scene.add(m);
  chunks.push({
    m, life: rand(2.2, 3.2),
    vel: new THREE.Vector3(rand(-3, 3), rand(2, 6), rand(-3, 3)),
    spin: rand(2, 7), settled: false,
  });
  if (chunks.length > 26) { const c = chunks.shift(); scene.remove(c.m); }
}
function updateChunks(dt) {
  for (let i = chunks.length - 1; i >= 0; i--) {
    const c = chunks[i];
    c.life -= dt;
    if (c.life <= 0) { scene.remove(c.m); chunks.splice(i, 1); continue; }
    if (c.settled) continue;
    c.vel.y -= 14 * dt;
    c.m.position.addScaledVector(c.vel, dt);
    c.m.rotation.x += c.spin * dt;
    c.m.rotation.z += c.spin * 0.6 * dt;
    if (c.m.position.y < 0.12 && c.vel.y < 0) {
      c.m.position.y = 0.12;
      if (Math.abs(c.vel.y) > 1.5) burst({ dur: 0.05, freq: 900, q: 2, vol: 0.12, type: 'bandpass', pan: panFor(c.m.position).pan });
      c.vel.y *= -0.3; c.vel.x *= 0.4; c.vel.z *= 0.4; c.spin *= 0.4;
      if (Math.abs(c.vel.y) < 0.5) { c.settled = true; c.m.rotation.set(rand(-0.2, 0.2), rand(0, 3), 0); }
    }
    for (const s of solids) { // 撞墙停
      const p = c.m.position;
      if (p.x > s.min.x && p.x < s.max.x && p.y > s.min.y && p.y < s.max.y && p.z > s.min.z && p.z < s.max.z) {
        c.settled = true; c.m.position.y = Math.max(c.m.position.y, s.max.y + 0.1);
        break;
      }
    }
  }
}
