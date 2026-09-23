/* CS:GO Web —— 可破坏墙/建筑系统/粒子引擎前置 */
'use strict';

/* ---------------- 可破坏墙（血量 → 裂纹 → 倒塌碎片，回合复原） ---------------- */
function crackCanvasFrom(src, level) {
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const x = c.getContext('2d');
  x.drawImage(src, 0, 0);
  x.strokeStyle = 'rgba(28,20,10,0.85)';
  for (let i = 0; i < 6 * level; i++) {
    x.lineWidth = rand(1, 2.5);
    x.beginPath();
    let px = rand(0, 256), py = rand(0, 256);
    x.moveTo(px, py);
    for (let j = 0; j < 6; j++) { px += rand(-30, 30); py += rand(-30, 30); x.lineTo(px, py); }
    x.stroke();
  }
  x.fillStyle = 'rgba(20,14,6,0.12)';
  for (let i = 0; i < 8 * level; i++) x.fillRect(rand(0, 256), rand(0, 256), rand(6, 30), rand(4, 20));
  return c;
}
const wallLvMats = [null,
  new THREE.MeshStandardMaterial({ map: toTex(crackCanvasFrom(plasterCanvas, 1)), roughness: 0.9 }),
  new THREE.MeshStandardMaterial({ map: toTex(crackCanvasFrom(plasterCanvas, 2.4)), roughness: 0.95, color: 0xcfcabc }),
];
const destructibles = [];
function addDestructible(x, y, z, w, h, d, kind, hp) {
  const base = matFor(kind, w, h, d);
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), base.clone());
  m.position.set(x, y + h / 2, z);
  m.castShadow = m.receiveShadow = true;
  scene.add(m);
  const solid = {
    min: new THREE.Vector3(x - w / 2, y, z - d / 2),
    max: new THREE.Vector3(x + w / 2, y + h, z + d / 2)
  };
  solids.push(solid);
  rayWalls.push(m);
  const rec = {
    m, solid, hp, maxHp: hp, level: 0, dead: false,
    args: { x, y, z, w, h, d, kind, hp },
    center: new THREE.Vector3(x, y + h / 2, z),
  };
  m.userData.destr = rec;
  destructibles.push(rec);
  return rec;
}
function damageWall(rec, dmg) {
  if (rec.dead) return;
  rec.hp -= dmg;
  const frac = rec.hp / rec.maxHp;
  const lv = frac > 0.62 ? 0 : frac > 0.3 ? 1 : 2;
  if (lv !== rec.level) {
    rec.level = lv;
    rec.m.material = lv ? wallLvMats[lv] : matFor(rec.args.kind, rec.args.w, rec.args.h, rec.args.d);
  }
  if (rec.hp <= 0) destroyWall(rec);
}
function destroyWall(rec) {
  rec.dead = true;
  scene.remove(rec.m);
  solids.splice(solids.indexOf(rec.solid), 1);
  rayWalls.splice(rayWalls.indexOf(rec.m), 1);
  staticTargets = staticTargets.filter(m2 => m2 !== rec.m);
  const c = rec.center;
  for (let i = 0; i < 12; i++) {
    chunkBurst(new THREE.Vector3(c.x + rand(-rec.args.w / 2, rec.args.w / 2), c.y + rand(-rec.args.h / 2, rec.args.h / 2), c.z + rand(-rec.args.d / 2, rec.args.d / 2)), rand(0.18, 0.5));
  }
  for (let i = 0; i < 3; i++) addSmoke(c.clone().add(new THREE.Vector3(rand(-1, 1), rand(0, 1), rand(-1, 1))));
  burst({ dur: 0.5, freq: 300, vol: 0.6, decay: 1.2 });
  trauma = Math.min(1, trauma + 0.3);
}
function restoreWalls() {
  for (const rec of destructibles) {
    if (!rec.dead) { rec.hp = rec.maxHp; rec.level = 0; rec.m.material = matFor(rec.args.kind, rec.args.w, rec.args.h, rec.args.d); continue; }
    rec.dead = false;
    rec.hp = rec.maxHp;
    rec.level = 0;
    rec.m.material = matFor(rec.args.kind, rec.args.w, rec.args.h, rec.args.d).clone();
    scene.add(rec.m);
    solids.push(rec.solid);
    rayWalls.push(rec.m);
    staticTargets.push(rec.m);
  }
}

