import { center, GOAL, phaseAt, scan, START, WORLD } from "./model.js";

export const THEME = { background: "#0b1821", panel: "#163747", line: "#294553", lineHot: "#6ce5d2", yellow: "#f5bd69", green: "#a6ed9a", text: "#e9f4f5", muted: "#87a6b3", danger: "#f18e7d", magenta: "#c6a7e9" };

export function drawMap(ctx, result, settings, frame, robot) {
  const phase = phaseAt(frame);
  ctx.fillStyle = THEME.background;
  ctx.fillRect(0, 0, WORLD.width, WORLD.height);
  for (let id = 0; id < WORLD.cols * WORLD.rows; id++) {
    const p = center(id);
    const unknown = !result.observed.free.has(id) && !result.observed.occupied.has(id);
    if (settings.mode === "sensor" && unknown) {
      ctx.fillStyle = "#23303b";
      ctx.fillRect(p.x-12, p.y-12, 24, 24);
    } else if (result.observed.free.has(id)) {
      ctx.fillStyle = "#102a33";
      ctx.fillRect(p.x-12, p.y-12, 24, 24);
    }
    if (phase >= 1 && result.blocked.has(id) && !result.occupied.has(id)) {
      ctx.fillStyle = settings.mode === "sensor" && unknown ? "#2a323d" : "#51402c";
      ctx.fillRect(p.x-11, p.y-11, 22, 22);
    }
  }
  ctx.strokeStyle = "#23404c";
  ctx.lineWidth = 0.5;
  ctx.beginPath();
  for (let x = 0; x <= WORLD.width; x += 24) { ctx.moveTo(x, 0); ctx.lineTo(x, WORLD.height); }
  for (let y = 0; y <= WORLD.height; y += 24) { ctx.moveTo(0, y); ctx.lineTo(WORLD.width, y); }
  ctx.stroke();
  const searchProgress = phase === 2 ? Math.min(1, (frame-240)/100) : phase > 2 ? 1 : 0;
  for (const id of result.expanded.slice(0, Math.floor(searchProgress * result.expanded.length))) {
    const p = center(id);
    ctx.fillStyle = "#244f67";
    ctx.fillRect(p.x-10, p.y-10, 20, 20);
  }
  for (const box of result.obstacles) {
    ctx.fillStyle = "#583e3d";
    ctx.strokeStyle = THEME.danger;
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.roundRect(box.x+2, box.y+2, box.width-4, box.height-4, 7); ctx.fill(); ctx.stroke();
    ctx.strokeStyle = "#9a6860";
    for (let y = box.y + 14; y < box.y + box.height; y += 24) {
      ctx.beginPath(); ctx.moveTo(box.x+10, y); ctx.lineTo(box.x+box.width-10, y); ctx.stroke();
    }
  }
  // Recast from the current physical pose during motion. Planning is a static snapshot.
  const rays = phase === 3 ? scan(robot, result.obstacles, settings.range) : result.rays;
  const count = phase === 0 ? Math.floor(Math.min(1, (frame+1)/100)*rays.length) : rays.length;
  rays.slice(0, count).forEach((ray, i) => {
    if (i % 3 === 0) {
      ctx.strokeStyle = ray.hit ? "rgba(108,229,210,.20)" : "rgba(108,229,210,.07)";
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(robot.x, robot.y); ctx.lineTo(ray.x, ray.y); ctx.stroke();
    }
    if (ray.hit) { ctx.fillStyle = THEME.lineHot; ctx.beginPath(); ctx.arc(ray.x, ray.y, 2.2, 0, Math.PI*2); ctx.fill(); }
  });
  if (phase === 0 && rays[0]) {
    const ray = rays[0];
    ctx.strokeStyle = THEME.lineHot; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(robot.x, robot.y); ctx.lineTo(ray.x, ray.y); ctx.stroke();
    ctx.font = "15px system-ui"; ctx.textAlign = "center";
    const text = ray.hit ? `首个表面 ${(ray.distance/60).toFixed(2)} m` : `量程 ${(ray.distance/60).toFixed(1)} m · 无回波`;
    const x = (robot.x+ray.x)/2;
    ctx.fillStyle = THEME.background; ctx.fillRect(x-92, robot.y-35, 184, 24);
    ctx.fillStyle = THEME.lineHot; ctx.fillText(text, x, robot.y-17);
  }
  if (phase === 2 && result.visits.length) {
    const visit = result.visits[Math.max(0, Math.floor(searchProgress*result.visits.length)-1)];
    const p = center(visit.id);
    ctx.strokeStyle = "#b5ddff"; ctx.lineWidth = 2; ctx.strokeRect(p.x-10, p.y-10, 20, 20);
    ctx.fillStyle = THEME.background; ctx.fillRect(WORLD.width-245, 10, 232, 32);
    ctx.fillStyle = "#b5ddff"; ctx.font = "15px system-ui"; ctx.textAlign = "right";
    ctx.fillText(`当前格  f ${visit.f} = g ${visit.g} + h ${visit.h}`, WORLD.width-23, 31);
  }
  if (frame >= 340 && result.path.length) {
    ctx.strokeStyle = THEME.green; ctx.lineWidth = 3;
    ctx.lineJoin = "round"; ctx.beginPath();
    result.path.map(center).forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y));
    ctx.stroke();
  }
  for (const [point, label, color] of [[START, "起点", THEME.lineHot], [GOAL, "目标", THEME.green]]) {
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(point.x, point.y, 24, 0, Math.PI*2); ctx.stroke();
    ctx.fillStyle = color; ctx.font = "15px system-ui"; ctx.textAlign = "center"; ctx.fillText(label, point.x, point.y+45);
  }
  ctx.fillStyle = THEME.muted; ctx.font = "13px system-ui"; ctx.textAlign = "left";
  ctx.fillText("俯视实验场 · 每格 0.4 m", 18, 25);
  ctx.fillText(settings.mode === "known" ? "规划输入：已知静态地图" : "规划输入：起点单帧观测（灰色未知禁行）", 18, WORLD.height-60);
  ctx.fillText("1 m", WORLD.width-77, WORLD.height-70);
  ctx.strokeStyle = THEME.muted; ctx.beginPath(); ctx.moveTo(WORLD.width-86, WORLD.height-62); ctx.lineTo(WORLD.width-26, WORLD.height-62); ctx.stroke();
}

export function drawRobotDetails(ctx, robot, radius) {
  ctx.save(); ctx.translate(robot.x, robot.y); ctx.rotate(robot.heading * Math.PI / 180);
  ctx.fillStyle = "#071217"; ctx.strokeStyle = THEME.lineHot; ctx.lineWidth = 1;
  for (const sign of [-1, 1]) { ctx.beginPath(); ctx.roundRect(-radius*.5, sign*radius*.66-3, radius, 6, 2); ctx.fill(); ctx.stroke(); }
  ctx.fillStyle = THEME.lineHot; ctx.beginPath(); ctx.arc(0, 0, 5, 0, Math.PI*2); ctx.fill();
  ctx.restore();
}
