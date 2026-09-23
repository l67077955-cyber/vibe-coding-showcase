/* CS:GO Web —— 程序化贴图 + 法线生成 */
'use strict';

/* ---------------- 程序化贴图 ---------------- */
function makeCanvas(fn, size = 512) {
  const c = document.createElement('canvas'); c.width = c.height = size;
  fn(c.getContext('2d'), size);
  return c;
}
function noise(x, s, n, alpha) {
  for (let i = 0; i < n; i++) {
    const v = Math.floor(rand(0, 60));
    x.fillStyle = `rgba(${v},${v},${v},${alpha})`;
    x.fillRect(rand(0, s), rand(0, s), rand(1, 3), rand(1, 3));
  }
}
const maxAniso = Math.min(8, renderer.capabilities.getMaxAnisotropy());
function toTex(canvas, rx = 1, ry = 1, srgb = false) {
  const t = new THREE.CanvasTexture(canvas);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(rx, ry);
  t.anisotropy = maxAniso;
  if (srgb) t.encoding = THREE.sRGBEncoding;
  return t;
}
// 高度图 → 法线贴图（Sobel），让砖缝/木纹产生真实光影凹凸
const normalCache = new Map();
function normalFromCanvas(src, strength = 2.2) {
  if (normalCache.has(src)) return normalCache.get(src);
  const s = src.width;
  const c = document.createElement('canvas'); c.width = c.height = s;
  const img = src.getContext('2d').getImageData(0, 0, s, s);
  const out = c.getContext('2d').createImageData(s, s);
  const hAt = (x, y) => {
    const i = (((y + s) % s) * s + ((x + s) % s)) * 4;
    return (img.data[i] + img.data[i + 1] + img.data[i + 2]) / 765;
  };
  for (let y = 0; y < s; y++) {
    for (let x = 0; x < s; x++) {
      const gx = (hAt(x - 1, y) - hAt(x + 1, y)) * strength;
      const gy = (hAt(x, y - 1) - hAt(x, y + 1)) * strength;
      const len = Math.hypot(gx, gy, 1);
      const i = (y * s + x) * 4;
      out.data[i] = ((gx / len) * 0.5 + 0.5) * 255;
      out.data[i + 1] = ((gy / len) * 0.5 + 0.5) * 255;
      out.data[i + 2] = ((1 / len) * 0.5 + 0.5) * 255;
      out.data[i + 3] = 255;
    }
  }
  c.getContext('2d').putImageData(out, 0, 0);
  normalCache.set(src, c);
  return c;
}

// 沙地：色斑 + 拼板缝 + 裂纹 + 噪点
const floorCanvas = makeCanvas((x, s) => {
  x.fillStyle = '#d6c49a'; x.fillRect(0, 0, s, s);
  for (let i = 0; i < 26; i++) {
    x.fillStyle = `rgba(${150 + Math.random() * 40 | 0},${125 + Math.random() * 35 | 0},${80 + Math.random() * 30 | 0},0.25)`;
    x.beginPath();
    x.ellipse(rand(0, s), rand(0, s), rand(10, 46), rand(8, 30), rand(0, 3), 0, 7);
    x.fill();
  }
  x.strokeStyle = 'rgba(90,70,45,0.5)'; x.lineWidth = 2;
  for (let i = 0; i <= 4; i++) {
    x.beginPath(); x.moveTo(i * s / 4, 0); x.lineTo(i * s / 4, s); x.stroke();
    x.beginPath(); x.moveTo(0, i * s / 4); x.lineTo(s, i * s / 4); x.stroke();
  }
  x.strokeStyle = 'rgba(70,55,35,0.4)'; x.lineWidth = 1;
  for (let i = 0; i < 7; i++) {
    x.beginPath();
    let px = rand(0, s), py = rand(0, s);
    x.moveTo(px, py);
    for (let j = 0; j < 5; j++) { px += rand(-22, 22); py += rand(-22, 22); x.lineTo(px, py); }
    x.stroke();
  }
  noise(x, s, 900, 0.08);
});

