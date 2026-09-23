/* CS:GO Web —— 武器逻辑/换弹/拾取 */
'use strict';

/* ---------------- 武器逻辑 / 视图模型 ---------------- */
function updateWeapon(dt, t) {
  const w = curWeapon(); const def = w.def;
  if (player.reloadEnd && t >= player.reloadEnd) {
    const need = def.mag - w.mag;
    const take = Math.min(need, w.reserve);
    w.mag += take;
    if (w.reserve !== Infinity) w.reserve -= take;
    player.reloadEnd = 0;
  }
  const canFire = player.alive && !buyOpen && !conOpen && roundState !== 'menu' && t >= player.switchEnd && !player.reloadEnd;
  const want = def.auto ? mouseHeld : triggerEdge;
  // 空仓提示：扣扳机点击声（滑轨后挂姿态在 vm 段处理）
  if (canFire && want && t - player.lastShotT >= 60 / def.rpm) {
    if (w.mag > 0) fire(t);
    else if (triggerEdge) {
      burst({ dur: 0.03, freq: 2800, q: 5, vol: 0.18, type: 'bandpass' });
      startReload(t);
    }
  }
  triggerEdge = false;
  // 弹道序号与连发不精确度随时间衰减（停火 ~0.3s 后开始回落）
  if (t - player.lastShotT > 0.3) player.consec = Math.max(0, player.consec - dt * 10);
  player.fireInacc *= Math.exp(-dt * def.inacc.decay);

  if (vm) {
    vmKick = Math.max(0, vmKick - dt * 10);
    vmRecoilV += (-380 * vmRecoil - 22 * vmRecoilV) * dt;
    vmRecoil += vmRecoilV * dt;
    const speed = Math.hypot(player.vel.x, player.vel.z);
    if (player.grounded && speed > 0.5) bobPhase += dt * speed * 1.8;
    const bobAmt = Math.min(speed / 5.4, 1);
    const bob = Math.sin(bobPhase) * 0.009 * bobAmt;
    const bobX = Math.cos(bobPhase * 0.5) * 0.006 * bobAmt;
    // 姿态：换弹（每枪关键帧动画）/ 拔枪 / 疾跑收枪
    let pose = 0, dropY = 0, tiltZ = 0, addRY = 0, addZ = 0;
    if (player.reloadEnd) {
      const rk = clamp(1 - (player.reloadEnd - t) / def.reload, 0, 1);
      const p = reloadPose(w.id, rk);
      pose = p.rx; dropY = p.y; tiltZ = p.rz; addRY = p.ry; addZ = p.z;
      $('rbar').style.display = 'block';
      $('rfill').style.width = (rk * 100).toFixed(1) + '%';
    } else {
      $('rbar').style.display = 'none';
    }
    if (!player.reloadEnd && t < player.switchEnd) {
      const k = (player.switchEnd - t) / 0.35;
      pose = k * 0.8; dropY = -k * 0.1;
    } else if (t - inspectT < 1.1 && !aiming) { // 检视：翻转端详
      const k2 = (t - inspectT) / 1.1;
      const e = Math.sin(k2 * Math.PI);
      pose = e * 0.4; addRY = e * 0.9; tiltZ = e * 0.3; dropY = -e * 0.02;
    } else if (speed > 4.8 && !aiming) {
      tiltZ = 0.2; dropY = -0.03;
    }
    // ADS 据枪插值：枪收回画面中线
    const canAim = aiming && !player.reloadEnd && t >= player.switchEnd && player.alive;
    aimT += ((canAim ? 1 : 0) - aimT) * Math.min(1, dt * 10);
    const steady = 1 - aimT * 0.75; // 据枪时抑制摆动
    // 待机呼吸摆动（8 字）
    const idleX = Math.sin(t * 1.4) * 0.004 * steady;
    const idleY = Math.cos(t * 2.8) * 0.003 * steady;
    const swayT = clamp(-swayVX * 0.00035, -0.06, 0.06) * steady;
    vm.rotation.y += (swayT + idleX + addRY - vm.rotation.y) * Math.min(1, dt * 8);
    swayVX *= Math.max(0, 1 - dt * 10);
    vm.rotation.z += (tiltZ - vm.rotation.z) * Math.min(1, dt * 8);
    vm.position.set(
      0.26 * (1 - aimT) + bobX * steady + idleX,
      -0.26 + 0.18 * aimT + bob * steady + idleY + dropY,
      -0.5 + 0.1 * aimT + vmKick * 0.09 + vmRecoil * 0.05 + addZ
    );
    vm.rotation.x = pose + vmKick * 0.25 + vmRecoil;
    vm.visible = player.alive && !(aiming && def.scope);
    const mf = vm.getObjectByName('muzzle');
    if (mf) mf.visible = t < muzzleFlashT;
    flashLight.intensity = t < muzzleFlashT ? 2.4 : Math.max(0, flashLight.intensity - dt * 40);
  }
  // 准星间隙弹簧（欠阻尼）：真实散布投影 × 视觉放大，开枪有速度冲量、带回弹
  const pxPerRad = (innerHeight / 2) / Math.tan(camera.fov * Math.PI / 360);
  const VIS_AMP = 2.6;
  const gapTarget = 3 + currentInacc() * pxPerRad * VIS_AMP;
  gapVel += (gapTarget - gapCur) * 260 * dt;
  gapVel *= Math.max(0, 1 - dt * 14);
  gapCur += gapVel * dt;
  if (gapCur > 90) { gapCur = 90; if (gapVel > 0) gapVel = 0; }
  if (gapCur < 2) { gapCur = 2; if (gapVel < 0) gapVel = 0; }
  drawCrosshair(t);
  // FOV：据枪变焦（每枪倍率）/ 开火冲击 / AWP 开镜呼吸晃动
  fovKick *= Math.max(0, 1 - dt * 8);
  const zoomFov = def.zooms ? baseFov / def.zooms[awpStage] : baseFov / (def.zoom || 1);
  const spdW = Math.hypot(player.vel.x, player.vel.z);
  const sprintFov = clamp((spdW - 4.6) * 1.6, 0, 2.4); // 疾跑 FOV 扩张
  const targetFov = zoomFov * aimT + (baseFov + fovKick + sprintFov) * (1 - aimT);
  if (Math.abs(camera.fov - targetFov) > 0.05) {
    camera.fov += (targetFov - camera.fov) * Math.min(1, dt * 14);
    camera.updateProjectionMatrix();
  }
  if (aiming && def.scope && player.alive) {
    punch.vx += Math.sin(t * 1.7) * 0.35 * dt;
    punch.vy += Math.cos(t * 1.3) * 0.3 * dt;
  }
  $('scope').style.display = (aiming && def.scope && player.alive && t >= scopeHideUntil) ? 'block' : 'none';
}
