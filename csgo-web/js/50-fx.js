/* CS:GO Web —— 特效/粒子/弹壳/掉落武器 */
'use strict';

/* ---------------- 特效 ---------------- */
const glowTex = (() => {
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const x = c.getContext('2d');
  const g = x.createRadialGradient(32, 32, 2, 32, 32, 30);
  g.addColorStop(0, 'rgba(255,255,255,1)');
  g.addColorStop(1, 'rgba(255,255,255,0)');
  x.fillStyle = g; x.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
})();
// 场景暖光灯布置（需在 glowTex 之后）
addLamp(0, -8.6, 3.6, 0.45, 12);      // 中路拱门
addLamp(-18.5, 3, 2.3, 0.35, 8);      // 左隧道内
addLamp(19, -15, 3.4, 0.4, 11);       // A 高台
addLamp(-17, -14, 3.4, 0.4, 11);      // B 区
addLamp(-6.5, 13, 3.8, 0.3, 9);       // 广场树旁
addLamp(6.5, 20, 3.8, 0.3, 9);        // 街边
/* —— CS2 氛围层：灯光光锥 / 漂浮尘埃 / 海报涂鸦 / 招牌布幌 —— */
const dustMotes = [];
const clothSigns = [];
const rayMat = new THREE.MeshBasicMaterial({
  color: 0xffe0b0, transparent: true, opacity: 0.045,
  blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide
});
[[0, -8.6, 3.6], [-18.5, 3, 2.2], [19, -15, 3.4], [-17, -14, 3.4]].forEach(([lx, lz, ly]) => {
  const cone = new THREE.Mesh(new THREE.ConeGeometry(1.5, ly, 12, 1, true), rayMat);
  cone.position.set(lx, ly / 2 + 0.2, lz);
  scene.add(cone);
});
for (let i = 0; i < 36; i++) {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({
    map: glowTex, color: 0xfff2d8, transparent: true, opacity: rand(0.05, 0.14), depthWrite: false
  }));
  s.position.set(rand(-24, 24), rand(0.2, 3.4), rand(-24, 24));
  s.scale.setScalar(rand(0.02, 0.05));
  scene.add(s);
  dustMotes.push({ s, ph: rand(0, 6), sp: rand(0.1, 0.3) });
}
function updateDust(t) {
  for (const d of dustMotes) {
    d.s.position.y += Math.sin(t * d.sp + d.ph) * 0.0008;
    d.s.position.x += Math.cos(t * d.sp * 0.7 + d.ph) * 0.0006;
  }
}
const posterCanvas = makeCanvas((x, s) => {
  x.fillStyle = '#d8cba8'; x.fillRect(6, 4, s - 12, s - 8);
  x.fillStyle = '#8a2f24'; x.fillRect(10, 8, s - 20, 56);
  x.fillStyle = '#f0e6cc'; x.font = 'bold 26px sans-serif'; x.textAlign = 'center';
  x.fillText('BAZAAR', s / 2, 46);
  for (let i = 0; i < 5; i++) { x.fillStyle = '#5a5142'; x.fillRect(20, 82 + i * 26, s - 44 - i * 14, 8); }
  x.fillStyle = '#3f6f4f'; x.fillRect(20, 222, 84, 10); x.fillRect(20, 240, 140, 10);
  x.fillStyle = '#b8ab88';
  x.beginPath(); x.moveTo(s - 6, s - 4); x.lineTo(s - 52, s - 4); x.lineTo(s - 6, s - 58); x.fill();
  noise(x, s, 260, 0.08);
});
const graffitiCanvas = makeCanvas((x, s) => {
  x.clearRect(0, 0, s, s);
  x.fillStyle = 'rgba(150,60,170,0.85)'; x.font = 'bold 46px sans-serif'; x.textAlign = 'center';
  x.save(); x.translate(s / 2, s / 2); x.rotate(-0.08); x.fillText('RUSH B', 0, 12); x.restore();
  x.fillStyle = 'rgba(70,120,170,0.8)'; x.font = 'bold 30px sans-serif';
  x.fillText('GG WP', s / 2, s - 38);
});
function addWallDecal(x, y, z, ry, canvas, w, h) {
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h),
    new THREE.MeshStandardMaterial({ map: toTex(canvas), transparent: true, roughness: 0.92 }));
  m.position.set(x, y, z);
  m.rotation.y = ry;
  scene.add(m);
}
function addClothSign(x, y, z, ry, w, h, color) {
  const geo = new THREE.PlaneGeometry(w, h);
  geo.translate(0, -h / 2, 0); // 枢轴移到顶边，可摇摆
  const m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color, roughness: 0.95, side: THREE.DoubleSide }));
  m.position.set(x, y, z);
  m.rotation.y = ry;
  scene.add(m);
  clothSigns.push({ m, ph: rand(0, 6) });
}
addWallDecal(-2.6, 2.3, -5.38, 0, posterCanvas, 1.1, 1.4);
addWallDecal(13.5, 2.6, -8.44, 0, posterCanvas, 1.2, 1.5);
addWallDecal(6, 1.9, -21.46, 0, graffitiCanvas, 2.2, 2.2);
addWallDecal(-13, 2.5, -9.46, 0, graffitiCanvas, 2.6, 2.6);
addClothSign(-16.5, 2.15, 7.15, 0, 2.1, 0.8, 0x8a3a2e);
addClothSign(-21.5, 2.15, 1.15, 0, 2.1, 0.8, 0x3a5a7a);
addClothSign(0, 3.3, -5.36, 0, 2.4, 0.7, 0x6a5a2e);
// 地面污渍/色斑（打破均匀平铺的"廉价感"）
(function addGroundGrime() {
  const spots = [
    [0, -4, 3.5], [3, -10, 2.6], [-4, 4, 3], [8, -6, 2.4], [-9, -6, 2.8],
    [0, 8, 3.2], [-6, 12, 2.2], [5, 14, 2.6], [12, 2, 2.4], [-14, 2, 2.6],
  ];
  for (let i = 0; i < spots.length; i++) {
    const [gx, gz, gs] = spots[i];
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({
      map: glowTex, color: i % 3 === 0 ? 0x6b5a40 : (i % 3 === 1 ? 0x574a34 : 0x7d6d4e),
      transparent: true, opacity: 0.32, depthWrite: false
    }));
    sp.scale.set(gs, gs * 0.55, 1);
    sp.material.rotation = rand(0, Math.PI * 2);
    sp.position.set(gx, 0.014, gz);
    scene.add(sp);
  }
})();

