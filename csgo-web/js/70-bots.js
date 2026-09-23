/* CS:GO Web —— Bot 模型/AI/伤害击杀 */
'use strict';

/* ---------------- Bot ---------------- */
const BOT_NAMES = ['Gooseman', 'Cliffe', 'Minh', 'Ridgway', 'Wolf', 'Vitaliy', 'Brett', 'Corey', 'Gabe', 'Ido'];
const bots = [];
let botMeshes = [];
const rayGun = new THREE.Raycaster();
// 共享材质与几何体（避免每次生成 Bot 都新建 GPU 资源）
const BOT_M = {
  skin:   new THREE.MeshStandardMaterial({ color: 0xc9a07a, roughness: 0.75 }),
  shirt:  new THREE.MeshStandardMaterial({ color: 0xa87840, roughness: 0.9 }),   // T 暖沙褐
  vest:   new THREE.MeshStandardMaterial({ color: 0x5c4a2c, roughness: 0.85 }),
  pants:  new THREE.MeshStandardMaterial({ color: 0x6b5a3e, roughness: 0.9 }),
  boot:   new THREE.MeshStandardMaterial({ color: 0x2f2b24, roughness: 0.8 }),
  gun:    new THREE.MeshStandardMaterial({ color: 0x2b2b2b, roughness: 0.45, metalness: 0.6 }),
  wood:   new THREE.MeshStandardMaterial({ color: 0x6e4a28, roughness: 0.7 }),
  helmet: new THREE.MeshStandardMaterial({ color: 0x716648, roughness: 0.7, metalness: 0.2 }),
  mask:   new THREE.MeshStandardMaterial({ color: 0x2a2a2a, roughness: 0.6 }),
};
// CT 队友配色（鲜明蓝系 + 头盔亮蓝条）
const BOT_M_CT = Object.assign({}, BOT_M, {
  shirt:  new THREE.MeshStandardMaterial({ color: 0x4a6a96, roughness: 0.9 }),
  vest:   new THREE.MeshStandardMaterial({ color: 0x2e3f56, roughness: 0.85 }),
  pants:  new THREE.MeshStandardMaterial({ color: 0x3d4652, roughness: 0.9 }),
  helmet: new THREE.MeshStandardMaterial({ color: 0x33445e, roughness: 0.7, metalness: 0.2 }),
});
// 队友标识圈（脚下蓝色光环，敌人无）
const ringGeo = new THREE.RingGeometry(0.34, 0.44, 22);
const ringMatCT = new THREE.MeshBasicMaterial({ color: 0x4a90d8, transparent: true, opacity: 0.55, depthWrite: false });
const livingTs = () => bots.filter(b => !b.dead && b.team === 'T');
const livingCTs = () => bots.filter(b => !b.dead && b.team === 'CT');
/* ---------------- 真实模型：three.js Soldier.glb（带骨骼动画的蒙皮人形） ----------------
   资产来自 three.js 官方示例（mrdoob/three.js r147），本地化于 models/Soldier.glb */
