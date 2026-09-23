/* CS:GO Web —— 地图几何与布局 */
'use strict';

/* ---------------- 地图 ---------------- */
const matCache = {};
function matFor(kind, w, h, d) {
  const rx = Math.max(1, Math.round(Math.max(w, d) / 2.2));
  const ry = Math.max(1, Math.round(h / 2.2));
  const k = kind + '_' + rx + 'x' + ry;
  if (!matCache[k]) {
    const src = {
      wall: wallCanvas, wall2: wallCanvas, crate: crateCanvas, plat: platCanvas,
      sand: platCanvas, barrel: crateCanvas, trim: platCanvas, plaster: plasterCanvas, roof: roofCanvas,
      cobble: cobbleCanvas, cloth: clothCanvas, door: doorCanvas, window: windowCanvas,
    }[kind];
    const tint = { wall2: 0xb0a184, sand: 0xb3a37e, barrel: 0xa06a42, trim: 0x6e5c40 }[kind] || 0xffffff;
    const metal = kind === 'barrel';
    const mat = new THREE.MeshStandardMaterial({
      map: toTex(src, rx, ry, true),
      normalMap: toTex(normalFromCanvas(src), rx, ry),
      normalScale: new THREE.Vector2(1.1, 1.1),
      roughnessMap: toTex(src, rx, ry),
      roughness: metal ? 0.5 : 0.96,
      metalness: metal ? 0.55 : 0.05,
      envMapIntensity: 0.32,
      color: tint,
    });
    if (kind === 'cloth') mat.side = THREE.DoubleSide;
    matCache[k] = mat;
  }
  return matCache[k];
}
const MAT = {
  floor: new THREE.MeshStandardMaterial({
    map: toTex(floorCanvas, 18, 18, true),
    normalMap: toTex(normalFromCanvas(floorCanvas), 18, 18),
    normalScale: new THREE.Vector2(0.7, 0.7),
    roughness: 0.92, metalness: 0.04, envMapIntensity: 0.4,
  }),
};
const solids = [];    // 碰撞体 {min,max}
const rayWalls = [];  // 视线遮挡网格
let staticTargets = [];

function addBox(x, y, z, w, h, d, kind) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), matFor(kind, w, h, d));
  m.position.set(x, y + h / 2, z);
  m.castShadow = m.receiveShadow = true;
  scene.add(m);
  solids.push({
    min: new THREE.Vector3(x - w / 2, y, z - d / 2),
    max: new THREE.Vector3(x + w / 2, y + h, z + d / 2)
  });
  rayWalls.push(m);
  // dust 式墙基防潮座：立地的墙体自动加一圈深色基座
  if ((kind === 'wall' || kind === 'wall2' || kind === 'plaster') && y === 0) {
    const trim = new THREE.Mesh(new THREE.BoxGeometry(w + 0.05, 0.5, d + 0.05), matFor('trim', 1, 1, 1));
    trim.position.set(x, 0.25, z);
    trim.castShadow = trim.receiveShadow = true;
    scene.add(trim);
    rayWalls.push(trim);
  }
  return m;
}
function addCyl(x, z, r, h) { // 油桶（圆柱，AABB 近似碰撞）
  const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 12), matFor('barrel', r * 2, h, r * 2));
  m.position.set(x, h / 2, z);
  m.castShadow = m.receiveShadow = true;
  m.userData.kind = 'barrel';
  scene.add(m);
  solids.push({ min: new THREE.Vector3(x - r * 0.8, 0, z - r * 0.8), max: new THREE.Vector3(x + r * 0.8, h, z + r * 0.8) });
  rayWalls.push(m);
  return m;
}
// 场景暖光灯（灯柱 + 发光灯头 + 点光源 + 光晕）—— 调用放在 glowTex 定义之后
const lampPoleMat = new THREE.MeshStandardMaterial({ color: 0x2a2a28, roughness: 0.7, metalness: 0.4 });
function addLamp(x, z, y, intensity, dist) {
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.09, y, 8), lampPoleMat);
  pole.position.set(x, y / 2, z); pole.castShadow = true;
  scene.add(pole);
  const head = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.12, 0.32),
    new THREE.MeshStandardMaterial({ color: 0x1c1c1c, emissive: 0xffc98a, emissiveIntensity: 2.2, roughness: 0.5 }));
  head.position.set(x, y, z);
  scene.add(head);
  const L = new THREE.PointLight(0xffc98a, intensity, dist, 2);
  L.position.set(x, y - 0.15, z);
  scene.add(L);
  const halo = new THREE.Sprite(new THREE.SpriteMaterial({
    map: glowTex, color: 0xffc98a, transparent: true, opacity: 0.32,
    blending: THREE.AdditiveBlending, depthWrite: false
  }));
  halo.scale.setScalar(1.3);
  halo.position.set(x, y, z);
  scene.add(halo);
}

