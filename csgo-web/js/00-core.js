/* CS:GO Web —— 核心：渲染器/相机/灯光/天空盒/动态灯 */
'use strict';


/* ---------------- 工具 ---------------- */
const $ = id => document.getElementById(id);
const clamp = THREE.MathUtils.clamp;
const rand = (a, b) => a + Math.random() * (b - a);
const now = () => performance.now() / 1000;

/* ---------------- 渲染基础 ---------------- */
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x9fc7e8);
scene.fog = new THREE.Fog(0xc9d8e6, 38, 115); // 拉远以透出场外天际线

const camera = new THREE.PerspectiveCamera(75, innerWidth / innerHeight, 0.05, 200);
camera.rotation.order = 'YXZ';
scene.add(camera);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(innerWidth, innerHeight);
renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputEncoding = THREE.sRGBEncoding;            // 电影级色彩管线
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.92;
$('game').appendChild(renderer.domElement);

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
  sizeXhair();
});

scene.add(new THREE.HemisphereLight(0xdfeaf5, 0xb8a077, 0.82));
const sun = new THREE.DirectionalLight(0xffedcf, 1.05);
sun.position.set(24, 36, 14);
sun.castShadow = true;
sun.shadow.mapSize.set(1536, 1536);
sun.shadow.camera.left = -30; sun.shadow.camera.right = 30;
sun.shadow.camera.top = 30; sun.shadow.camera.bottom = -30;
sun.shadow.camera.near = 1; sun.shadow.camera.far = 110;
scene.add(sun);
const flashLight = new THREE.PointLight(0xffc070, 0, 9); // 枪口火光动态灯
scene.add(flashLight);
// Bot 枪口共享闪光灯 + 弹着冲击灯池
const botFlashLight = new THREE.PointLight(0xffc070, 0, 8);
scene.add(botFlashLight);
const impactLights = [];
for (let i = 0; i < 3; i++) {
  const L = new THREE.PointLight(0xffc080, 0, 5);
  scene.add(L);
  impactLights.push(L);
}
let impactLightIdx = 0;
function impactFlash(pos, color) {
  const L = impactLights[impactLightIdx++ % impactLights.length];
  L.color.setHex(color || 0xffc080);
  L.position.copy(pos);
  L.intensity = 1.5;
}

/* ---------------- 天空盒（着色器天穹：大气渐变 + 太阳 + 漂移云） ---------------- */
const skyMat = new THREE.ShaderMaterial({
  side: THREE.BackSide,
  depthWrite: false,
  uniforms: {
    uTime: { value: 0 },
    uSun: { value: new THREE.Vector3(24, 36, 14).normalize() },
  },
  vertexShader: 'varying vec3 vDir; void main(){ vDir = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
  fragmentShader: [
    'varying vec3 vDir;',
    'uniform float uTime; uniform vec3 uSun;',
    'float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }',
    'float vnoise(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);',
    '  return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x), mix(hash(i+vec2(0.,1.)),hash(i+vec2(1.,1.)),f.x), f.y); }',
    'float fbm(vec2 p){ float v=0.0, a=0.5; for(int i=0;i<4;i++){ v+=a*vnoise(p); p*=2.13; a*=0.5; } return v; }',
    'void main(){',
    '  vec3 d = normalize(vDir);',
    '  vec3 zen = vec3(0.34,0.54,0.80);',
    '  vec3 hor = vec3(0.86,0.89,0.92);',
    '  vec3 col = mix(hor, zen, pow(max(d.y,0.0), 0.55));',
    '  float s = max(dot(d, uSun), 0.0);',
    '  col += vec3(1.0,0.92,0.72) * pow(s, 900.0) * 4.0;',
    '  col += vec3(1.0,0.82,0.55) * pow(s, 6.0) * 0.20;',
    '  if (d.y > 0.02) {',
    '    vec2 uv = d.xz / (d.y + 0.25);',
    '    float cl = fbm(uv * 2.2 + vec2(uTime*0.006, uTime*0.002));',
    '    cl = smoothstep(0.52, 0.78, cl) * smoothstep(0.02, 0.2, d.y);',
    '    vec3 cc = mix(vec3(0.78,0.80,0.85), vec3(1.0,0.98,0.95), 0.5 + pow(s,3.0)*0.5);',
    '    col = mix(col, cc, cl * 0.72);',
    '  }',
    '  gl_FragColor = vec4(col, 1.0);',
    '}',
  ].join('\n'),
});
const skyDome = new THREE.Mesh(new THREE.SphereGeometry(95, 32, 16), skyMat);
scene.add(skyDome);
// 用天穹生成 PMREM 环境贴图，给 PBR 材质提供环境反射
(function buildEnv() {
  try {
    const pmrem = new THREE.PMREMGenerator(renderer);
    const envScene = new THREE.Scene();
    envScene.add(new THREE.Mesh(skyDome.geometry, skyMat));
    scene.environment = pmrem.fromScene(envScene, 0.04).texture;
    pmrem.dispose();
  } catch (e) { /* 环境贴图失败时仅用灯光 */ }
})();