let soldierProto = null;
if (THREE.GLTFLoader) {
  new THREE.GLTFLoader().load('models/Soldier.glb',
    g => { soldierProto = g; },
    undefined,
    () => { /* 加载失败则沿用程序化人形 */ });
}
function makeSoldierBot(team) {
  const model = THREE.SkeletonUtils.clone(soldierProto.scene);
  model.rotation.y = Math.PI; // 模型默认朝 -Z，转为朝 +Z
  const tint = team === 'CT' ? 0x9db8dd : 0xd8b184;
  const meshes = [];
  let handBone = null;
  model.traverse(o => {
    if (o.isBone && /RightHand$/i.test(o.name)) handBone = o;
    if (o.isMesh) {
      o.castShadow = true;
      o.frustumCulled = false; // 蒙皮网格包围盒跟随动画
      o.material = o.material.clone();
      o.material.color = new THREE.Color(tint); // 队伍色罩染
      meshes.push(o);
    }
  });
  // 右手挂枪（若有手部骨骼）
  let gun = null;
  if (handBone) {
    gun = new THREE.Group();
    const gm = new THREE.MeshPhongMaterial({ color: 0x2b2b2b, shininess: 30 });
    const gw = new THREE.MeshPhongMaterial({ color: 0x6e4a28 });
    const b1 = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.08, 0.5), gm); b1.position.z = 0.2;
    const b2 = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.03, 0.24), gm); b2.position.set(0, 0.01, 0.5);
    const b3 = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.13, 0.06), gm); b3.position.set(0, -0.1, 0.12); b3.rotation.x = 0.4;
    const b4 = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.06, 0.16), gw); b4.position.set(0, 0, -0.12);
    gun.add(b1, b2, b3, b4);
    gun.rotation.set(0, Math.PI / 2, 0);
    gun.scale.setScalar(0.9);
    handBone.add(gun);
  }
  return { model, meshes, gun };
}

