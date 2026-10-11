import * as THREE from '/viewer/vendor/three.module.js';

function triangleGeometry(triangles, scale) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(triangles.flatMap(tri => tri.flatMap(([x, y, h]) => [x, h / scale, y])), 3));
  geometry.computeVertexNormals();
  return geometry;
}

export function createBuilding(scene, p, index, scale) {
  const pickables = [], roofModel = p.roofModel;
  const shape = new THREE.Shape(p.footprint.map(([x, y]) => new THREE.Vector2(x, -y)));
  const wallGeometry = new THREE.ExtrudeGeometry(shape, { depth: roofModel.eaveHeightM / scale, bevelEnabled: false });
  wallGeometry.rotateX(-Math.PI / 2);
  const wallMaterial = new THREE.MeshStandardMaterial({ color: ['#e5decb', '#d8d6c4', '#e7e5d9'][index % 3], roughness: 1, side: THREE.DoubleSide });
  function add(geometry, material) {
    const mesh = new THREE.Mesh(geometry, material);
    mesh.castShadow = true; mesh.receiveShadow = true; mesh.userData.premiseId = p.premiseId;
    scene.add(mesh); pickables.push(mesh); return mesh;
  }
  add(wallGeometry, wallMaterial);
  if (roofModel.gableTriangles.length) add(triangleGeometry(roofModel.gableTriangles, scale), wallMaterial);
  const roofMaterial = new THREE.MeshStandardMaterial({ color: new THREE.Color().setHSL(.23, .08, .43 + p.physical.roofTone * .12), roughness: .95, side: THREE.DoubleSide });
  const roof = add(triangleGeometry(roofModel.triangles, scale), roofMaterial);
  roof.userData.baseColor = roofMaterial.color.clone();
  roof.userData.roofType = roofModel.type;
  const seams = [];
  for (const line of roofModel.seams) for (let i = 1; i < line.length; i++) {
    for (const [x, y, h] of [line[i - 1], line[i]]) seams.push(x, (h + .025) / scale, y);
  }
  const seamGeometry = new THREE.BufferGeometry();
  seamGeometry.setAttribute('position', new THREE.Float32BufferAttribute(seams, 3));
  scene.add(new THREE.LineSegments(seamGeometry, new THREE.LineBasicMaterial({ color: '#758172', transparent: true, opacity: .45 })));
  const panelTriangles = [];
  for (const panel of p.solarSurfaces) {
    const [a, b, c, d] = panel.vertices;
    panelTriangles.push([a, c, b], [a, d, c]);
  }
  if (panelTriangles.length) add(triangleGeometry(panelTriangles, scale), new THREE.MeshStandardMaterial({ color: '#365b73', roughness: .65, metalness: .15, side: THREE.DoubleSide }));

  if(p.isAccessory)return {roof,pickables,facets:roofModel.faces.length,windows:0};

  // Decorative openings follow the actual wall edges and recorded story count.
  // They are batched per building rather than creating a mesh for each window.
  const ring = p.footprint, edges = [], windows = [], doors = [];
  let signedArea = 0;
  for (let i = 1; i < ring.length; i++) signedArea += ring[i - 1][0] * ring[i][1] - ring[i][0] * ring[i - 1][1];
  for (let i = 1; i < ring.length; i++) {
    const a = ring[i - 1], b = ring[i], dx = b[0] - a[0], dy = b[1] - a[1], length = Math.hypot(dx, dy);
    const t = Math.max(.15, Math.min(.85, ((p.frontage[0] - a[0]) * dx + (p.frontage[1] - a[1]) * dy) / length ** 2));
    edges.push({ a, dx, dy, length, t, distance: Math.hypot(a[0] + dx * t - p.frontage[0], a[1] + dy * t - p.frontage[1]) });
  }
  const front = edges.reduce((best, edge) => edge.distance < best.distance ? edge : best);
  function opening(edge, t, width, bottom, height, target) {
    const half = width / scale / edge.length / 2;
    if (t - half < .08 || t + half > .92 || bottom + height > roofModel.eaveHeightM - .2) return;
    const direction = signedArea > 0 ? 1 : -1, ox = direction * edge.dy / edge.length * .035 / scale, oy = -direction * edge.dx / edge.length * .035 / scale;
    const left = [edge.a[0] + edge.dx * (t - half) + ox, edge.a[1] + edge.dy * (t - half) + oy];
    const right = [edge.a[0] + edge.dx * (t + half) + ox, edge.a[1] + edge.dy * (t + half) + oy];
    const a = [...left, bottom], b = [...right, bottom], c = [...right, bottom + height], d = [...left, bottom + height];
    target.push([a, b, c], [a, c, d]);
  }
  opening(front, front.t, .95, .03, 2.1, doors);
  for (const edge of edges) {
    const count = Math.min(6, Math.floor(edge.length * scale / 2.8));
    for (let floor = 0; floor < p.physical.stories; floor++) for (let i = 0; i < count; i++) {
      const t = (i + 1) / (count + 1);
      if (edge === front && floor === 0 && Math.abs(t - front.t) * edge.length * scale < 1.25) continue;
      opening(edge, t, 1.1, 1 + floor * 2.6, 1.2, windows);
    }
  }
  if (windows.length) add(triangleGeometry(windows, scale), new THREE.MeshStandardMaterial({ color: '#6b8583', roughness: .5, side: THREE.DoubleSide }));
  if (doors.length) add(triangleGeometry(doors, scale), new THREE.MeshStandardMaterial({ color: '#777b66', roughness: 1, side: THREE.DoubleSide }));
  return { roof, pickables, facets: roofModel.faces.length, windows: windows.length / 2 };
}