const effects = [];
/* ---------------- 粒子引擎 2.0（GPU 点精灵池：单 draw call × 600 粒子） ---------------- */
const P2 = (() => {
  const MAX = 600;
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(MAX * 3);
  const col = new Float32Array(MAX * 3);
  const attr = new Float32Array(MAX * 2);  // size, alpha
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('pcol', new THREE.BufferAttribute(col, 3));
  geo.setAttribute('pattr', new THREE.BufferAttribute(attr, 2));
  const mat = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: `
      attribute vec3 pcol; attribute vec2 pattr;
      varying vec3 vCol; varying float vA;
      void main() {
        vCol = pcol; vA = pattr.y;
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = pattr.x * (240.0 / -mv.z);
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: `
      varying vec3 vCol; varying float vA;
      void main() {
        float d = length(gl_PointCoord - 0.5);
        float a = smoothstep(0.5, 0.12, d) * vA;
        if (a < 0.01) discard;
        gl_FragColor = vec4(vCol, a);
      }`,
  });
  const points = new THREE.Points(geo, mat);
  points.frustumCulled = false;
  scene.add(points);
  // 粒子状态池
  const st = [];
  for (let i = 0; i < MAX; i++) st.push({ alive: false, life: 0, max: 1, vx: 0, vy: 0, vz: 0, grav: 0, drag: 0, size: 1, grow: 0, fade: 1, baseA: 1 });
  let ptr = 0;
  const c = new THREE.Color();
  function spawn(x, y, z, vx, vy, vz, color, size, life, opt) {
    const i = ptr; ptr = (ptr + 1) % MAX;
    const p = st[i];
    p.alive = true; p.life = life; p.max = life;
    p.vx = vx; p.vy = vy; p.vz = vz;
    p.grav = (opt && opt.grav) || 0;
    p.drag = (opt && opt.drag) || 0;
    p.grow = (opt && opt.grow) || 0;
    p.fade = (opt && opt.fade !== undefined) ? opt.fade : 1;
    p.baseA = (opt && opt.alpha !== undefined) ? opt.alpha : 1;
    p.size = size;
    pos[i * 3] = x; pos[i * 3 + 1] = y; pos[i * 3 + 2] = z;
    c.set(color);
    col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
    attr[i * 2] = size; attr[i * 2 + 1] = p.baseA;
  }
  function update(dt) {
    for (let i = 0; i < MAX; i++) {
      const p = st[i];
      if (!p.alive) { attr[i * 2 + 1] = 0; continue; }
      p.life -= dt;
      if (p.life <= 0) { p.alive = false; attr[i * 2 + 1] = 0; continue; }
      p.vy -= p.grav * dt;
      if (p.drag) { const d = Math.max(0, 1 - p.drag * dt); p.vx *= d; p.vy *= d; p.vz *= d; }
      pos[i * 3] += p.vx * dt;
      pos[i * 3 + 1] += p.vy * dt;
      pos[i * 3 + 2] += p.vz * dt;
      if (p.grow) p.size += p.grow * dt;
      const k = p.life / p.max;
      attr[i * 2] = p.size;
      attr[i * 2 + 1] = p.baseA * (p.fade ? k * k : 1);
    }
    geo.attributes.position.needsUpdate = true;
    geo.attributes.pcol.needsUpdate = true;
    geo.attributes.pattr.needsUpdate = true;
  }
  return { spawn, update };
})();

function addSpark(pos, color, scale) {
  // 亮芯 + 4 飞溅
  P2.spawn(pos.x, pos.y, pos.z, 0, 0, 0, color, scale * 26, 0.07, { alpha: 0.95 });
  for (let i = 0; i < 4; i++) {
    P2.spawn(pos.x, pos.y, pos.z,
      rand(-3, 3), rand(0.5, 3.5), rand(-3, 3),
      color, scale * 9, rand(0.12, 0.25), { grav: 9, drag: 2 });
  }
}
function addTracer(a, b) { // 双层曳光：亮芯 + 暖色辉光
  const g = new THREE.BufferGeometry().setFromPoints([a, b]);
  const glow = new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0xff9040, transparent: true, opacity: 0.32, depthTest: false }));
  const core = new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0xfff2c8, transparent: true, opacity: 0.95, depthTest: false }));
  scene.add(glow); scene.add(core);
  effects.push({ o: glow, life: 0.07, max: 0.07 });
  effects.push({ o: core, life: 0.05, max: 0.05 });
}
function addSmoke(pos) { // 枪口硝烟：8 粒缓升膨胀
  for (let i = 0; i < 8; i++) {
    P2.spawn(pos.x + rand(-0.05, 0.05), pos.y + rand(-0.02, 0.06), pos.z + rand(-0.05, 0.05),
      rand(-0.25, 0.25), rand(0.35, 0.8), rand(-0.25, 0.25),
      0x8d887d, rand(7, 11), rand(0.5, 0.9), { grow: 9, drag: 1.2, alpha: 0.16, fade: 1 });
  }
}
function addBlood(pos, dir) { // 血雾粒子
  for (let i = 0; i < 9; i++) {
    P2.spawn(pos.x, pos.y, pos.z,
      dir.x * rand(1, 3) + rand(-1.2, 1.2), rand(0.3, 2.6), dir.z * rand(1, 3) + rand(-1.2, 1.2),
      i % 3 ? 0xa11414 : 0x6e0d0d, rand(2.5, 5), rand(0.3, 0.5), { grav: 8, drag: 0.8 });
  }
}
function addDustPuff(pos, n, spread) { // 墙面/落地扬尘
  for (let i = 0; i < n; i++) {
    P2.spawn(pos.x + rand(-0.2, 0.2), pos.y + rand(-0.1, 0.2), pos.z + rand(-0.2, 0.2),
      rand(-spread, spread), rand(0.2, spread), rand(-spread, spread),
      0xb8a67e, rand(4, 8), rand(0.4, 0.8), { grow: 6, drag: 2, alpha: 0.2 });
  }
}
const decals = [];
function addDecal(point, normal, color) { // 弹孔 / 血渍
  const s = new THREE.Sprite(new THREE.SpriteMaterial({
    map: glowTex, color: color || 0x181209, transparent: true, opacity: 0.85, depthWrite: false
  }));
  s.position.copy(point).addScaledVector(normal, 0.02);
  s.scale.setScalar(0.09 + Math.random() * 0.04);
  scene.add(s);
  decals.push(s);
  if (decals.length > 40) { const old = decals.shift(); scene.remove(old); old.material.dispose(); }
}
/* ---------------- 碎屑粒子池（弹着物理碎块 / 金属火花） ---------------- */
const debris = [];
const debrisGeo = new THREE.BoxGeometry(0.035, 0.035, 0.035);
const debrisMat = new THREE.MeshStandardMaterial({ color: 0x8a7a5a, roughness: 1 });
const sparkMat = new THREE.MeshStandardMaterial({ color: 0xffcc66, emissive: 0xffaa33, emissiveIntensity: 2.5, roughness: 0.4 });
function burstDebris(point, normal, metal) {
  for (let i = 0; i < (metal ? 7 : 5); i++) {
    let d = debris.find(x => !x.alive);
    if (!d) {
      if (debris.length >= 28) d = debris[0];
      else {
        d = { m: new THREE.Mesh(debrisGeo, metal ? sparkMat : debrisMat), vel: new THREE.Vector3(), alive: false, life: 0 };
        scene.add(d.m);
        debris.push(d);
      }
    }
    d.m.material = metal ? sparkMat : debrisMat;
    d.alive = true;
    d.life = rand(0.5, 1.1);
    d.m.visible = true;
    d.m.position.copy(point);
    d.m.scale.setScalar(rand(0.6, 1.4));
    d.vel.set(
      normal.x * rand(1, 3.5) + rand(-1.5, 1.5),
      normal.y * rand(1, 3) + rand(0.5, 2.5),
      normal.z * rand(1, 3.5) + rand(-1.5, 1.5)
    );
    d.spin = rand(-14, 14);
  }
}
function updateDebris(dt) {
  for (const d of debris) {
    if (!d.alive) continue;
    d.life -= dt;
    if (d.life <= 0) { d.alive = false; d.m.visible = false; continue; }
    d.vel.y -= 14 * dt;
    d.m.position.addScaledVector(d.vel, dt);
    d.m.rotation.x += d.spin * dt;
    d.m.rotation.z += d.spin * 0.7 * dt;
    if (d.m.position.y < 0.02 && d.vel.y < 0) {
      d.m.position.y = 0.02;
      d.vel.y *= -0.35; d.vel.x *= 0.5; d.vel.z *= 0.5; d.spin *= 0.5;
    }
  }
}
function clearDecals() {
  for (const d of decals) { scene.remove(d); d.material.dispose(); }
  decals.length = 0;
}
function updateEffects(dt) {
  for (let i = effects.length - 1; i >= 0; i--) {
    const e = effects[i];
    e.life -= dt;
    if (e.life <= 0) {
      scene.remove(e.o);
      if (e.o.geometry) e.o.geometry.dispose();
      e.o.material.dispose();
      effects.splice(i, 1);
      continue;
    }
    e.o.material.opacity = (e.life / e.max) * (e.op || 1);
    if (e.grow) e.o.scale.setScalar(e.base * (1 + (1 - e.life / e.max) * 1.6));
    if (e.vel) {
      e.vel.y -= (e.grav || 0) * dt;
      e.o.position.addScaledVector(e.vel, dt);
    }
    if (e.rise) e.o.position.y += e.rise * dt;
  }
}
/* ---------------- 弹壳物理 ---------------- */
const shells = [];
const shellGeo = new THREE.BoxGeometry(0.012, 0.012, 0.03);
const shellMat = new THREE.MeshPhongMaterial({ color: 0xd9a441, shininess: 80, specular: 0xccaa44 });
function spawnShell() {
  const m = new THREE.Mesh(shellGeo, shellMat);
  const p = vm && vm.visible ? vm.localToWorld(new THREE.Vector3(0.05, 0.02, -0.35)) : camera.position.clone();
  m.position.copy(p);
  scene.add(m);
  const rx = Math.cos(player.yaw), rz = -Math.sin(player.yaw);
  shells.push({
    m,
    vel: new THREE.Vector3(rx * rand(1.2, 2), rand(1.5, 2.5), rz * rand(1.2, 2)),
    rot: rand(8, 16), life: 9
  });
  if (shells.length > 40) { const s = shells.shift(); scene.remove(s.m); }
}
function updateShells(dt) {
  for (let i = shells.length - 1; i >= 0; i--) {
    const s = shells[i];
    s.life -= dt;
    if (s.life <= 0) { scene.remove(s.m); shells.splice(i, 1); continue; }
    s.vel.y -= 12 * dt;
    s.m.position.addScaledVector(s.vel, dt);
    s.m.rotation.x += s.rot * dt;
    s.m.rotation.z += s.rot * 0.6 * dt;
    if (s.m.position.y < 0.012 && s.vel.y < 0) {
      s.m.position.y = 0.012;
      if (Math.abs(s.vel.y) > 0.5) burst({ dur: 0.03, freq: 5200, q: 4, vol: 0.05, type: 'bandpass' });
      s.vel.y *= -0.3; s.vel.x *= 0.5; s.vel.z *= 0.5; s.rot *= 0.4;
    }
  }
}
/* ---------------- 掉落武器（可拾取） ---------------- */
const groundGuns = [];
const GG_GEO = {
  body: new THREE.BoxGeometry(0.07, 0.09, 0.55),
  mag: new THREE.BoxGeometry(0.05, 0.14, 0.07),
  stock: new THREE.BoxGeometry(0.05, 0.08, 0.2),
};
function dropGun(pos, id) {
  const g = new THREE.Group();
  const body = new THREE.Mesh(GG_GEO.body, BOT_M.gun); body.position.y = 0.05;
  const mag = new THREE.Mesh(GG_GEO.mag, BOT_M.gun); mag.position.set(0, 0.02, 0.05); mag.rotation.x = 0.4;
  const stock = new THREE.Mesh(GG_GEO.stock, BOT_M.wood); stock.position.set(0, 0.05, -0.32);
  g.add(body, mag, stock);
  g.position.set(pos.x + rand(-0.4, 0.4), 0, pos.z + rand(-0.4, 0.4));
  g.rotation.y = rand(0, Math.PI * 2);
  scene.add(g);
  groundGuns.push({ g, id });
}
function clearGroundGuns() {
  for (const gg of groundGuns) scene.remove(gg.g);
  groundGuns.length = 0;
}
function tryPickup() { // E 拾取掉落武器
  if (!player.alive || buyOpen) return;
  let best = null, bd = 2.2;
  for (const gg of groundGuns) {
    const d = Math.hypot(gg.g.position.x - player.pos.x, gg.g.position.z - player.pos.z);
    if (d < bd) { bd = d; best = gg; }
  }
  if (!best) return;
  groundGuns.splice(groundGuns.indexOf(best), 1);
  scene.remove(best.g);
  const w = makeWeapon(best.id);
  if (player.cur === 'primary') player.lastSlot = 'primary';
  player.slots.primary = w;
  player.cur = 'primary';
  player.switchEnd = now() + 0.35;
  aiming = false; awpStage = 0;
  rebuildVM();
  drawSound();
  toast('拾取 ' + w.def.name);
}