/* ---------------- 人形骨骼（程序化骨骼层级 + 胶囊体四肢） ---------------- */
const HUM_G = {
  thigh: new THREE.CapsuleGeometry(0.075, 0.32, 4, 8),
  shin:  new THREE.CapsuleGeometry(0.058, 0.3, 4, 8),
  foot:  new THREE.BoxGeometry(0.11, 0.07, 0.24),
  pelvis:new THREE.BoxGeometry(0.3, 0.16, 0.19),
  chest: new THREE.CapsuleGeometry(0.16, 0.2, 4, 8),
  vest:  new THREE.BoxGeometry(0.34, 0.28, 0.23),
  head:  new THREE.SphereGeometry(0.11, 12, 10),
  helmet:new THREE.SphereGeometry(0.128, 12, 8, 0, Math.PI * 2, 0, Math.PI * 0.55),
  mask:  new THREE.BoxGeometry(0.16, 0.05, 0.02),
  uarm:  new THREE.CapsuleGeometry(0.05, 0.2, 4, 8),
  farm:  new THREE.CapsuleGeometry(0.044, 0.17, 4, 8),
  hand:  new THREE.BoxGeometry(0.07, 0.08, 0.1),
  pack:  new THREE.BoxGeometry(0.26, 0.28, 0.12),
  gBody: new THREE.BoxGeometry(0.05, 0.08, 0.5),
  gBarrel: new THREE.BoxGeometry(0.028, 0.028, 0.3),
  gMag: new THREE.BoxGeometry(0.045, 0.14, 0.06),
  gStock: new THREE.BoxGeometry(0.045, 0.06, 0.18),
};
function buildHumanoid(BM) {
  const mk = (geo, mat, part) => {
    const m = new THREE.Mesh(geo, mat);
    m.castShadow = true;
    m.userData.part = part;
    return m;
  };
  const J = (x, y, z, parent) => {
    const g = new THREE.Group();
    g.position.set(x, y, z);
    parent.add(g);
    return g;
  };

  const root = new THREE.Group();
  // 髋 → 脊柱 → 胸 → 颈 → 头
  const hips = J(0, 0.95, 0, root);
  hips.add(mk(HUM_G.pelvis, BM.pants, 'body'));
  const spine = J(0, 0.1, 0, hips);
  const chest = J(0, 0.16, 0, spine);
  const chestMesh = mk(HUM_G.chest, BM.shirt, 'body');
  chestMesh.position.y = 0.1; chest.add(chestMesh);
  const vest = mk(HUM_G.vest, BM.vest, 'body');
  vest.position.y = 0.1; chest.add(vest);
  const pack = mk(HUM_G.pack, BM.vest, 'body');
  pack.position.set(0, 0.1, -0.17); chest.add(pack);
  const neck = J(0, 0.32, 0, chest);
  const head = J(0, 0.05, 0, neck);
  const headMesh = mk(HUM_G.head, BM.skin, 'head');
  headMesh.position.y = 0.06; head.add(headMesh);
  const helmet = mk(HUM_G.helmet, BM.helmet, 'head');
  helmet.position.y = 0.08; head.add(helmet);
  const mask = mk(HUM_G.mask, BM.mask, 'head');
  mask.position.set(0, 0.04, 0.1); head.add(mask);

  // 腿：髋 → 膝 → 踝
  function buildLeg(side) {
    const thigh = J(0.1 * side, -0.06, 0, hips);
    const tm = mk(HUM_G.thigh, BM.pants, 'legs');
    tm.position.y = -0.22; thigh.add(tm);
    const shin = J(0, -0.44, 0, thigh);
    const sm = mk(HUM_G.shin, BM.pants, 'legs');
    sm.position.y = -0.19; shin.add(sm);
    const ankle = J(0, -0.40, 0, shin);
    const fm = mk(HUM_G.foot, BM.boot, 'legs');
    fm.position.set(0, -0.015, 0.05); ankle.add(fm);
    return { thigh, shin, ankle };
  }
  const legL = buildLeg(-1), legR = buildLeg(1);

  // 臂：肩 → 肘 → 腕（持枪姿势）
  function buildArm(side) {
    const shoulder = J(0.2 * side, 0.24, 0, chest);
    const um = mk(HUM_G.uarm, BM.shirt, 'body');
    um.position.y = -0.13; shoulder.add(um);
    const elbow = J(0, -0.26, 0, shoulder);
    const fm = mk(HUM_G.farm, BM.shirt, 'body');
    fm.position.y = -0.11; elbow.add(fm);
    const hand = J(0, -0.24, 0, elbow);
    hand.add(mk(HUM_G.hand, BM.skin, 'body'));
    return { shoulder, elbow, hand };
  }
  const armL = buildArm(-1), armR = buildArm(1);
  // 持枪姿态
  armR.shoulder.rotation.set(-1.05, -0.25, -0.2);
  armR.elbow.rotation.x = -0.55;
  armL.shoulder.rotation.set(-1.15, 0.45, 0.25);
  armL.elbow.rotation.x = -0.8;

  // 步枪挂在胸口（随脊柱俯仰）
  const gun = new THREE.Group();
  gun.position.set(0.13, 0.16, 0.3);
  chest.add(gun);
  const gb = (geo, x, y, z, mat) => {
    const b = new THREE.Mesh(geo, mat);
    b.castShadow = true;
    b.userData.part = 'body';
    b.position.set(x, y, z);
    gun.add(b);
    return b;
  };
  gb(HUM_G.gBody, 0, 0, 0.12, BM.gun);
  gb(HUM_G.gBarrel, 0, 0.01, 0.5, BM.gun);
  gb(HUM_G.gMag, 0, -0.1, 0.05, BM.gun).rotation.x = 0.4;
  gb(HUM_G.gStock, 0, -0.005, -0.2, BM.wood);

  const parts = [];
  root.traverse(o => { if (o.isMesh) parts.push(o); });
  // 队友脚下蓝色标识圈
  if (BM === BOT_M_CT) {
    const ring = new THREE.Mesh(ringGeo, ringMatCT);
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.03;
    root.add(ring);
  }
  return { root, hips, spine, chest, neck, head, legL, legR, armL, armR, gun, parts };
}

