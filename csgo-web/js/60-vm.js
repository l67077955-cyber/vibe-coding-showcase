/* CS:GO Web —— 第一人称武器材质与模型 */
'use strict';

/* ---------------- 武器材质（环境反射 + 程序化贴图） ---------------- */
const envRT = (() => {
  try {
    const pmrem = new THREE.PMREMGenerator(renderer);
    const es = new THREE.Scene();
    es.add(new THREE.Mesh(new THREE.SphereGeometry(30, 16, 8),
      new THREE.MeshBasicMaterial({ color: 0x9db8d4, side: THREE.BackSide })));
    const panel = (x, y, z, w, h, c) => {
      const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, 0.5), new THREE.MeshBasicMaterial({ color: c }));
      m.position.set(x, y, z);
      m.lookAt(0, 0, 0);
      es.add(m);
    };
    panel(8, 11, 7, 7, 3, 0xfff2d0);    // 主光（暖）
    panel(-10, 4, -8, 6, 2, 0xbcd4ee);  // 冷补光
    panel(0, -9, 5, 9, 4, 0x6b5f4a);    // 地面反光
    const rt = pmrem.fromScene(es, 0.05);
    pmrem.dispose();
    return rt;
  } catch (e) { return null; }
})();
const envTex = envRT ? envRT.texture : null;
// 金属划痕
const metalTexGun = makeCanvas((x, s) => {
  x.fillStyle = '#4a4d52'; x.fillRect(0, 0, s, s);
  for (let i = 0; i < 260; i++) {
    const v = 60 + Math.random() * 40 | 0;
    x.fillStyle = `rgba(${v},${v + 2},${v + 6},0.5)`;
    x.fillRect(rand(0, s), rand(0, s), rand(2, 26), 1.5);
  }
  for (let i = 0; i < 70; i++) {
    x.fillStyle = 'rgba(190,196,205,0.25)';
    x.fillRect(rand(0, s), rand(0, s), rand(1, 3), rand(4, 18));
  }
  noise(x, s, 500, 0.05);
});
// 枪械木纹
const woodTexGun = makeCanvas((x, s) => {
  x.fillStyle = '#7a4f2a'; x.fillRect(0, 0, s, s);
  for (let i = 0; i < 42; i++) {
    x.strokeStyle = `rgba(${120 + Math.random() * 60 | 0},${70 + Math.random() * 40 | 0},${30 + Math.random() * 20 | 0},0.5)`;
    x.lineWidth = rand(1, 3);
    const y0 = rand(0, s);
    x.beginPath(); x.moveTo(0, y0);
    x.bezierCurveTo(s * 0.3, y0 + rand(-10, 10), s * 0.7, y0 + rand(-10, 10), s, y0 + rand(-6, 6));
    x.stroke();
  }
  noise(x, s, 400, 0.08);
});
const VM_M = {
  gunmetal:  new THREE.MeshStandardMaterial({ color: 0x3a3d42, metalness: 0.85, roughness: 0.38, map: toTex(metalTexGun), envMap: envTex, envMapIntensity: 0.7 }),
  darkmetal: new THREE.MeshStandardMaterial({ color: 0x25272b, metalness: 0.8, roughness: 0.5, envMap: envTex, envMapIntensity: 0.5 }),
  steel:     new THREE.MeshStandardMaterial({ color: 0xb8bcc4, metalness: 0.95, roughness: 0.22, envMap: envTex, envMapIntensity: 0.9 }),
  gold:      new THREE.MeshStandardMaterial({ color: 0xc9a24a, metalness: 0.95, roughness: 0.3, envMap: envTex, envMapIntensity: 1 }),
  polymer:   new THREE.MeshStandardMaterial({ color: 0x2c2c2e, metalness: 0.1, roughness: 0.85, envMap: envTex, envMapIntensity: 0.25 }),
  olive:     new THREE.MeshStandardMaterial({ color: 0x4d5b45, metalness: 0.15, roughness: 0.75, envMap: envTex, envMapIntensity: 0.3 }),
  wood:      new THREE.MeshStandardMaterial({ color: 0xffffff, metalness: 0.05, roughness: 0.55, map: toTex(woodTexGun), envMap: envTex, envMapIntensity: 0.25 }),
  lens:      new THREE.MeshStandardMaterial({ color: 0x0e2a4a, metalness: 0.9, roughness: 0.05, envMap: envTex, envMapIntensity: 1.3 }),
  skin:      new THREE.MeshStandardMaterial({ color: 0xc9a07a, metalness: 0, roughness: 0.7 }),
  sleeve:    new THREE.MeshStandardMaterial({ color: 0x6b6250, metalness: 0, roughness: 0.9 }),
};