const floorMesh = new THREE.Mesh(new THREE.PlaneGeometry(72, 72), MAT.floor);
floorMesh.rotation.x = -Math.PI / 2;
floorMesh.receiveShadow = true;
scene.add(floorMesh);

/* —— 56×56 多区域竞技场 —— */
// 外墙
addBox(0, 0, -27, 56, 4, 1, 'wall');
addBox(0, 0, 27, 56, 4, 1, 'wall');
addBox(-27, 0, 0, 1, 4, 56, 'wall');
addBox(27, 0, 0, 1, 4, 56, 'wall');
// —— 中路：双柱拱门（左段可破坏） ——
addDestructible(-7, 0, -6, 10, 3, 1, 'wall2', 340); // 左段
addBox(7, 0, -6, 10, 3, 1, 'wall2');         // 右段
addBox(-2.6, 0, -6, 1.2, 3.6, 1.2, 'wall');  // 左门柱
addBox(2.6, 0, -6, 1.2, 3.6, 1.2, 'wall');   // 右门柱
addBox(0, 3.4, -6, 6.4, 0.8, 1.2, 'wall');   // 拱梁
addBox(0, 0, -13, 1.6, 1.1, 1.6, 'crate');   // 拱后木箱
addCyl(5.5, -12, 0.45, 1.1);                 // 油桶对
addCyl(6.5, -12.6, 0.45, 1.1);
addBox(-6, 0, -16, 5, 0.8, 0.8, 'sand');     // 沙袋掩体
// —— 左路：长廊 + 顶盖隧道（B 通路） ——
addBox(-13, 0, 12, 1, 3, 20, 'wall');        // 长廊右墙
addBox(-24, 0, 12, 1, 3, 20, 'wall');        // 长廊左墙
addBox(-18.5, 2.6, 3, 12, 0.5, 11, 'plat');  // 隧道顶盖 z -2.5..8.5
addBox(-18.5, 0, -3, 1, 3, 5, 'wall');       // 隧道口分隔柱
// —— B 区（西南广场） ——
addDestructible(-22, 0, -14, 3, 2.2, 3, 'wall2', 260); // B 区高台箱（可破坏）
addBox(-22, 2.2, -14, 2.4, 1.8, 2.4, 'crate');
addBox(-14, 0, -20, 2, 1.1, 2, 'crate');
addCyl(-11.5, -19, 0.45, 1.1);
addCyl(-10.6, -18.2, 0.45, 1.1);
addBox(-17, 0, -10, 6, 0.8, 0.8, 'sand');
// —— 右路：A 高台 + 三级台阶（可自动登步） ——
addBox(19, 0, -15, 12, 1.2, 12, 'plat');     // 高台 x13..25, z-21..-9
addBox(19, 0, -8.4, 6, 0.3, 1.2, 'plat');    // 台阶 1
addBox(19, 0.3, -7.2, 6, 0.3, 1.2, 'plat');  // 台阶 2
addBox(19, 0.6, -6.0, 6, 0.3, 1.2, 'plat');  // 台阶 3
addBox(16, 1.2, -18, 2, 1.1, 2, 'crate');    // 台上掩体
addBox(22, 1.2, -12, 2, 1.1, 2, 'crate');
addBox(22, 2.3, -12, 1.6, 1.0, 1.6, 'crate');
addBox(25.6, 1.2, -15, 0.8, 1.0, 12, 'wall2'); // 台边护栏
addBox(13, 0, 8, 1, 3, 18, 'wall');          // 右长墙 z-1..17
addDestructible(9, 0, 2, 8, 3, 1, 'wall2', 340); // 中右连接墙（可破坏）
// —— CT 出生点掩体 ——
addBox(-7, 0, 18, 4, 1.0, 0.7, 'sand');
addBox(7, 0, 18, 4, 1.0, 0.7, 'sand');
addBox(0, 0, 12, 6, 0.8, 0.8, 'sand');       // 前沿沙袋（可跳越）
// —— T 侧 ——
addDestructible(6, 0, -22, 8, 3, 1, 'wall2', 340); // T 出生前墙（可破坏）
addCyl(-3, -22, 0.45, 1.1);
addCyl(-2.1, -21.2, 0.45, 1.1);
addBox(-8, 0, -18, 2, 1.1, 2, 'crate');