function spawnBot(sp, t, team) {
  // 优先使用 Soldier.glb 真实模型（带骨骼动画）
  if (soldierProto) {
    const g = new THREE.Group();
    g.position.set(sp[0], 0, sp[1]);
    g.rotation.y = team === 'T' ? 0 : Math.PI;
    const s = makeSoldierBot(team);
    g.add(s.model);
    if (team === 'CT') {
      const ring = new THREE.Mesh(ringGeo, ringMatCT);
      ring.rotation.x = -Math.PI / 2;
      ring.position.y = 0.03;
      g.add(ring);
    }
    scene.add(g);
    const mixer = new THREE.AnimationMixer(s.model);
    const act = (n, fallback) => {
      const c = soldierProto.animations.find(a => a.name === n) || soldierProto.animations[fallback];
      return c ? mixer.clipAction(c) : null;
    };
    const bot = {
      name: BOT_NAMES[Math.floor(Math.random() * BOT_NAMES.length)],
      team,
      hp: 100, dead: false, deadT: 0, removed: false,
      group: g, rig: null, gun: s.gun, rigKick: 0,
      mixer, actIdle: act('Idle', 0), actWalk: act('Walk', 3), actRun: act('Run', 1), curAct: null,
      walkPhase: Math.random() * 6,
      nextShot: t + rand(1.5, 3), burst: 0,
      strafe: 1, strafeT: 0, detour: 0, detourT: 0,
    };
    for (const m of s.meshes) m.userData = { bot, part: 'body' };
    bots.push(bot);
    if (team === 'T') botMeshes = botMeshes.concat(s.meshes);
    return bot;
  }
  const BM = team === 'CT' ? BOT_M_CT : BOT_M;
  const rig = buildHumanoid(BM);
  const g = rig.root;
  g.position.set(sp[0], 0, sp[1]);
  g.rotation.y = team === 'T' ? 0 : Math.PI;
  scene.add(g);
  const bot = {
    name: BOT_NAMES[Math.floor(Math.random() * BOT_NAMES.length)],
    team,
    hp: 100, dead: false, deadT: 0, removed: false,
    group: g, rig, gun: rig.gun, rigKick: 0,
    walkPhase: Math.random() * 6,
    nextShot: t + rand(1.5, 3), burst: 0,
    strafe: 1, strafeT: 0, detour: 0, detourT: 0,
  };
  for (const m of rig.parts) m.userData = { bot, part: m.userData.part };
  bots.push(bot);
  if (team === 'T') botMeshes = botMeshes.concat(rig.parts); // 玩家子弹只判定敌人，无友伤
  return bot;
}

function moveBotAxis(b, axis, delta) {
  if (!delta) return;
  const p = b.group.position;
  p[axis] += delta;
  const r = 0.32, h = 1.8;
  for (const s of solids) {
    if (p.x + r > s.min.x && p.x - r < s.max.x &&
        p.y + h > s.min.y && p.y < s.max.y &&
        p.z + r > s.min.z && p.z - r < s.max.z) {
      // 低矮台阶不阻挡（由地面跟随处理登步）
      if (axis !== 'y' && s.max.y - p.y <= 0.4 && s.max.y > p.y) continue;
      if (axis === 'x') p.x = delta > 0 ? s.min.x - r : s.max.x + r;
      else p.z = delta > 0 ? s.min.z - r : s.max.z + r;
    }
  }
}
// 某位置的可站立地面高度（石板街/台阶/高台顶）
function groundHeightAt(x, z) {
  let h = 0;
  for (const s of solids) {
    if (x > s.min.x && x < s.max.x && z > s.min.z && z < s.max.z && s.max.y <= 1.35 && s.max.y > h) h = s.max.y;
  }
  return h;
}

// 选目标：最近的敌方单位（T 可选玩家和 CT，CT 只选 T）
function acquireTarget(b) {
  const p = b.group.position;
  let best = null, bd = Infinity;
  const consider = (pos, isPlayer, bot) => {
    const d = Math.hypot(pos.x - p.x, pos.z - p.z);
    if (d < bd) { bd = d; best = { pos, isPlayer, bot }; }
  };
  if (b.team === 'T' && player.alive) consider(player.pos, true, null);
  for (const o of bots) if (!o.dead && o.team !== b.team) consider(o.group.position, false, o);
  return best;
}