// dust2 式灰泥沙墙：大面风化 + 横向风蚀 + 面板缝（非砖墙）
const wallCanvas = makeCanvas((x, s) => {
  x.fillStyle = '#cfc096'; x.fillRect(0, 0, s, s);
  for (let i = 0; i < 22; i++) {
    x.fillStyle = `rgba(${185 + Math.random() * 35 | 0},${170 + Math.random() * 30 | 0},${125 + Math.random() * 28 | 0},0.28)`;
    x.beginPath();
    x.ellipse(rand(0, s), rand(0, s), rand(18, 55), rand(12, 38), rand(0, 3), 0, 7);
    x.fill();
  }
  x.fillStyle = 'rgba(140,120,85,0.16)';
  for (let i = 0; i < 6; i++) x.fillRect(0, rand(0, s), s, rand(4, 14));
  x.strokeStyle = 'rgba(120,102,70,0.4)'; x.lineWidth = 2;
  for (let i = 1; i < 4; i++) {
    x.beginPath(); x.moveTo(i * s / 4, rand(10, 30)); x.lineTo(i * s / 4 + rand(-4, 4), s - rand(10, 40)); x.stroke();
  }
  for (let i = 0; i < 9; i++) {
    x.fillStyle = 'rgba(115,95,62,0.12)';
    x.fillRect(rand(0, s), rand(0, s * 0.55), rand(5, 16), rand(35, 100));
  }
  noise(x, s, 900, 0.07);
});

// 木箱：横板木纹 + 边框 + 斜撑 + 角钉
const crateCanvas = makeCanvas((x, s) => {
  x.fillStyle = '#8a6f47'; x.fillRect(0, 0, s, s);
  for (let p = 0; p < 4; p++) {
    x.fillStyle = `rgba(${135 + Math.random() * 30 | 0},${105 + Math.random() * 25 | 0},${60 + Math.random() * 20 | 0},0.85)`;
    x.fillRect(0, p * s / 4 + 2, s, s / 4 - 4);
    x.strokeStyle = 'rgba(80,58,32,0.35)'; x.lineWidth = 1;
    for (let g = 0; g < 5; g++) {
      const gy = p * s / 4 + rand(6, s / 4 - 6);
      x.beginPath(); x.moveTo(0, gy);
      x.bezierCurveTo(s * 0.3, gy + rand(-4, 4), s * 0.6, gy + rand(-4, 4), s, gy + rand(-3, 3));
      x.stroke();
    }
  }
  x.strokeStyle = '#5f4527'; x.lineWidth = 10; x.strokeRect(5, 5, s - 10, s - 10);
  x.strokeStyle = 'rgba(95,69,39,0.9)'; x.lineWidth = 8;
  x.beginPath(); x.moveTo(14, 14); x.lineTo(s - 14, s - 14); x.stroke();
  x.fillStyle = '#3f2f18';
  [[16, 16], [s - 16, 16], [16, s - 16], [s - 16, s - 16]].forEach(([px, py]) => {
    x.beginPath(); x.arc(px, py, 4, 0, 7); x.fill();
  });
  // 角部金属护板
  x.fillStyle = 'rgba(125,120,110,0.92)';
  [[5, 5], [s - 29, 5], [5, s - 29], [s - 29, s - 29]].forEach(([px, py]) => {
    x.fillRect(px, py, 24, 24);
    x.fillStyle = 'rgba(90,86,78,0.6)';
    x.fillRect(px + 4, py + 4, 16, 16);
    x.fillStyle = 'rgba(125,120,110,0.92)';
  });
  // 模板喷字（旧补给箱风）
  x.save();
  x.translate(s / 2, s / 2);
  x.rotate(-0.02);
  x.fillStyle = 'rgba(45,32,18,0.5)';
  x.font = 'bold 26px monospace';
  x.textAlign = 'center';
  x.fillText('SUPPLY', 0, -10);
  x.font = 'bold 17px monospace';
  x.fillText('7.62 AMMO', 0, 16);
  x.restore();
  noise(x, s, 400, 0.06);
});

// 混凝土高台：分格 + 铆点
const platCanvas = makeCanvas((x, s) => {
  x.fillStyle = '#9c8a63'; x.fillRect(0, 0, s, s);
  x.strokeStyle = 'rgba(70,60,40,0.5)'; x.lineWidth = 3;
  for (let i = 0; i <= 2; i++) {
    x.beginPath(); x.moveTo(i * s / 2, 0); x.lineTo(i * s / 2, s); x.stroke();
    x.beginPath(); x.moveTo(0, i * s / 2); x.lineTo(s, i * s / 2); x.stroke();
  }
  x.fillStyle = 'rgba(60,50,35,0.5)';
  for (let i = 0; i < 24; i++) x.fillRect(rand(0, s), rand(0, s), 2, 2);
  noise(x, s, 500, 0.07);
});

