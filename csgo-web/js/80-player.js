/* CS:GO Web —— 玩家移动/碰撞/镜头组 */
'use strict';

/* ---------------- 玩家移动与碰撞 ---------------- */
const keys = {};
function moveAxisP(axis, delta) {
  if (!delta) return;
  const p = player.pos;
  p[axis] += delta;
  const r = 0.35, h = playerHeight();
  for (const s of solids) {
    if (p.x + r > s.min.x && p.x - r < s.max.x &&
        p.y + h > s.min.y && p.y < s.max.y &&
        p.z + r > s.min.z && p.z - r < s.max.z) {
      // 台阶自动登步（≤0.34m 且在地面）
      if (axis !== 'y' && player.grounded) {
        const step = s.max.y - p.y;
        if (step > 0 && step <= 0.34) { p.y = s.max.y + 0.002; continue; }
      }
      if (axis === 'x') { p.x = delta > 0 ? s.min.x - r : s.max.x + r; player.vel.x = 0; }
      else if (axis === 'z') { p.z = delta > 0 ? s.min.z - r : s.max.z + r; player.vel.z = 0; }
      else {
        if (delta > 0) p.y = s.min.y - h;
        else { p.y = s.max.y; player.grounded = true; }
        player.vel.y = 0;
      }
    }
  }
}
function updatePlayer(dt) {
  player.crouch = !!(keys['ControlLeft'] || keys['ControlRight']);
  player.walk = !!(keys['ShiftLeft'] || keys['ShiftRight']);
  let f = 0, s = 0;
  if (player.alive) {
    if (keys['KeyW']) f += 1;
    if (keys['KeyS']) f -= 1;
    if (keys['KeyD']) s += 1;
    if (keys['KeyA']) s -= 1;
  }
  const maxSp = (player.crouch ? 2.2 : player.walk ? 2.7 : 5.4) * curWeapon().def.mv * (aiming ? (curWeapon().def.scope ? 0.4 : 0.65) : 1);

  // noclip：穿墙飞行
  if (player.noclip) {
    const d = new THREE.Vector3(); camera.getWorldDirection(d);
    const rt = new THREE.Vector3(Math.cos(player.yaw), 0, -Math.sin(player.yaw));
    const v = new THREE.Vector3();
    if (keys['KeyW']) v.add(d);
    if (keys['KeyS']) v.sub(d);
    if (keys['KeyD']) v.add(rt);
    if (keys['KeyA']) v.sub(rt);
    if (keys['Space']) v.y += 1;
    if (keys['ControlLeft'] || keys['ControlRight']) v.y -= 1;
    if (v.lengthSq() > 0) v.normalize().multiplyScalar(14);
    player.pos.addScaledVector(v, dt);
    player.vel.set(0, 0, 0);
    player.grounded = false;
    camera.position.set(player.pos.x, player.pos.y + eyeH(), player.pos.z);
    camera.rotation.set(player.pitch + punch.x, player.yaw + punch.y, camRoll);
    return;
  }

  const sin = Math.sin(player.yaw), cos = Math.cos(player.yaw);
  const wx = -sin * f + cos * s, wz = -cos * f - sin * s;
  const wl = Math.hypot(wx, wz);
  const ux = wl > 0 ? wx / wl : 0, uz = wl > 0 ? wz / wl : 0;
  if (player.grounded) {
    // CS 式移动：摩擦减速（急停脆）+ 限速加速（起步快）
    const spd0 = Math.hypot(player.vel.x, player.vel.z);
    if (spd0 > 0.01) {
      const drop = Math.max(spd0, 1.5) * 8 * dt;
      const ns = Math.max(0, spd0 - drop) / spd0;
      player.vel.x *= ns; player.vel.z *= ns;
    }
    if (wl > 0) {
      const cur = player.vel.x * ux + player.vel.z * uz;
      const add = Math.min(Math.max(maxSp - cur, 0), 12 * maxSp * dt);
      player.vel.x += ux * add; player.vel.z += uz * add;
    }
  } else if (wl > 0) {
    // 空中弱操控
    const cur = player.vel.x * ux + player.vel.z * uz;
    const add = Math.min(Math.max(maxSp - cur, 0), 2.2 * maxSp * dt);
    player.vel.x += ux * add; player.vel.z += uz * add;
  }

  if (player.alive && keys['Space'] && player.grounded) { player.vel.y = 7.8; player.grounded = false; }
  player.vel.y -= gravityV * dt;
  player.grounded = false;
  moveAxisP('x', player.vel.x * dt);
  moveAxisP('z', player.vel.z * dt);
  moveAxisP('y', player.vel.y * dt);
  if (player.pos.y <= 0) { player.pos.y = 0; player.vel.y = 0; player.grounded = true; }

  // 落地：膝盖下沉弹簧 + 视角冲量 + 创伤抖动 + 闷响
  player.fallSpeed = Math.max(0, -player.vel.y);
  if (player.wasGrounded === false && player.grounded) {
    const impact = Math.min(player.fallSpeed * 0.03, 0.28);
    if (impact > 0.05) {
      landDipV -= impact * 2.4;
      punch.vx -= impact * 6;
      trauma = Math.min(1, trauma + impact * 1.2);
      landSound(impact > 0.16);
    }
  }
  player.wasGrounded = player.grounded;
  landDipV += (-320 * landDip - 16 * landDipV) * dt;
  landDip += landDipV * dt;

  // 视角弹簧（后坐/受击，欠阻尼自动回弹）
  punch.vx += (-260 * punch.x - 18 * punch.vx) * dt;
  punch.x += punch.vx * dt;
  punch.vy += (-260 * punch.y - 18 * punch.vy) * dt;
  punch.y += punch.vy * dt;

  // ---- AAA 镜头组（寒霜/虚幻式） ----
  const tq = now();
  const spd2 = Math.hypot(player.vel.x, player.vel.z);
  const bobAmt = Math.min(spd2 / 5.4, 1) * (player.grounded ? 1 : 0);
  // 侧移滚转 + 左右脚交替滚转
  const sideVel = player.vel.x * Math.cos(player.yaw) - player.vel.z * Math.sin(player.yaw);
  const footRoll = Math.sin(bobPhase) * 0.013 * bobAmt;
  camRoll += ((clamp(-sideVel * 0.012, -0.03, 0.03) + footRoll) - camRoll) * Math.min(1, dt * 10);
  // 头部起伏：双频垂直 + 横向 8 字 + 待机呼吸
  const camBobY = (Math.sin(bobPhase * 2) * 0.024 + Math.sin(bobPhase * 4) * 0.006) * bobAmt
                + Math.sin(tq * 1.3) * 0.004 * (1 - bobAmt);
  const bobLat = Math.cos(bobPhase) * 0.015 * bobAmt;
  const rX = Math.cos(player.yaw), rZ = -Math.sin(player.yaw);
  // 脚步声
  if (bobAmt > 0.3) {
    const stepIdx = Math.floor(bobPhase / Math.PI);
    if (stepIdx !== bobStep) {
      bobStep = stepIdx;
      footstep(player.walk || player.crouch ? 0.12 : 0.32);
    }
  }
  // 转身惯性（视角滞后于输入，急停甩枪更真实）
  const yawVelRaw = dt > 1e-5 ? (player.yaw - lastYaw) / dt : 0;
  lastYaw = player.yaw;
  yawVelS += (yawVelRaw - yawVelS) * Math.min(1, dt * 12);
  turnLag += (clamp(-yawVelS * 0.018, -0.03, 0.03) - turnLag) * Math.min(1, dt * 7);
  // 创伤抖动：trauma² × 多频噪声（射击/受击/落地累积，随时间消退）
  trauma = Math.max(0, trauma - dt * 1.6);
  const amp = trauma * trauma;
  const shP = (Math.sin(tq * 39.7) + Math.sin(tq * 27.3 + 1.3) * 0.6) * 0.016 * amp;
  const shY = (Math.sin(tq * 35.3 + 2.1) + Math.sin(tq * 29.1 + 0.7) * 0.6) * 0.014 * amp;
  const shR = (Math.sin(tq * 43.1 + 4.2) + Math.sin(tq * 31.7 + 2.8) * 0.6) * 0.02 * amp;
  // 疾跑前倾
  const sprintTilt = clamp((spd2 - 4.6) * 0.008, 0, 0.02);

  camera.position.set(
    player.pos.x + rX * bobLat,
    player.pos.y + eyeH() + camBobY + landDip,
    player.pos.z + rZ * bobLat
  );
  camera.rotation.y = player.yaw + punch.y + shY + turnLag;
  camera.rotation.x = player.pitch + punch.x + shP + sprintTilt;
  camera.rotation.z = camRoll + shR;
}