function botShoot(b, target, dist) {
  b.group.updateMatrixWorld(true);
  b.rigKick = 1;
  let mzl;
  if (b.gun && b.gun.isGroup && b.gun.parent) {
    mzl = b.gun.localToWorld(new THREE.Vector3(0, 0.01, 0.6));
  } else {
    const ry = b.group.rotation.y;
    const p0 = b.group.position;
    mzl = new THREE.Vector3(p0.x + Math.sin(ry) * 0.5, p0.y + 1.4, p0.z + Math.cos(ry) * 0.5);
  }
  addSpark(mzl, 0xffd080, 0.45);
  botFlashLight.position.copy(mzl); // Bot 枪口共享灯
  botFlashLight.intensity = 1.6;
  shotSound('ak', mzl);
  const moving = target.isPlayer ? Math.hypot(player.vel.x, player.vel.z) > 2 : true;
  let p = 0.45 - dist * 0.016 - (moving ? 0.12 : 0) + (target.isPlayer && player.crouch ? -0.05 : 0);
  p = clamp(p, 0.04, 0.55);
  const hit = Math.random() < p;
  // 曳光弹：命中的直指目标，脱靶的略过目标旁
  const tEnd = target.isPlayer
    ? new THREE.Vector3(player.pos.x + (hit ? 0 : rand(-1.6, 1.6)), player.pos.y + eyeH() + (hit ? 0 : rand(-0.6, 0.6)), player.pos.z + (hit ? 0 : rand(-1.6, 1.6)))
    : target.bot.group.position.clone().setY(1.2 + (hit ? 0 : rand(-0.5, 0.8)));
  addTracer(mzl, tEnd);
  if (hit) {
    if (target.isPlayer) damagePlayer(rand(6, 12), b);
    else damageBotDirect(target.bot, rand(18, 30), b);
  } else if (target.isPlayer && dist < 26 && Math.random() < 0.5) {
    whizSound(panFor(mzl).pan * -0.6); // 子弹掠耳
  }
}