// 灰泥墙面：色渍 + 裂纹
const plasterCanvas = makeCanvas((x, s) => {
  x.fillStyle = '#cdb488'; x.fillRect(0, 0, s, s);
  for (let i = 0; i < 18; i++) {
    x.fillStyle = `rgba(${170 + Math.random() * 40 | 0},${145 + Math.random() * 35 | 0},${100 + Math.random() * 30 | 0},0.3)`;
    x.beginPath();
    x.ellipse(rand(0, s), rand(0, s), rand(15, 60), rand(12, 40), rand(0, 3), 0, 7);
    x.fill();
  }
  x.strokeStyle = 'rgba(110,90,60,0.35)'; x.lineWidth = 1;
  for (let i = 0; i < 8; i++) {
    x.beginPath();
    let px = rand(0, s), py = 0;
    x.moveTo(px, py);
    for (let j = 0; j < 7; j++) { px += rand(-12, 12); py += rand(20, 42); x.lineTo(px, py); }
    x.stroke();
  }
  noise(x, s, 800, 0.07);
});
// 陶瓦屋顶
const roofCanvas = makeCanvas((x, s) => {
  x.fillStyle = '#8f563a'; x.fillRect(0, 0, s, s);
  const rows = 8, rh = s / rows;
  for (let r = 0; r < rows; r++) {
    for (let c2 = 0; c2 < 8; c2++) {
      const shade = 130 + Math.random() * 50 | 0;
      x.fillStyle = `rgb(${shade + 30},${(shade * 0.55) | 0},${(shade * 0.38) | 0})`;
      x.beginPath();
      x.ellipse(c2 * s / 8 + s / 16, r * rh + rh / 2, s / 17, rh / 2.3, 0, 0, 7);
      x.fill();
    }
    x.fillStyle = 'rgba(60,30,18,0.35)';
    x.fillRect(0, (r + 1) * rh - 3, s, 3);
  }
});
// 石板路
const cobbleCanvas = makeCanvas((x, s) => {
  x.fillStyle = '#6e655a'; x.fillRect(0, 0, s, s);
  const n2 = 7, cs = s / n2;
  for (let r = 0; r < n2; r++) for (let c2 = 0; c2 < n2; c2++) {
    const v = 120 + Math.random() * 50 | 0;
    x.fillStyle = `rgb(${v},${v - 8},${v - 22})`;
    x.beginPath();
    const off = (r % 2) * cs / 2;
    x.ellipse(c2 * cs + off + cs / 2 + rand(-1, 1), r * cs + cs / 2 + rand(-1, 1), cs / 2.4, cs / 3.2, rand(-0.2, 0.2), 0, 7);
    x.fill();
  }
  noise(x, s, 600, 0.08);
});
// 布篷条纹
const clothCanvas = makeCanvas((x, s) => {
  for (let i = 0; i < 8; i++) {
    x.fillStyle = i % 2 ? '#c8392e' : '#ede3cf';
    x.fillRect(i * s / 8, 0, s / 8, s);
  }
  noise(x, s, 300, 0.06);
});
// 木门
const doorCanvas = makeCanvas((x, s) => {
  x.fillStyle = '#4a351f'; x.fillRect(0, 0, s, s);
  for (let i = 1; i < 4; i++) {
    x.fillStyle = `rgba(${90 + Math.random() * 30 | 0},${65 + Math.random() * 20 | 0},${35 | 0},0.6)`;
    x.fillRect(i * s / 4, 6, s / 4 - 4, s - 12);
  }
  x.strokeStyle = 'rgba(30,20,10,0.8)'; x.lineWidth = 3;
  for (let i = 1; i < 4; i++) { x.beginPath(); x.moveTo(i * s / 4, 4); x.lineTo(i * s / 4, s - 4); x.stroke(); }
  x.strokeStyle = '#33241388'; x.lineWidth = 14; x.strokeRect(7, 7, s - 14, s - 14);
  x.fillStyle = '#c9b063';
  x.beginPath(); x.arc(s * 0.78, s * 0.55, 7, 0, 7); x.fill();
});
// 暗窗（十字框 + 天光反射）
const windowCanvas = makeCanvas((x, s) => {
  x.fillStyle = '#20262e'; x.fillRect(0, 0, s, s);
  x.fillStyle = 'rgba(130,160,190,0.28)';
  x.beginPath(); x.moveTo(0, s); x.lineTo(s * 0.5, 0); x.lineTo(s * 0.75, 0); x.lineTo(s * 0.25, s); x.fill();
  x.strokeStyle = '#3d3126'; x.lineWidth = 10; x.strokeRect(4, 4, s - 8, s - 8);
  x.lineWidth = 6;
  x.beginPath(); x.moveTo(s / 2, 6); x.lineTo(s / 2, s - 6); x.stroke();
  x.beginPath(); x.moveTo(6, s / 2); x.lineTo(s - 6, s / 2); x.stroke();
});
