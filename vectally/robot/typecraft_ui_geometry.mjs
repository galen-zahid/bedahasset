export async function setMesh(e,quad=[[561.8991771,1012.7640343],[1026.8684746,946.6621573],[1062.2610701,1216.5253028],[516.6642447,1250.6909179]]){
 const c=e.querySelector('canvas[id^="paper-view-"]');if(!c)throw new Error('Warp canvas absent');
 function points(){
  const w=c.width,h=c.height,d=c.getContext('2d').getImageData(0,0,w,h).data,seen=new Uint8Array(w*h),out=[];
  const white=i=>d[i*4]>245&&d[i*4+1]>245&&d[i*4+2]>245&&d[i*4+3]>200;
  for(let k=0;k<w*h;k++){if(seen[k]||!white(k))continue;const q=[k];seen[k]=1;let n=0,sx=0,sy=0,minx=w,miny=h,maxx=0,maxy=0;
   while(q.length){const p=q.pop(),x=p%w,y=Math.floor(p/w);n++;sx+=x;sy+=y;minx=Math.min(minx,x);maxx=Math.max(maxx,x);miny=Math.min(miny,y);maxy=Math.max(maxy,y);for(const j of[p-1,p+1,p-w,p+w])if(j>=0&&j<w*h&&!seen[j]&&white(j)){seen[j]=1;q.push(j);}}
   if(n>5&&n<200&&maxx-minx<18&&maxy-miny<18)out.push({x:sx/n,y:sy/n});
  }if(out.length!==10)throw new Error('Expected ten visible warp handles, got '+out.length);
  out.sort((a,b)=>a.y-b.y);return [...out.slice(0,5).sort((a,b)=>a.x-b.x),...out.slice(5).sort((a,b)=>a.x-b.x)];
 }
 const minx=Math.min(...quad.map(p=>p[0])),maxx=Math.max(...quad.map(p=>p[0])),miny=Math.min(...quad.map(p=>p[1])),maxy=Math.max(...quad.map(p=>p[1]));
 const s=Math.min((c.width-120)/(maxx-minx),(c.height-120)/(maxy-miny));
 const q=quad.map(p=>[(p[0]-(minx+maxx)/2)*s+c.width/2,(p[1]-(miny+maxy)/2)*s+c.height/2]);
 const targets=[];
 for(const [a,b] of[[q[0],q[1]],[q[3],q[2]]])for(let i=0;i<5;i++)targets.push({x:a[0]+(b[0]-a[0])*i/4,y:a[1]+(b[1]-a[1])*i/4});
 const before=points();let after,maxError;
 async function drag(from,to){const r=c.getBoundingClientRect(),doc=e.ownerDocument;
  const emit=(target,type,x,y,buttons)=>target.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:doc.defaultView,clientX:r.left+x*r.width/c.width,clientY:r.top+y*r.height/c.height,button:0,buttons}));
  emit(c,'mousedown',from.x,from.y,1);for(let i=1;i<=12;i++){emit(doc,'mousemove',from.x+(to.x-from.x)*i/12,from.y+(to.y-from.y)*i/12,1);await new Promise(r=>setTimeout(r,20));}emit(doc,'mouseup',to.x,to.y,0);
 }
 for(let pass=0;pass<2;pass++){const current=points();for(let i=0;i<10;i++)if(Math.hypot(current[i].x-targets[i].x,current[i].y-targets[i].y)>0.7)await drag(current[i],targets[i]);await new Promise(r=>setTimeout(r,1200));after=points();maxError=Math.max(...after.map((p,i)=>Math.hypot(p.x-targets[i].x,p.y-targets[i].y)));if(maxError<=1.5)break;}
 return {quad,before,targets,after,maxError};
}

