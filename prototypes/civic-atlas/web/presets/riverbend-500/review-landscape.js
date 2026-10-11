import * as THREE from '/viewer/vendor/three.module.js';

// Independent, selectable surfaces keep the approved artwork's UV registration.
// Holes exclude farm roofs, paths, and other gaps retained by the traced boundary.
export function createLandscape(scene, data, texture) {
  const pickables = [], surfaces = [], farms = [];
  function shape(points, holes = []) {
    const result = new THREE.Shape(points.map(([x, y]) => new THREE.Vector2(x, -y)));
    for (const ring of holes) result.holes.push(new THREE.Path(ring.map(([x, y]) => new THREE.Vector2(x, -y))));
    return result;
  }
  for (const feature of data.landscape) {
    if (feature.renderFill && !feature.renderTexture) continue; // Authored green already has its own surface.
    const geometry = new THREE.ShapeGeometry(shape(feature.polygon, feature.holes));
    const positions = geometry.attributes.position, uv = geometry.attributes.uv;
    for (let i = 0; i < positions.count; i++) uv.setXY(i, positions.getX(i) / 1536, 1 + positions.getY(i) / 1024);
    geometry.rotateX(-Math.PI / 2);
    const material = new THREE.MeshStandardMaterial({ map: texture, roughness: 1, side: THREE.DoubleSide });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.y = -.04;
    mesh.receiveShadow = true;
    mesh.userData.landscapeId = feature.id;
    scene.add(mesh); pickables.push(mesh); surfaces.push(mesh);
  }
  for (const feature of data.farmBuildings) {
    const geometry = new THREE.ExtrudeGeometry(shape(feature.polygon), { depth: feature.heightM / data.scaleMPerPixel, bevelEnabled: false });
    geometry.rotateX(-Math.PI / 2);
    const mesh = new THREE.Mesh(geometry, [new THREE.MeshStandardMaterial({ color: '#9ba68d', roughness: 1 }), new THREE.MeshStandardMaterial({ color: '#ddd7bc', roughness: 1 })]);
    mesh.castShadow = true; mesh.receiveShadow = true;
    mesh.userData.farmId = feature.id;
    scene.add(mesh); pickables.push(mesh); farms.push(mesh);
  }
  return {
    pickables,
    stats: { landscapeSurfaces: surfaces.length, farmBuildings: farms.length },
    select(id) {
      for (const mesh of surfaces) mesh.material.color.set(mesh.userData.landscapeId === id ? '#e9bb73' : '#ffffff');
      for (const mesh of farms) mesh.material[0].color.set(mesh.userData.farmId === id ? '#d79563' : '#9ba68d');
    },
  };
}