function updateBots(dt, t) {
  for (const b of bots) {
    if (b.dead) {
      if (!b.removed) {
        b.group.rotation.z = Math.min(Math.PI / 2, b.group.rotation.z + dt * 5);
        // 关节松垮（软倒地，程序化人形专用；Soldier 冻结动画姿势倒下）
        if (b.rig) {
          const R0 = b.rig, k = Math.min(1, dt * 4);
          R0.armL.shoulder.rotation.x += (-0.2 - R0.armL.shoulder.rotation.x) * k;
          R0.armR.shoulder.rotation.x += (-0.2 - R0.armR.shoulder.rotation.x) * k;
          R0.legL.thigh.rotation.x += (0.5 - R0.legL.thigh.rotation.x) * k;
          R0.legR.thigh.rotation.x += (0.3 - R0.legR.thigh.rotation.x) * k;
          R0.legL.shin.rotation.x += (0.7 - R0.legL.shin.rotation.x) * k;
          R0.legR.shin.rotation.x += (0.5 - R0.legR.shin.rotation.x) * k;
          R0.head.rotation.x += (0.35 - R0.head.rotation.x) * k;
        }
        b.group.position.x += (b.deadVX || 0) * dt;
        b.group.position.z += (b.deadVZ || 0) * dt;
        if (b.deadVX) { b.deadVX *= Math.max(0, 1 - dt * 4); b.deadVZ *= Math.max(0, 1 - dt * 4); }
        if (t > b.deadT + 0.6) b.group.position.y -= dt * 1.5;
        if (t > b.deadT + 1.8 || b.group.position.y < -2) { scene.remove(b.group); b.removed = true; }
      }
      continue;
    }
    if (roundState !== 'live') { b.group.rotation.y += dt * 0.5; continue; }
    if (botsFrozen) continue;   // 控制台冻结
    if (t < (b.flinchT || 0)) continue;   // 受击僵直
    const target = acquireTarget(b);
    if (!target) continue;
    const p = b.group.position;
    const tpos = target.pos;
    const dx = tpos.x - p.x, dz = tpos.z - p.z;
    const dist = Math.hypot(dx, dz);
    // 转向插值，避免瞬间掉头
    const ty = Math.atan2(dx, dz);
    let dyaw = Math.atan2(Math.sin(ty - b.group.rotation.y), Math.cos(ty - b.group.rotation.y));
    b.group.rotation.y += dyaw * Math.min(1, dt * 8);

    // 视线判定
    const eye = new THREE.Vector3(p.x, 1.6, p.z);
    const aimY = target.isPlayer ? player.pos.y + eyeH() : tpos.y + 1.5;
    const dirT = new THREE.Vector3(tpos.x - p.x, aimY - 1.6, tpos.z - p.z);
    const d3 = dirT.length(); dirT.normalize();
    rayGun.set(eye, dirT); rayGun.far = d3;
    const hits = rayGun.intersectObjects(rayWalls, false);
    const blocked = hits.length > 0 && hits[0].distance < d3 - 0.25;

    // 移动：近距离侧向拉扯，远距离逼近（受击减速）
    const tagSlow = t < (b.tagT || 0) ? 0.5 : 1;
    let ang = Math.atan2(dx, dz);
    let mv = 3.0 * tagSlow;
    if (!blocked && dist < 14) {
      if (t > b.strafeT) { b.strafe = Math.random() < 0.5 ? -1 : 1; b.strafeT = t + rand(0.7, 1.6); }
      ang += b.strafe * Math.PI / 2;
      mv = 2.0 * tagSlow;
    }
    if (b.detourT > t) ang += b.detour;
    const before = p.clone();
    moveBotAxis(b, 'x', Math.sin(ang) * mv * dt);
    moveBotAxis(b, 'z', Math.cos(ang) * mv * dt);
    if (before.distanceTo(p) < mv * dt * 0.35 && b.detourT < t) {
      b.detour = (Math.random() < 0.5 ? -1 : 1) * Math.PI / 2;
      b.detourT = t + 0.7;
    }

    // 动画：Soldier 蒙皮混合树 / 程序化人形回退
    const moved = before.distanceTo(p);
    const walkAmt = Math.min(moved / Math.max(dt, 1e-6) / 3, 1);
    b.walkPhase += dt * (4 + walkAmt * 6);
    // 地面跟随：石板街/台阶上不悬空不下陷
    const gy = groundHeightAt(p.x, p.z);
    b.group.position.y += (gy - b.group.position.y) * Math.min(1, dt * 10);
    const bstep = Math.floor(b.walkPhase / Math.PI);
    if (bstep !== (b._step || 0) && walkAmt > 0.3) { b._step = bstep; footstep(0.5, p); }
    if (b.mixer) {
      // 真实骨骼动画：Idle ↔ Walk ↔ Run 按移速交叉淡入
      const target = walkAmt > 0.72 ? b.actRun : walkAmt > 0.22 ? b.actWalk : b.actIdle;
      if (target && b.curAct !== target) {
        if (b.curAct) b.curAct.fadeOut(0.18);
        target.reset().setEffectiveWeight(1).fadeIn(0.18).play();
        b.curAct = target;
      }
      if (target) target.setEffectiveTimeScale(0.8 + walkAmt * 0.55);
      b.mixer.update(dt);
    } else if (b.rig) {
      const ph2 = b.walkPhase, sw2 = Math.sin(ph2), R = b.rig;
      const aimPitch = Math.atan2(aimY - 1.55, Math.max(dist, 0.5));
      R.legL.thigh.rotation.x = -sw2 * 0.6 * walkAmt;
      R.legR.thigh.rotation.x = sw2 * 0.6 * walkAmt;
      R.legL.shin.rotation.x = Math.max(0, Math.sin(ph2 + 1.1)) * 0.95 * walkAmt;
      R.legR.shin.rotation.x = Math.max(0, Math.sin(ph2 + 1.1 + Math.PI)) * 0.95 * walkAmt;
      R.legL.ankle.rotation.x = -(R.legL.thigh.rotation.x + R.legL.shin.rotation.x) * 0.35;
      R.legR.ankle.rotation.x = -(R.legR.thigh.rotation.x + R.legR.shin.rotation.x) * 0.35;
      R.hips.position.y = 0.95 + Math.abs(Math.cos(ph2)) * 0.045 * walkAmt;
      R.hips.position.x = sw2 * 0.025 * walkAmt;
      R.spine.rotation.x = 0.06 + 0.16 * walkAmt + aimPitch * 0.45;
      R.chest.rotation.y = -sw2 * 0.12 * walkAmt;
      R.chest.rotation.x = Math.sin(t * 1.4) * 0.02 + (b.rigKick || 0) * 0.14;
      R.head.rotation.x = aimPitch * 0.45;
      b.rigKick = Math.max(0, (b.rigKick || 0) - dt * 6);
    }

    // 射击（点射节奏）
    if (!blocked && dist < 30 && t >= b.nextShot && t >= (b.blindT || 0)) {
      if (b.burst > 0) { b.burst--; b.nextShot = t + 0.14; }
      else { b.burst = Math.floor(rand(1, 4)); b.nextShot = t + rand(0.9, 2.0); }
      botShoot(b, target, dist);
    }
  }

  // Bot 相互分离，避免堆叠穿模
  for (let i = 0; i < bots.length; i++) {
    for (let j = i + 1; j < bots.length; j++) {
      const a = bots[i], c = bots[j];
      if (a.dead || c.dead) continue;
      const ddx = c.group.position.x - a.group.position.x;
      const ddz = c.group.position.z - a.group.position.z;
      const dd = Math.hypot(ddx, ddz);
      if (dd > 0.001 && dd < 0.7) {
        const push = (0.7 - dd) / 2;
        const nx = ddx / dd, nz = ddz / dd;
        a.group.position.x -= nx * push; a.group.position.z -= nz * push;
        c.group.position.x += nx * push; c.group.position.z += nz * push;
      }
    }
  }
}