/* —— 小镇建筑与道具 —— */
function facePanel(x, y, z, w, h, axis, off, kind) { // 贴墙片（门/窗）
  const m = new THREE.Mesh(new THREE.BoxGeometry(axis === 'z' ? w : 0.12, h, axis === 'z' ? 0.12 : w), matFor(kind, 1, 1, 1));
  m.position.set(x + (axis === 'x' ? off : 0), y, z + (axis === 'z' ? off : 0));
  m.castShadow = true;
  scene.add(m);
  rayWalls.push(m);
  return m;
}
function addBuilding(x, z, w, d, h, door) { // 二层小楼：主体+出檐+女儿墙+门窗+遮篷
  addBox(x, 0, z, w, h, d, 'plaster');
  addBox(x, h, z, w + 0.6, 0.22, d + 0.6, 'roof');
  addBox(x, h + 0.22, z - d / 2, w, 0.45, 0.22, 'plaster');
  addBox(x, h + 0.22, z + d / 2, w, 0.45, 0.22, 'plaster');
  addBox(x - w / 2, h + 0.22, z, 0.22, 0.45, d, 'plaster');
  addBox(x + w / 2, h + 0.22, z, 0.22, 0.45, d, 'plaster');
  const dd = 1.7, dh = 2.6;
  if (door === 'E') facePanel(x + w / 2, dh / 2, z, dd, dh, 'x', 0.08, 'door');
  if (door === 'W') facePanel(x - w / 2, dh / 2, z, dd, dh, 'x', -0.08, 'door');
  if (door === 'S') facePanel(x, dh / 2, z + d / 2, dd, dh, 'z', 0.08, 'door');
  if (door === 'N') facePanel(x, dh / 2, z - d / 2, dd, dh, 'z', -0.08, 'door');
  for (const sx of [-1, 1]) {
    for (const wy of [2.2, 4.6]) {
      if (door && sx === (door === 'E' ? 1 : -1) && wy < 3) continue; // 门位不叠窗
      facePanel(x + sx * w / 2, wy, z + d * 0.22, 1.3, 1.3, 'x', sx * 0.08, 'window');
      facePanel(x + sx * w / 2, wy, z - d * 0.22, 1.3, 1.3, 'x', sx * 0.08, 'window');
    }
  }
  const awn = new THREE.Mesh(new THREE.BoxGeometry(1.1, 0.06, 2.6), matFor('cloth', 1, 1, 1));
  if (door === 'E') { awn.position.set(x + w / 2 + 0.55, dh + 0.35, z); awn.rotation.z = 0.32; }
  else if (door === 'W') { awn.position.set(x - w / 2 - 0.55, dh + 0.35, z); awn.rotation.z = -0.32; }
  awn.castShadow = true;
  scene.add(awn);
}
function addStall(x, z) { // 巴扎摊位（柜台碰撞 + 布篷）
  addBox(x, 0, z, 1.9, 0.85, 0.9, 'crate');
  const wood = matFor('crate', 2, 2, 2);
  for (const [px, pz] of [[-0.95, -0.45], [0.95, -0.45], [-0.95, 0.45], [0.95, 0.45]]) {
    const post = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 2.1, 6), wood);
    post.position.set(x + px, 1.05, z + pz);
    post.castShadow = true;
    scene.add(post);
  }
  const top = new THREE.Mesh(new THREE.BoxGeometry(2.3, 0.06, 1.4), matFor('cloth', 1, 1, 1));
  top.position.set(x, 2.1, z);
  top.rotation.x = 0.16;
  top.castShadow = true;
  scene.add(top);
  addBox(x + 0.35, 0.85, z, 0.7, 0.5, 0.6, 'crate');
}
function addCar(x, z, color) { // 报废轿车（掩体，可跳上车顶）
  const M = new THREE.MeshStandardMaterial({ color, roughness: 0.4, metalness: 0.6, envMapIntensity: 0.7 });
  const glass = new THREE.MeshStandardMaterial({ color: 0x1a222c, roughness: 0.15, metalness: 0.4 });
  const mk = (w, h, d, px, py, pz, mat) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
    m.position.set(x + px, py, z + pz);
    m.castShadow = m.receiveShadow = true;
    scene.add(m);
    rayWalls.push(m);
    solids.push({ min: new THREE.Vector3(x + px - w / 2, py - h / 2, z + pz - d / 2), max: new THREE.Vector3(x + px + w / 2, py + h / 2, z + pz + d / 2) });
    return m;
  };
  mk(4.2, 0.72, 1.9, 0, 0.72, 0, M);        // 车身
  mk(2.2, 0.66, 1.7, -0.25, 1.38, 0, glass); // 座舱
  const wheel = new THREE.MeshStandardMaterial({ color: 0x181818, roughness: 0.9 });
  for (const [wx, wz] of [[-1.4, 0.95], [1.4, 0.95], [-1.4, -0.95], [1.4, -0.95]]) {
    const wm = new THREE.Mesh(new THREE.CylinderGeometry(0.36, 0.36, 0.26, 10), wheel);
    wm.rotation.x = Math.PI / 2;
    wm.position.set(x + wx, 0.36, z + wz);
    wm.castShadow = true;
    scene.add(wm);
  }
}
function addRubble(x, z) { // 瓦砾堆（矮掩体）
  for (let i = 0; i < 6; i++) {
    const s = rand(0.25, 0.55);
    const m = new THREE.Mesh(new THREE.BoxGeometry(s, s * rand(0.5, 0.9), s), matFor('plat', 1, 1, 1));
    m.position.set(x + rand(-0.8, 0.8), s * 0.3, z + rand(-0.8, 0.8));
    m.rotation.set(rand(-0.4, 0.4), rand(0, 3), rand(-0.4, 0.4));
    m.castShadow = m.receiveShadow = true;
    scene.add(m);
    rayWalls.push(m);
  }
  solids.push({ min: new THREE.Vector3(x - 1, 0, z - 1), max: new THREE.Vector3(x + 1, 0.7, z + 1) });
}
function addPole(x, z, h) { // 电线杆
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.09, h, 8), matFor('crate', 1, 1, 1));
  pole.position.set(x, h / 2, z);
  pole.castShadow = true;
  scene.add(pole);
  solids.push({ min: new THREE.Vector3(x - 0.12, 0, z - 0.12), max: new THREE.Vector3(x + 0.12, h, z + 0.12) });
  rayWalls.push(pole);
  const arm = new THREE.Mesh(new THREE.BoxGeometry(1.1, 0.08, 0.08), matFor('crate', 1, 1, 1));
  arm.position.set(x, h - 0.25, z);
  scene.add(arm);
}
function addWire(a, b) { // 下垂电线
  const mid = a.clone().lerp(b, 0.5); mid.y -= 0.45;
  const g = new THREE.BufferGeometry().setFromPoints([a, mid, b]);
  scene.add(new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0x1a1a1a })));
}