/* —— 城市广场（巴黎式） —— */
// 发光招牌贴图
function makeSignTex(text, bg, fg) {
  const c = document.createElement('canvas'); c.width = 256; c.height = 64;
  const x = c.getContext('2d');
  x.fillStyle = bg; x.fillRect(0, 0, 256, 64);
  x.strokeStyle = fg; x.lineWidth = 4; x.strokeRect(4, 4, 248, 56);
  x.fillStyle = fg;
  x.font = 'bold 30px Georgia';
  x.textAlign = 'center'; x.textBaseline = 'middle';
  x.fillText(text, 128, 34);
  const t = new THREE.CanvasTexture(c);
  t.encoding = THREE.sRGBEncoding;
  return t;
}
const ZINC = new THREE.MeshStandardMaterial({ color: 0x4a4e55, roughness: 0.6, metalness: 0.5, envMapIntensity: 0.6 });
const IRON = new THREE.MeshStandardMaterial({ color: 0x1d1f22, roughness: 0.5, metalness: 0.7 });
const FRAME = new THREE.MeshStandardMaterial({ color: 0xe8e0cc, roughness: 0.8 });
// 广场喷泉（多层水盘）
function addFountain(x, z) {
  const stone = matFor('plat', 2, 2, 2);
  const base = new THREE.Mesh(new THREE.CylinderGeometry(2.3, 2.5, 0.55, 16), stone);
  base.position.set(x, 0.28, z);
  base.castShadow = base.receiveShadow = true;
  scene.add(base);
  const water = new THREE.Mesh(new THREE.CylinderGeometry(2.05, 2.05, 0.12, 16),
    new THREE.MeshStandardMaterial({ color: 0x3f7f9e, roughness: 0.05, metalness: 0.2, transparent: true, opacity: 0.85, emissive: 0x0a2029, emissiveIntensity: 0.6 }));
  water.position.set(x, 0.56, z);
  scene.add(water);
  const col = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.45, 1.5, 12), stone);
  col.position.set(x, 1.3, z);
  col.castShadow = true;
  scene.add(col);
  const bowl = new THREE.Mesh(new THREE.CylinderGeometry(1.1, 0.5, 0.42, 12), stone);
  bowl.position.set(x, 2.15, z);
  bowl.castShadow = true;
  scene.add(bowl);
  const water2 = water.clone();
  water2.scale.set(0.52, 1, 0.52);
  water2.position.set(x, 2.37, z);
  scene.add(water2);
  const fin = new THREE.Mesh(new THREE.SphereGeometry(0.18, 10, 8), stone);
  fin.position.set(x, 2.75, z);
  scene.add(fin);
  solids.push({ min: new THREE.Vector3(x - 2.4, 0, z - 2.4), max: new THREE.Vector3(x + 2.4, 2.5, z + 2.4) });
  rayWalls.push(base, col, bowl);
}
// 行道棕榈（三段弯干 + 环纹 + 羽状下垂叶冠 + 椰果 + 枯叶）
const LEAF = new THREE.MeshStandardMaterial({ color: 0x4a6b2e, roughness: 0.9, side: THREE.DoubleSide });
const LEAF_DRY = new THREE.MeshStandardMaterial({ color: 0x8a7a3e, roughness: 0.95, side: THREE.DoubleSide });
function buildFrond(len, mat) { // 羽状叶：4 段渐细 + 逐段下垂
  const g = new THREE.Group();
  let y = 0, segLen = len / 4, droop = 0.15;
  for (let i = 0; i < 4; i++) {
    const w = 0.2 * (1 - i * 0.2);
    const seg = new THREE.Mesh(new THREE.BoxGeometry(w, 0.035, segLen * 1.15), mat);
    seg.position.set(0, y - Math.sin(droop) * segLen / 2, segLen / 2 * Math.cos(droop));
    seg.rotation.x = droop;
    seg.castShadow = true;
    g.add(seg);
    y -= Math.sin(droop) * segLen;
    droop += 0.28;
  }
  return g;
}
function addTree(x, z) {
  const bend = rand(0.04, 0.1);
  // 三段树干（逐段偏移+微弯，视觉连续）
  let cx = x, cy = 0;
  const segs = [[2.4, 0.2, 0.16], [1.3, 0.16, 0.13], [1.0, 0.13, 0.11]];
  for (const [len, r1, r2] of segs) {
    const seg = new THREE.Mesh(new THREE.CylinderGeometry(r2, r1, len, 8), matFor('crate', 1, 1, 1));
    cx += Math.sin(bend) * len / 2;
    seg.position.set(cx, cy + len / 2, z);
    seg.rotation.z = bend;
    seg.castShadow = true;
    scene.add(seg);
    rayWalls.push(seg);
    cy += len * Math.cos(bend);
    cx += Math.sin(bend) * len / 2;
  }
  const topX = cx, topY = cy + 0.05;
  // 叶冠：10 片羽状叶放射 + 高度/倾角随机
  for (let i = 0; i < 10; i++) {
    const fr = buildFrond(rand(1.5, 2.1), i % 5 === 4 ? LEAF_DRY : LEAF);
    fr.position.set(topX, topY + rand(0, 0.12), z);
    fr.rotation.y = i * Math.PI * 2 / 10 + rand(-0.25, 0.25);
    fr.rotation.z = rand(-0.12, 0.12);
    scene.add(fr);
  }
  // 椰果簇
  for (let i = 0; i < 4; i++) {
    const nut = new THREE.Mesh(new THREE.SphereGeometry(0.1, 7, 6), matFor('crate', 1, 1, 1));
    nut.position.set(topX + rand(-0.18, 0.18), topY - 0.18, z + rand(-0.18, 0.18));
    nut.castShadow = true;
    scene.add(nut);
  }
  solids.push({ min: new THREE.Vector3(x - 0.24, 0, z - 0.24), max: new THREE.Vector3(x + 0.4, 3.6, z + 0.24) });
}
// 长椅 / 碎石桩 / 红绿灯
function addBench(x, z, ry) {
  const g = new THREE.Group();
  const seat = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.08, 0.5), matFor('crate', 1, 1, 1));
  seat.position.y = 0.45;
  const back = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.45, 0.07), matFor('crate', 1, 1, 1));
  back.position.set(0, 0.75, -0.24);
  const legL = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.45, 0.45), IRON);
  legL.position.set(-0.75, 0.22, 0);
  const legR = legL.clone();
  legR.position.x = 0.75;
  [seat, back, legL, legR].forEach(m => { m.castShadow = true; g.add(m); });
  g.position.set(x, 0, z);
  g.rotation.y = ry;
  scene.add(g);
  solids.push({ min: new THREE.Vector3(x - 0.9, 0, z - 0.35), max: new THREE.Vector3(x + 0.9, 0.9, z + 0.35) });
}
function addBollards(x0, z0, x1, z1, n) {
  for (let i = 0; i < n; i++) {
    const bx = x0 + (x1 - x0) * i / (n - 1), bz = z0 + (z1 - z0) * i / (n - 1);
    const b = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.11, 0.85, 8), IRON);
    b.position.set(bx, 0.42, bz);
    b.castShadow = true;
    scene.add(b);
    rayWalls.push(b);
  }
}
function addTrafficLight(x, z) {
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.08, 4.6, 8), IRON);
  pole.position.set(x, 2.3, z);
  pole.castShadow = true;
  scene.add(pole);
  const boxM = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.9, 0.25), IRON);
  boxM.position.set(x, 4.2, z);
  scene.add(boxM);
  [['#ff4444', 0.35], ['#ffcc33', 0], ['#4dff6a', -0.35]].forEach(([c2, dy], i) => {
    const lit = new THREE.Mesh(new THREE.SphereGeometry(0.09, 8, 8),
      new THREE.MeshStandardMaterial({ color: c2, emissive: c2, emissiveIntensity: i === 0 ? 1.6 : 0.15, roughness: 0.3 }));
    lit.position.set(x, 4.2 + dy, z + 0.14);
    scene.add(lit);
  });
  solids.push({ min: new THREE.Vector3(x - 0.15, 0, z - 0.15), max: new THREE.Vector3(x + 0.15, 4.4, z + 0.15) });
}
/* —— 中东民居系统：带门洞窗洞的实心墙（可穿窗射击） —— */
function addGrille(c, fixed, y0, y1, w, axis) { // 木窗栅（视觉件，子弹从缝隙穿过）
  for (let i = 1; i <= 4; i++) {
    const off = -w / 2 + i * w / 5;
    const bar = new THREE.Mesh(new THREE.BoxGeometry(0.06, y1 - y0 - 0.06, 0.06), matFor('crate', 1, 1, 1));
    if (axis === 'x') bar.position.set(c + off, (y0 + y1) / 2, fixed);
    else bar.position.set(fixed, (y0 + y1) / 2, c + off);
    bar.castShadow = true;
    scene.add(bar);
  }
}
function wallRun(a, b, fixed, h, axis, openings) {
  const th = 0.35;
  const ops = (openings || []).slice().sort((p, q) => p.c - q.c);
  const segs = [];
  let cur = a;
  for (const o of ops) {
    const l = o.c - o.w / 2, r = o.c + o.w / 2;
    if (l - cur > 0.02) segs.push([cur, l, 0, h, 'wall']);
    if (o.b > 0.02) segs.push([l, r, 0, o.b, 'plat']);     // 窗台
    if (h - o.t > 0.02) segs.push([l, r, o.t, h, 'plat']); // 门楣/窗楣
    if (o.g) addGrille(o.c, fixed, o.b, o.t, o.w, axis);
    cur = r;
  }
  if (b - cur > 0.02) segs.push([cur, b, 0, h, 'wall']);
  for (const [s0, s1, y0, y1, kd] of segs) {
    const w2 = s1 - s0, hh = y1 - y0;
    if (axis === 'x') addBox((s0 + s1) / 2, y0, fixed, w2, hh, th, kd);
    else addBox(fixed, y0, (s0 + s1) / 2, th, hh, w2, kd);
  }
}
const wallX = (a, b, z, h, ops) => wallRun(a, b, z, h, 'x', ops);
const wallZ = (a, b, x, h, ops) => wallRun(a, b, x, h, 'z', ops);
function addLantern(x, y, z) { // 室内吊灯（自发光 + 点光源）
  const m = new THREE.Mesh(new THREE.SphereGeometry(0.12, 8, 6),
    new THREE.MeshStandardMaterial({ color: 0xffdd99, emissive: 0xffaa44, emissiveIntensity: 2.5 }));
  m.position.set(x, y, z);
  scene.add(m);
  const L = new THREE.PointLight(0xffb268, 0.75, 7, 2);
  L.position.set(x, y, z);
  scene.add(L);
}
function addDome(x, y, z, r) { // 穹顶
  const d = new THREE.Mesh(new THREE.SphereGeometry(r, 14, 8, 0, Math.PI * 2, 0, Math.PI / 2), matFor('plat', 2, 2, 2));
  d.position.set(x, y, z);
  d.castShadow = true;
  scene.add(d);
  rayWalls.push(d);
}
// 可进入民居：门厅(前房) + 内门 + 后廊，东北/西北角二层块+穹顶，屋顶露台+护墙，外侧实体阶梯
function buildHouse(cx, side) { // side: -1 西侧 / 1 东侧；占地 9×8 (z 18..26)
  const x0 = cx - 4.5, x1 = cx + 4.5;
  const zF = 18, zB = 26;
  const ux0 = side < 0 ? cx : cx - 4.5;      // 二层块（贴地图中线一侧，宽 4.5）
  const ubc = ux0 + 2.25;
  const doorX = cx + side * 2.2;
  const winA = cx - side * 1.2, winB = cx - side * 3.2;
  const outX = side < 0 ? x0 : x1;
  const inX = side < 0 ? x1 : x0;
  // 南墙（门 + 两窗）
  wallX(x0, x1, zF, 3.2, [
    { c: doorX, w: 1.5, b: 0, t: 2.4 },
    { c: winA, w: 1.4, b: 1.0, t: 2.3, g: 1 },
    { c: winB, w: 1.4, b: 1.0, t: 2.3, g: 1 },
  ]);
  wallZ(zF, zB, outX, 3.2, []);                                           // 外侧墙（外侧有楼梯）
  wallZ(zF, 22, inX, 3.2, [{ c: 19.8, w: 1.3, b: 1.0, t: 2.3, g: 1 }]);  // 内侧前段一窗
  wallX(x0, x1, zB - 0.2, 3.2, []);                                       // 北墙
  wallX(x0, x1, 22, 3.2, [{ c: outX + side * 1.5, w: 1.2, b: 0, t: 2.2 }]); // 内隔墙(带门洞)
  // 二层块（背面内侧半）+ 窗 + 平屋顶 + 穹顶
  addBox(ubc, 0, 24, 4.5, 6.6, 4, 'plaster');
  for (const wx of [ubc - 1.2, ubc + 1.2]) facePanel(wx, 4.6, 22, 1.2, 1.5, 'z', -0.08, 'window');
  addBox(ubc, 6.6, 24, 5, 0.25, 4.5, 'roof');
  addDome(ubc, 6.85, 24, 1.3);
  // 屋顶：前房全宽 + 外侧后廊条带
  addBox(cx, 3.2, 20, 9, 0.3, 4, 'plat');
  const bcx = side < 0 ? (x0 + ux0) / 2 : (ux0 + 4.5 + x1) / 2;
  const bw = 4.5;
  addBox(bcx, 3.2, 24, bw, 0.3, 4, 'plat');
  // 露台护墙（南侧全宽；外侧留楼梯口）
  addBox(cx, 3.5, zF + 0.15, 9, 0.8, 0.3, 'wall');
  addBox(outX - side * 0.15, 3.5, 21, 0.3, 0.8, 2, 'wall');
  // 外侧实体阶梯（10 级上屋顶，0.325 步高可自动登步）
  const sx = outX + side * 0.9;
  for (let i = 0; i < 10; i++) addBox(sx, 0, 25.3 - i * 0.78, 1.4, 0.325 * (i + 1), 0.8, 'plat');
  // 室内：吊灯 + 地毯 + 后廊木箱
  addLantern(cx + side * 2.2, 2.4, 20);
  addBox(cx - side * 0.6, 0.03, 20, 2.6, 0.05, 1.8, 'cloth');
  addBox(bcx, 0, 24.5, 1.3, 1.1, 1.3, 'crate');
}
/* —— 小镇场景 —— */
// CT 侧：两栋可进入的中东民居（门厅→内门→后廊，屋顶露台，角楼穹顶）
buildHouse(-13, -1);
buildHouse(13, 1);
addBox(-24.5, 0, 25.5, 5, 6, 4, 'plaster');  // 街角院墙
addBox(24.5, 0, 25.5, 5, 6, 4, 'plaster');
addDome(-24.5, 6, 25.5, 1.5);
addDome(24.5, 6, 25.5, 1.5);
// B 区小屋（可进入，穹顶）
wallX(-26.5, -22.5, -18, 2.8, [{ c: -24.5, w: 1.4, b: 0, t: 2.2 }]);
wallX(-26.5, -22.5, -22, 2.8, []);
wallZ(-22, -18, -26.4, 2.8, [{ c: -20, w: 1.3, b: 0.9, t: 2.1, g: 1 }]);
wallZ(-22, -18, -22.6, 2.8, []);
addBox(-24.5, 2.8, -20, 4.4, 0.3, 4.4, 'plat');
addDome(-24.5, 3.1, -20, 1.4);
addLantern(-24.5, 2.1, -20);
addBox(-25.6, 0, -21, 1.1, 1.1, 1.1, 'crate');
// 广场：喷泉 + 树 + 长椅 + 桩柱 + 红绿灯 + 广告牌
addFountain(0, 5.5);
addTree(-7.5, 10); addTree(7.5, 10);
addTree(-7.5, 17); addTree(7.5, 17);
addBench(-4.2, 5.5, Math.PI / 2);
addBench(4.2, 5.5, -Math.PI / 2);
addBench(0, 10.8, 0);
addBollards(-9.6, 8, -9.6, 20, 5);
addBollards(9.6, 8, 9.6, 20, 5);
addTrafficLight(11.2, 5.2);
// 中门集市场招（发光）
(function () {
  const st = makeSignTex('سوق · SOUK', '#2a1c0c', '#ffd9a0');
  const board = new THREE.Mesh(new THREE.BoxGeometry(3.4, 0.85, 0.15),
    new THREE.MeshStandardMaterial({ map: st, emissive: 0xffffff, emissiveMap: st, emissiveIntensity: 1.2, color: 0x777777 }));
  board.position.set(0, 4.1, -5.4);
  scene.add(board);
})();
addBox(0, 0, 16, 18, 0.06, 26, 'cobble');       // 中央石板街
addBox(-10.2, 0, 18, 0.3, 0.28, 12, 'plat');    // 路缘
addBox(10.2, 0, 18, 0.3, 0.28, 12, 'plat');
addBuilding(23, -20, 4.5, 4.5, 7, 'S');         // A 高台角楼
addStall(-16.5, 6.5);                           // 巴扎摊位 ×2
addStall(-21.5, 0.5);
addCar(-6, -22.5, 0x7a4a3a);                    // T 院报废车
addRubble(5, -24);
addRubble(-20, -22);
addPole(8, 22, 5.2);
addPole(8, 10, 5.2);
addPole(8, -2, 5.2);
addWire(new THREE.Vector3(8, 4.8, 22), new THREE.Vector3(8, 4.8, 10));
addWire(new THREE.Vector3(8, 4.8, 10), new THREE.Vector3(8, 4.8, -2));