/* ---------------- 伤害与击杀 ---------------- */
function vigFlash() {
  const v = $('vig');
  v.style.transition = 'none'; v.style.opacity = 0.55;
  requestAnimationFrame(() => { v.style.transition = 'opacity .5s'; v.style.opacity = 0; });
}
function showHit(head) {
  xh.hitT = now();
  xh.hitHead = head;
}
function damagePlayer(dmg, fromBot, pen) {
  if (!player.alive || roundState !== 'live' || player.god) return;
  if (player.armor > 0) {
    // CS 穿甲模型：护甲按武器穿透率放行伤害
    const p = pen || 0.775; // Bot 持 AK
    const through = dmg * p;
    player.armor = Math.max(0, player.armor - (dmg - through) * 0.5);
    dmg = through;
    armorSound();
  }
  player.hp -= dmg;
  vigFlash();
  punch.vx += player.armor > 0 ? 0.25 : 0.5; // 受击视角上抬（有甲减半）
  trauma = Math.min(1, trauma + 0.35);
  fovKick = Math.min(fovKick + 0.4, 1.6);
  if (fromBot) { // 受击方向指示弧
    const dx = fromBot.group.position.x - player.pos.x;
    const dz = fromBot.group.position.z - player.pos.z;
    const rel = Math.atan2(dx, dz) - (player.yaw + Math.PI);
    const el = $('dmgarc');
    el.style.transform = `translate(-50%,-50%) rotate(${-rel}rad)`;
    el.style.opacity = 1;
    clearTimeout(el._t);
    el._t = setTimeout(() => { el.style.opacity = 0; }, 700);
  }
  if (player.hp <= 0) playerDie(fromBot);
}
function playerDie(fromBot) {
  player.hp = 0; player.alive = false; player.deadAt = now();
  aiming = false; awpStage = 0;
  if (buyOpen) closeBuy();
  if (vm) vm.visible = false;
  $('dead').textContent = livingCTs().length > 0 ? '你已阵亡 · 队友战斗中' : '你已阵亡';
  $('dead').style.display = 'block';
  // CS2 式死亡报告
  if (fromBot) {
    const dr = $('deadreport');
    dr.innerHTML = `<span class="dr-k">${fromBot.name}</span> ${iconImg('ak47')} 击杀了你 ｜ 对方剩余 HP <b>${Math.max(1, Math.ceil(fromBot.hp))}</b><br>本回合你造成 <b>${Math.round(player.dmgDealt)}</b> 伤害 · 击杀 ${player.kills - player.roundKillBase}`;
    dr.style.display = 'block';
  }
  feed(`${fromBot ? fromBot.name : '敌人'} 击杀 你`, false);
}
function hitBot(b, dmg, head, point, dir) {
  if (b.dead) return;
  addBlood(point, dir || new THREE.Vector3(0, 0, 1));
  const distPB = Math.hypot(b.group.position.x - player.pos.x, b.group.position.z - player.pos.z);
  const dealt = dmg * Math.pow(curWeapon().def.fall, distPB / 10);
  b.hp -= dealt;
  player.dmgDealt += Math.max(0, Math.min(dealt, b.hp + dealt)); // 统计实际伤害
  b.flinchT = now() + (head ? 0.2 : 0.12);   // 受击僵直
  b.tagT = now() + 0.5;                      // 移动减速（tagging）
  showHit(head);
  hitSound(head);
  if (b.hp <= 0) killBot(b, head, null, dir);
}
function damageBotDirect(b, dmg, killer) {
  if (b.dead) return;
  const tp = b.group.position;
  addBlood(new THREE.Vector3(tp.x, tp.y + 1.2, tp.z), new THREE.Vector3(rand(-1, 1), 0.5, rand(-1, 1)));
  b.hp -= dmg;
  b.flinchT = now() + 0.12;
  b.tagT = now() + 0.4;
  if (b.hp <= 0) killBot(b, false, killer, null);
}
function killBot(b, head, killer, dir) {
  b.dead = true; b.deadT = now();
  botMeshes = botMeshes.filter(m => m.userData.bot !== b);
  // 死亡带动量滑倒 + 掉落武器 + 血泊
  const p = b.group.position;
  const from = killer ? killer.group.position : player.pos;
  const dv = dir || new THREE.Vector3(p.x - from.x, 0, p.z - from.z).normalize();
  b.deadVX = dv.x * 1.6; b.deadVZ = dv.z * 1.6;
  if (Math.random() < 0.55) dropGun(p, 'ak47');
  const pool = new THREE.Sprite(new THREE.SpriteMaterial({
    map: glowTex, color: 0x4d0a08, transparent: true, opacity: 0.75, depthWrite: false
  }));
  pool.scale.set(rand(0.5, 0.85), rand(0.35, 0.5), 1);
  pool.position.set(p.x, groundHeightAt(p.x, p.z) + 0.018, p.z);
  scene.add(pool);
  decals.push(pool);
  if (decals.length > 40) { const old2 = decals.shift(); scene.remove(old2); old2.material.dispose(); }
  addDecal(new THREE.Vector3(p.x, 0.012, p.z), new THREE.Vector3(0, 1, 0), 0x4a0d0d); // 地面血渍
  if (!killer) {
    addMoney(curWeapon().def.reward); player.kills++;
    killSound();
    xh.killT = now();
    feed(`你 ${iconImg(curWeapon().id, 'fic')} ${b.name}${head ? ' · 爆头' : ''}`, head);
  } else {
    killer.kills = (killer.kills || 0) + 1;
    feed(`${killer.name} ${iconImg('ak47', 'fic')} ${b.name}`, killer.team === 'CT');
  }
  checkRoundEnd();
}
function checkRoundEnd() {
  if (roundState !== 'live') return;
  if (livingTs().length === 0) endRound('ct');
  else if (livingCTs().length === 0 && !player.alive) endRound('t');
}