/* ---------------- 手持武器模型 ---------------- */
let vm = null;
const flashTex = (() => {
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const x = c.getContext('2d');
  x.translate(32, 32);
  const grd = x.createRadialGradient(0, 0, 1, 0, 0, 30);
  grd.addColorStop(0, 'rgba(255,255,230,1)');
  grd.addColorStop(0.3, 'rgba(255,190,90,0.9)');
  grd.addColorStop(1, 'rgba(255,120,20,0)');
  x.fillStyle = grd;
  x.beginPath();
  for (let i = 0; i < 12; i++) {
    const a = i * Math.PI / 6, r = i % 2 ? 12 : 30;
    x.lineTo(Math.cos(a) * r * 1.4, Math.sin(a) * r);
  }
  x.closePath(); x.fill();
  return new THREE.CanvasTexture(c);
})();

function makeVM(id) {
  const g = new THREE.Group();
  const M = VM_M;
  const bx = (w, h, d, x, y, z, m, rx = 0, ry = 0, rz = 0) => {
    const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m);
    b.position.set(x, y, z); b.rotation.set(rx, ry, rz); g.add(b); return b;
  };
  let muzzleZ = -0.9;
  if (id === 'usp') {
    bx(.052, .062, .30, 0, .012, -.12, M.gunmetal);                       // 套筒
    bx(.054, .05, .006, 0, .012, -.02, M.darkmetal);                      // 防滑槽
    bx(.054, .05, .006, 0, .012, -.05, M.darkmetal);
    bx(.054, .05, .006, 0, .012, -.08, M.darkmetal);
    bx(.05, .05, .22, 0, -.022, -.1, M.polymer);                          // 下 frame
    bx(.044, .044, .18, 0, .012, -.36, M.darkmetal);                      // 消音器
    bx(.048, .048, .012, 0, .012, -.31, M.gunmetal);                      // 消音器环
    bx(.048, .048, .012, 0, .012, -.38, M.gunmetal);
    bx(.046, .13, .062, 0, -.1, .01, M.polymer, .28);                     // 握把
    bx(.05, .014, .068, 0, -.16, .028, M.darkmetal, .28);                 // 匣底板
    bx(.012, .008, .05, 0, -.05, -.04, M.darkmetal);                      // 护弓前
    bx(.01, .035, .012, 0, -.048, -.02, M.steel);                         // 扳机
    bx(.008, .02, .008, 0, .052, -.25, M.darkmetal);                      // 准星
    bx(.012, .014, .012, -.014, .05, 0, M.darkmetal);                     // 照门左
    bx(.012, .014, .012, .014, .05, 0, M.darkmetal);                      // 照门右
    bx(.02, .02, .05, .03, .03, -.08, M.darkmetal);                       // 抛壳窗
    muzzleZ = -0.46;
  } else if (id === 'deagle') {
    bx(.06, .08, .34, 0, .01, -.14, M.steel);                             // 大 slide
    bx(.045, .014, .3, 0, .058, -.14, M.steel);                           // 顶肋
    bx(.048, .048, .1, 0, .028, -.33, M.gunmetal);                        // 枪管六角
    bx(.052, .05, .2, 0, -.025, -.12, M.polymer);
    bx(.007, .03, .18, -.0335, .01, -.14, M.gold);                        // 金饰条
    bx(.007, .03, .18, .0335, .01, -.14, M.gold);
    bx(.05, .14, .07, 0, -.11, .02, M.polymer, .3);                       // 握把
    bx(.012, .008, .05, 0, -.055, -.05, M.darkmetal);
    bx(.01, .035, .012, 0, -.05, -.02, M.steel);
    bx(.008, .022, .008, 0, .075, -.3, M.darkmetal);                      // 准星片
    bx(.014, .012, .012, -.015, .068, .01, M.darkmetal);
    bx(.014, .012, .012, .015, .068, .01, M.darkmetal);
    bx(.02, .025, .05, .034, .035, -.1, M.darkmetal);                     // 抛壳窗
    muzzleZ = -0.4;
  } else if (id === 'ak47') {
    bx(.058, .088, .34, 0, 0, -.16, M.gunmetal);                          // 机匣
    bx(.05, .02, .3, 0, .052, -.15, M.darkmetal);                         // 机匣盖
    bx(.056, .062, .2, 0, -.004, -.44, M.wood);                           // 下护木
    bx(.05, .028, .18, 0, .042, -.42, M.wood);                            // 上护木
    bx(.024, .024, .24, 0, .056, -.4, M.darkmetal);                       // 导气管
    bx(.03, .03, .2, 0, .02, -.62, M.darkmetal);                          // 枪管
    bx(.04, .04, .05, 0, .02, -.75, M.darkmetal);                         // 制退器
    bx(.02, .028, .02, 0, .062, -.58, M.gunmetal);                        // 准星座
    bx(.007, .02, .007, 0, .078, -.58, M.darkmetal);                      // 准星片
    bx(.032, .014, .024, 0, .064, -.09, M.gunmetal);                      // 照门
    bx(.045, .09, .075, 0, -.1, -.14, M.gunmetal, .3);                    // 弯弹匣
    bx(.045, .085, .07, 0, -.17, -.09, M.gunmetal, .55);
    bx(.042, .07, .065, 0, -.226, -.03, M.gunmetal, .8);
    bx(.04, .1, .05, 0, -.088, .04, M.wood, .25);                         // 握把
    bx(.045, .075, .2, 0, -.018, .2, M.wood, .06);                        // 枪托
    bx(.05, .09, .014, 0, -.026, .305, M.darkmetal);                      // 托底板
    bx(.03, .014, .02, .036, .036, -.06, M.steel);                        // 拉机柄
    bx(.01, .032, .01, 0, -.045, -.03, M.steel);                          // 扳机
    muzzleZ = -0.79;
  } else if (id === 'm4a1') {
    bx(.055, .075, .3, 0, .005, -.14, M.gunmetal);                        // 上机匣
    bx(.05, .05, .1, 0, -.045, -.05, M.gunmetal);                         // 弹匣井
    for (let i = 0; i < 3; i++) bx(.044, .01, .068, 0, -.055 - i * .038, -.055, M.polymer, .1); // 直弹匣
    bx(.042, .012, .07, 0, -.17, -.045, M.polymer, .1);
    bx(.052, .052, .24, 0, .002, -.42, M.polymer);                        // 圆护木
    for (let i = 0; i < 5; i++) bx(.054, .014, .026, 0, .002, -.34 - i * .042, M.darkmetal);   // 透气槽
    bx(.024, .024, .14, 0, .018, -.6, M.darkmetal);                       // 枪管
    bx(.034, .034, .06, 0, .018, -.7, M.darkmetal);                       // 消焰器
    bx(.014, .038, .05, -.019, .055, -.08, M.gunmetal);                   // 提把柱
    bx(.014, .038, .05, .019, .055, -.08, M.gunmetal);
    bx(.05, .012, .16, 0, .077, -.1, M.gunmetal);                         // 顶部导轨
    for (let i = 0; i < 7; i++) bx(.05, .012, .012, 0, .084, -.05 - i * .022, M.darkmetal);    // 导轨齿
    bx(.016, .024, .016, 0, .075, -.55, M.darkmetal);                     // 准星柱
    bx(.007, .018, .007, 0, .09, -.55, M.darkmetal);                      // 准星片
    bx(.03, .03, .14, 0, 0, .13, M.darkmetal);                            // 缓冲管
    bx(.05, .09, .12, 0, -.012, .24, M.polymer);                          // 伸缩托
    bx(.04, .1, .05, 0, -.088, .05, M.polymer, .35);                      // 握把
    bx(.05, .012, .03, 0, .048, -.01, M.steel);                           // 拉机柄
    muzzleZ = -0.74;
  } else if (id === 'awp') {
    bx(.056, .09, .58, 0, 0, -.2, M.olive);                               // 主体
    bx(.03, .03, .34, 0, .015, -.66, M.darkmetal);                        // 枪管
    bx(.04, .04, .06, 0, .015, -.85, M.darkmetal);                        // 制退器
    bx(.02, .02, .08, .045, .022, .02, M.steel, 0, 0, -.5);               // 枪栓
    bx(.05, .05, .26, 0, .105, -.18, M.darkmetal);                        // 镜身
    bx(.062, .062, .05, 0, .105, -.33, M.darkmetal);                      // 物镜罩
    bx(.056, .056, .012, 0, .105, -.36, M.lens);                          // 物镜
    bx(.055, .055, .04, 0, .105, -.03, M.darkmetal);                      // 目镜
    bx(.05, .05, .012, 0, .105, -.005, M.lens);
    bx(.06, .06, .018, 0, .1, -.13, M.darkmetal);                         // 镜环
    bx(.06, .06, .018, 0, .1, -.24, M.darkmetal);
    bx(.05, .05, .3, 0, -.058, .14, M.olive);                             // 托下缘
    bx(.04, .028, .3, 0, -.012, .14, M.olive);                            // 托脊
    bx(.045, .03, .16, 0, .012, .18, M.olive);                            // 贴腮
    bx(.042, .1, .05, 0, -.085, .06, M.olive, .3);                        // 握把
    bx(.05, .08, .09, 0, -.075, -.02, M.darkmetal, .15);                  // 弹匣
    muzzleZ = -0.89;
  } else if (id === 'knife') {
    bx(.012, .045, .3, 0, .02, -.2, M.steel);            // 刀身
    bx(.012, .012, .3, 0, .048, -.2, M.steel);           // 刀刃
    bx(.05, .02, .025, 0, .025, -.045, M.darkmetal);     // 护指
    bx(.034, .04, .13, 0, -.005, .04, M.polymer, .18);   // 刀柄
    bx(.05, .05, .02, 0, -.06, .1, M.gold);              // 柄尾
    muzzleZ = -0.4;
  } else if (id === 'he' || id === 'flash') {
    const body = new THREE.Mesh(new THREE.SphereGeometry(0.075, 12, 10), id === 'he' ? M.olive : M.steel);
    body.position.set(0, 0, -0.32);
    body.castShadow = true;
    g.add(body);
    bx(.02, .02, .05, 0, .07, -.32, M.steel);            // 引信座
    bx(.012, .05, .02, .012, .1, -.31, M.steel, 0, 0, 0.3); // 拉环杆
    bx(.05, .012, .05, 0, -.055, -.3, M.darkmetal);      // 手托
    muzzleZ = -0.4;
  }
  // 手 + 手臂
  bx(.07, .07, .1, .005, -.1, -.02, M.skin, .3);
  bx(.07, .07, .11, 0, -.07, -.42, M.sleeve, .1);
  bx(.09, .09, .22, .02, -.15, .12, M.sleeve, .35);
  const mf = new THREE.Sprite(new THREE.SpriteMaterial({
    map: flashTex, color: 0xffd080, transparent: true, depthTest: false, blending: THREE.AdditiveBlending
  }));
  mf.name = 'muzzle'; mf.scale.setScalar(0.28);
  mf.position.set(0, .01, muzzleZ);
  mf.visible = false; g.add(mf);
  return g;
}
function rebuildVM() {
  if (vm) camera.remove(vm);
  vm = makeVM(curWeapon().id);
  camera.add(vm);
}
function vmTipWorld() {
  if (vm && vm.visible) return vm.localToWorld(new THREE.Vector3(0, 0.01, -0.8));
  const d = new THREE.Vector3(); camera.getWorldDirection(d);
  return camera.position.clone().addScaledVector(d, 0.6);
}