/* —— 场外远景：小镇天际线（无碰撞，雾中剪影） —— */
const skylineMat = new THREE.MeshLambertMaterial({ color: 0xb5ac96 });
const skylineMat2 = new THREE.MeshLambertMaterial({ color: 0xc4bba4 });
const domeMat = new THREE.MeshLambertMaterial({ color: 0x9fae9a });
(function addSkyline() {
  const N = 30;
  for (let i = 0; i < N; i++) {
    const a = (i / N) * Math.PI * 2 + rand(-0.07, 0.07);
    const R = rand(46, 72);
    const w = rand(7, 17), h = rand(4.5, 15), d = rand(6, 12);
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), i % 2 ? skylineMat : skylineMat2);
    m.position.set(Math.sin(a) * R, h / 2 - rand(0, 1.5), Math.cos(a) * R);
    m.rotation.y = rand(0, Math.PI);
    scene.add(m);
    // 部分楼顶水箱/天线
    if (Math.random() < 0.4) {
      const t = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 1.2, 8), skylineMat);
      t.position.set(m.position.x + rand(-w / 3, w / 3), h + 0.6, m.position.z + rand(-d / 3, d / 3));
      scene.add(t);
    }
  }
  // 远处清真寺：穹顶 + 宣礼塔
  const base = new THREE.Mesh(new THREE.BoxGeometry(9, 8, 9), skylineMat2);
  base.position.set(-38, 4, -56);
  scene.add(base);
  const dome = new THREE.Mesh(new THREE.SphereGeometry(4.2, 16, 10, 0, Math.PI * 2, 0, Math.PI / 2), domeMat);
  dome.position.set(-38, 8, -56);
  scene.add(dome);
  const tower = new THREE.Mesh(new THREE.BoxGeometry(1.8, 17, 1.8), skylineMat2);
  tower.position.set(-30, 8.5, -53);
  scene.add(tower);
  const cap = new THREE.Mesh(new THREE.SphereGeometry(1.35, 10, 8, 0, Math.PI * 2, 0, Math.PI / 2), domeMat);
  cap.position.set(-30, 17, -53);
  scene.add(cap);
  // 远山脊
  const ridgeMat = new THREE.MeshLambertMaterial({ color: 0xa9b2a6 });
  for (let i = 0; i < 10; i++) {
    const a2 = i / 10 * Math.PI * 2;
    const r2 = new THREE.Mesh(new THREE.ConeGeometry(rand(14, 26), rand(8, 18), 5), ridgeMat);
    r2.position.set(Math.sin(a2) * 88, 2, Math.cos(a2) * 88);
    scene.add(r2);
  }
})();

staticTargets = rayWalls.concat([floorMesh]);

const BOT_SPAWNS = [[-18, -24], [0, -24], [12, -24], [-24, -2], [24, -2], [-11, -13], [6, -14], [0, -18]];
const CT_SPAWNS = [[-4, 14], [4, 14], [-9, 17], [9, 17], [-5, 20], [5, 20], [0, 19]];
const PLAYER_SPAWN = new THREE.Vector3(0, 0, 17);
