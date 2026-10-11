import * as THREE from '/viewer/vendor/three.module.js';
import {hash} from '/viewer/lowpoly.js';

const insideRing=(p,ring)=>{let yes=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const a=ring[i],b=ring[j];if((a.z>p.z)!==(b.z>p.z)&&p.x<(b.x-a.x)*(p.z-a.z)/(b.z-a.z)+a.x)yes=!yes;}return yes;};
const inside=(p,area)=>insideRing(p,area.polygon)&&!(area.holes||[]).some(r=>insideRing(p,r));

// Saved vector polygons, including their holes, drive every land surface.
export function renderPresetLand(scene,town){
 const design=town.atlasDesign;if(!design?.presetId)return null;
 const native=new THREE.Group(),zoning=new THREE.Group(),resources=[];native.name='preset-land';zoning.name='preset-zoning';zoning.visible=false;
 scene.root.add(native,zoning);
 const colors={agricultural:'#c7be94',environmental:'#8da777',parks:'#a9c787',water:'#72b9c7',development:'#b8bfaf'};
 function mesh(area,color,height,group){
  const shape=new THREE.Shape(area.polygon.map(p=>new THREE.Vector2(p.x,-p.z)));
  for(const hole of area.holes||[])shape.holes.push(new THREE.Path(hole.map(p=>new THREE.Vector2(p.x,-p.z))));
  const geo=new THREE.ShapeGeometry(shape);geo.rotateX(-Math.PI/2);
  const pos=geo.attributes.position;for(let i=0;i<pos.count;i++)pos.setY(i,scene.heightAt(pos.getX(i),pos.getZ(i))+height);
  const material=new THREE.MeshBasicMaterial({color,side:THREE.DoubleSide,toneMapped:false,polygonOffset:true,polygonOffsetFactor:-1,polygonOffsetUnits:-1});
  const m=new THREE.Mesh(geo,material);m.userData.landUseId=area.id;group.add(m);resources.push(geo,material);
 }
 for(const area of design.openAreas||[])mesh(area,colors[area.kind]||'#b3c497',.055,native);
 for(const area of design.landUseZones||[])mesh(area,area.color,.075,zoning);
 const forests=(design.openAreas||[]).filter(a=>a.kind==='environmental');
 const fields=(design.openAreas||[]).filter(a=>['agricultural','development','water'].includes(a.kind));
 const matrix=new THREE.Matrix4(),position=new THREE.Vector3();
 scene.root.traverse(m=>{if(!m.isInstancedMesh||m.userData.atlasTreeKind===undefined)return;for(let i=0;i<m.count;i++){m.getMatrixAt(i,matrix);position.setFromMatrixPosition(matrix);if(fields.some(a=>inside(position,a)))m.setMatrixAt(i,new THREE.Matrix4().makeScale(0,0,0));}m.instanceMatrix.needsUpdate=true;m.computeBoundingSphere();});
 const trees=[];
 const sample=value=>{let h=value>>>0;h=Math.imul(h^(h>>>16),0x7feb352d);h=Math.imul(h^(h>>>15),0x846ca68b);return((h^(h>>>16))>>>0)/4294967296;};
 for(let i=0;i<15000;i++){
  const h=hash(`riverbend-wood:${i}`),p={x:town.bounds.minX+sample(i*2+1907)*(town.bounds.maxX-town.bounds.minX),z:town.bounds.minZ+sample(i*2+1908)*(town.bounds.maxZ-town.bounds.minZ)};
  if(forests.some(a=>inside(p,a))&&forests.some(a=>inside({x:p.x+4,z:p.z+4},a)&&inside({x:p.x-4,z:p.z-4},a)))trees.push({...p,kind:h%3,scale:1+(h%70)/100});
 }
 const dummy=new THREE.Object3D(),treeMeshes=[];
 for(let kind=0;kind<3;kind++){
  const selected=trees.filter(t=>t.kind===kind),geo=new THREE.SphereGeometry(2.8,8,6);geo.translate(0,4,0);
  const material=new THREE.MeshStandardMaterial({color:['#608365','#739169','#56796a'][kind],roughness:1});
  const m=new THREE.InstancedMesh(geo,material,selected.length);m.userData.atlasTreeKind=kind;m.castShadow=true;
  selected.forEach((p,i)=>{dummy.position.set(p.x,scene.heightAt(p.x,p.z),p.z);dummy.scale.setScalar(p.scale);dummy.updateMatrix();m.setMatrixAt(i,dummy.matrix);});
  m.computeBoundingSphere();scene.root.add(m);treeMeshes.push(m);resources.push(geo,material);
 }
 return {setZoning(show){zoning.visible=show;},destroy(){scene.root.remove(native,zoning,...treeMeshes);resources.forEach(r=>r.dispose());},stats:{zones:design.landUseZones.length,trees:trees.length}};
}
