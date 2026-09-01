/**
 * SANJAYA 3D Knowledge Graph Renderer
 *
 * Uses Three.js for interactive 3D graph visualization.
 * Falls back to 2D Canvas if Three.js is unavailable.
 */
(function () {
  "use strict";

  const COLORS = {
    system: 0x00d4ff,
    team: 0x00ff88,
    document: 0xffaa00,
    concept: 0xaa66ff,
    process: 0xff6644,
    configuration: 0x00e5c0,
    job: 0x88aacc,
    property: 0xccaacc,
    incident: 0xff4466,
    client: 0x88ccaa,
    knowledge_article: 0x6688cc,
  };

  const EDGE_COLORS = {
    uses: 0x334466,
    references: 0x445566,
    owned_by: 0x00aa66,
    triggers: 0xaa4444,
    configures: 0x00aacc,
    resolves: 0x00cc88,
    co_occurs: 0x556677,
    used_by_team: 0x00cc66,
    associated_with: 0x6644aa,
  };

  let scene, camera, renderer, controls;
  let nodeGroup, edgeGroup, labelGroup;
  let graphData = null;
  let currentMode = "3d"; // '3d' or '2d'
  let selectedNode = null;
  let hoveredNode = null;
  let raycaster, mouse;
  let nodePositions = {};
  let forceSimulation = null;
  let isInitialized = false;
  let canvas2d, ctx2d;
  let animFrame;

  // ─── Public API ────────────────────────────────────────────────────────

  window.Graph3D = {
    init,
    load,
    setMode,
    destroy,
    filterByType,
    filterByTeam,
    search,
    focusNode,
  };

  function init(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // Check if Three.js is available
    if (typeof THREE !== "undefined") {
      init3D(container);
    } else {
      init2DCanvas(container);
    }
    isInitialized = true;
  }

  // ─── 3D Initialization ─────────────────────────────────────────────────

  function init3D(container) {
    currentMode = "3d";
    container.innerHTML = "";

    // Scene
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x050810);

    // Camera
    const w = container.clientWidth || 800;
    const h = container.clientHeight || 500;
    camera = new THREE.PerspectiveCamera(60, w / h, 0.1, 2000);
    camera.position.set(0, 0, 400);

    // Renderer
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    // OrbitControls
    if (typeof THREE.OrbitControls !== "undefined") {
      controls = new THREE.OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.rotateSpeed = 0.5;
      controls.zoomSpeed = 0.8;
      controls.minDistance = 50;
      controls.maxDistance = 1000;
    }

    // Raycaster for picking
    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();

    // Groups
    nodeGroup = new THREE.Group();
    edgeGroup = new THREE.Group();
    labelGroup = new THREE.Group();
    scene.add(edgeGroup);
    scene.add(nodeGroup);
    scene.add(labelGroup);

    // Lights
    const ambient = new THREE.AmbientLight(0x222233, 0.6);
    scene.add(ambient);
    const point = new THREE.PointLight(0x00d4ff, 0.5, 1000);
    point.position.set(200, 200, 200);
    scene.add(point);
    const point2 = new THREE.PointLight(0x00ff88, 0.3, 800);
    point2.position.set(-200, -100, -200);
    scene.add(point2);

    // Events
    renderer.domElement.addEventListener("click", on3DClick);
    renderer.domElement.addEventListener("mousemove", on3DMouseMove);
    window.addEventListener("resize", onResize);

    animate();
  }

  function animate() {
    animFrame = requestAnimationFrame(animate);
    if (controls) controls.update();
    if (renderer && scene && camera) renderer.render(scene, camera);
  }

  function onResize() {
    const container = renderer?.domElement?.parentElement;
    if (!container || !renderer || !camera) return;
    const w = container.clientWidth;
    const h = container.clientHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  }

  // ─── 3D Event Handlers ─────────────────────────────────────────────────

  function on3DClick(e) {
    if (!renderer) return;
    const rect = renderer.domElement.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    raycaster.setFromCamera(mouse, camera);
    const intersects = raycaster.intersectObjects(nodeGroup.children, true);
    if (intersects.length > 0) {
      const obj = intersects[0].object;
      if (obj.userData && obj.userData.nodeId) {
        selectNode(obj.userData.nodeId);
      }
    } else {
      deselectNode();
    }
  }

  function on3DMouseMove(e) {
    if (!renderer) return;
    const rect = renderer.domElement.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    raycaster.setFromCamera(mouse, camera);
    const intersects = raycaster.intersectObjects(nodeGroup.children, true);
    if (intersects.length > 0) {
      const obj = intersects[0].object;
      if (obj.userData && obj.userData.nodeId) {
        renderer.domElement.style.cursor = "pointer";
        const node = graphData?.nodes.find((n) => n.id === obj.userData.nodeId);
        if (node) showTooltip(node, e.clientX, e.clientY);
        return;
      }
    }
    renderer.domElement.style.cursor = "default";
    hideTooltip();
  }

  // ─── Graph Loading ─────────────────────────────────────────────────────

  async function load() {
    try {
      const resp = await fetch("/api/graph/visualization?limit=200");
      graphData = await resp.json();
      if (graphData.nodes && graphData.nodes.length > 0) {
        renderGraph();
      }
    } catch (e) {
      console.error("Failed to load graph:", e);
    }
  }

  function renderGraph() {
    if (!graphData) return;

    if (currentMode === "3d" && renderer) {
      render3D();
    } else {
      render2D();
    }
  }

  // ─── 3D Rendering ──────────────────────────────────────────────────────

  function render3D() {
    if (!scene) return;

    // Clear previous
    while (nodeGroup.children.length) nodeGroup.remove(nodeGroup.children[0]);
    while (edgeGroup.children.length) edgeGroup.remove(edgeGroup.children[0]);
    nodePositions = {};

    const nodes = graphData.nodes;
    const edges = graphData.edges;

    // Simple force-directed layout (seeded positions)
    const N = nodes.length;
    const radius = Math.min(300, 80 + N * 2);

    nodes.forEach((node, i) => {
      const phi = Math.acos(1 - (2 * (i + 0.5)) / N);
      const theta = Math.PI * (1 + Math.sqrt(5)) * i;
      // Weight by quality
      const q = node.quality || 0.5;
      const r = radius * (0.5 + q * 0.5);
      nodePositions[node.id] = {
        x: r * Math.sin(phi) * Math.cos(theta),
        y: r * Math.sin(phi) * Math.sin(theta),
        z: r * Math.cos(phi),
      };
    });

    // Offset teams to center
    nodes
      .filter((n) => n.type === "team")
      .forEach((n, i) => {
        const angle = (i / Math.max(1, nodes.filter((n) => n.type === "team").length)) * Math.PI * 2;
        nodePositions[n.id] = {
          x: Math.cos(angle) * 30,
          y: Math.sin(angle) * 30,
          z: 0,
        };
      });

    // Iterative force simulation (simple repulsion + edge attraction)
    for (let iter = 0; iter < 50; iter++) {
      for (let i = 0; i < N; i++) {
        const ni = nodes[i];
        const pi = nodePositions[ni.id];
        if (!pi) continue;

        // Repulsion from all nodes
        for (let j = i + 1; j < N; j++) {
          const nj = nodes[j];
          const pj = nodePositions[nj.id];
          if (!pj) continue;
          const dx = pi.x - pj.x;
          const dy = pi.y - pj.y;
          const dz = pi.z - pj.z;
          const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) + 0.01;
          const force = 800 / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          const fz = (dz / dist) * force;
          pi.x += fx * 0.01;
          pi.y += fy * 0.01;
          pi.z += fz * 0.01;
          pj.x -= fx * 0.01;
          pj.y -= fy * 0.01;
          pj.z -= fz * 0.01;
        }
      }

      // Edge attraction
      edges.forEach((e) => {
        const pi = nodePositions[e.source];
        const pj = nodePositions[e.target];
        if (!pi || !pj) return;
        const dx = pj.x - pi.x;
        const dy = pj.y - pi.y;
        const dz = pj.z - pi.z;
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) + 0.01;
        const force = (dist - 60) * 0.005;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        const fz = (dz / dist) * force;
        pi.x += fx;
        pi.y += fy;
        pi.z += fz;
        pj.x -= fx;
        pj.y -= fy;
        pj.z -= fz;
      });
    }

    // Create edge meshes
    edges.forEach((edge) => {
      const p1 = nodePositions[edge.source];
      const p2 = nodePositions[edge.target];
      if (!p1 || !p2) return;

      const points = [
        new THREE.Vector3(p1.x, p1.y, p1.z),
        new THREE.Vector3(p2.x, p2.y, p2.z),
      ];
      const geom = new THREE.BufferGeometry().setFromPoints(points);
      const color = EDGE_COLORS[edge.relationship] || 0x334455;
      const mat = new THREE.LineBasicMaterial({
        color: color,
        transparent: true,
        opacity: 0.4,
      });
      const line = new THREE.Line(geom, mat);
      edgeGroup.add(line);
    });

    // Create node meshes
    nodes.forEach((node) => {
      const pos = nodePositions[node.id];
      if (!pos) return;

      const color = COLORS[node.type] || 0x888888;
      const baseSize = node.type === "team" ? 8 : node.type === "system" ? 6 : 4;
      const qualityBonus = (node.quality || 0.5) * 3;
      const size = baseSize + qualityBonus;

      const geom = new THREE.SphereGeometry(size, 16, 16);
      const mat = new THREE.MeshPhongMaterial({
        color: color,
        emissive: color,
        emissiveIntensity: 0.2,
        transparent: true,
        opacity: 0.85,
      });
      const mesh = new THREE.Mesh(geom, mat);
      mesh.position.set(pos.x, pos.y, pos.z);
      mesh.userData = { nodeId: node.id, nodeType: node.type };
      nodeGroup.add(mesh);

      // Glow sprite
      const spriteMat = new THREE.SpriteMaterial({
        color: color,
        transparent: true,
        opacity: 0.15,
      });
      const sprite = new THREE.Sprite(spriteMat);
      sprite.position.set(pos.x, pos.y, pos.z);
      sprite.scale.set(size * 3, size * 3, 1);
      nodeGroup.add(sprite);
    });

    // Center camera
    camera.position.set(0, 0, radius * 1.5);
    if (controls) {
      controls.target.set(0, 0, 0);
      controls.update();
    }
  }

  // ─── 2D Canvas Rendering ───────────────────────────────────────────────

  function init2DCanvas(container) {
    currentMode = "2d";
    container.innerHTML = "";
    canvas2d = document.createElement("canvas");
    canvas2d.style.width = "100%";
    canvas2d.style.height = "100%";
    container.appendChild(canvas2d);
    ctx2d = canvas2d.getContext("2d");

    // Resize
    const resize = () => {
      canvas2d.width = container.clientWidth * (window.devicePixelRatio || 1);
      canvas2d.height = container.clientHeight * (window.devicePixelRatio || 1);
      ctx2d.scale(window.devicePixelRatio || 1, window.devicePixelRatio || 1);
      if (graphData) render2D();
    };
    resize();
    window.addEventListener("resize", resize);

    // Click
    canvas2d.addEventListener("click", on2DClick);
    canvas2d.addEventListener("mousemove", on2DMouseMove);
  }

  function render2D() {
    if (!ctx2d || !graphData) return;

    const w = canvas2d.width / (window.devicePixelRatio || 1);
    const h = canvas2d.height / (window.devicePixelRatio || 1);

    ctx2d.clearRect(0, 0, w, h);

    const nodes = graphData.nodes;
    const edges = graphData.edges;
    const N = nodes.length;

    // Layout in concentric circles by type
    const typeOrder = ["team", "system", "process", "configuration", "concept", "document", "job", "property", "incident"];
    const grouped = {};
    nodes.forEach((n) => {
      const t = n.type || "concept";
      if (!grouped[t]) grouped[t] = [];
      grouped[t].push(n);
    });

    const centerX = w / 2;
    const centerY = h / 2;
    nodePositions = {};

    typeOrder.forEach((type, ti) => {
      const group = grouped[type] || [];
      const ringRadius = 60 + ti * 50;
      group.forEach((node, i) => {
        const angle = (i / Math.max(1, group.length)) * Math.PI * 2 - Math.PI / 2;
        nodePositions[node.id] = {
          x: centerX + Math.cos(angle) * ringRadius,
          y: centerY + Math.sin(angle) * ringRadius,
        };
      });
    });

    // Draw edges
    ctx2d.lineWidth = 1;
    edges.forEach((edge) => {
      const p1 = nodePositions[edge.source];
      const p2 = nodePositions[edge.target];
      if (!p1 || !p2) return;

      const color = EDGE_COLORS[edge.relationship] || 0x334455;
      ctx2d.strokeStyle = `rgba(${(color >> 16) & 0xff},${(color >> 8) & 0xff},${color & 0xff},0.3)`;
      ctx2d.beginPath();
      ctx2d.moveTo(p1.x, p1.y);
      ctx2d.lineTo(p2.x, p2.y);
      ctx2d.stroke();
    });

    // Draw nodes
    nodes.forEach((node) => {
      const pos = nodePositions[node.id];
      if (!pos) return;

      const color = COLORS[node.type] || 0x888888;
      const r = node.type === "team" ? 10 : node.type === "system" ? 7 : 5;

      ctx2d.beginPath();
      ctx2d.arc(pos.x, pos.y, r, 0, Math.PI * 2);
      ctx2d.fillStyle = `rgba(${(color >> 16) & 0xff},${(color >> 8) & 0xff},${color & 0xff},0.25)`;
      ctx2d.fill();
      ctx2d.strokeStyle = `rgba(${(color >> 16) & 0xff},${(color >> 8) & 0xff},${color & 0xff},0.8)`;
      ctx2d.lineWidth = 1.5;
      ctx2d.stroke();

      // Label
      ctx2d.fillStyle = "#dce4ec";
      ctx2d.font = `${node.type === "team" ? "bold " : ""}${node.type === "team" ? 11 : 10}px Segoe UI`;
      ctx2d.textAlign = "center";
      const label = node.label.length > 14 ? node.label.substring(0, 12) + "…" : node.label;
      ctx2d.fillText(label, pos.x, pos.y + r + 12);
    });

    // Watermark
    ctx2d.fillStyle = "rgba(0,212,255,0.3)";
    ctx2d.font = "10px Segoe UI";
    ctx2d.textAlign = "center";
    ctx2d.fillText("SANJAYA Knowledge Brain", centerX, h - 10);
  }

  function on2DClick(e) {
    if (!canvas2d || !graphData) return;
    const rect = canvas2d.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    for (const node of graphData.nodes) {
      const pos = nodePositions[node.id];
      if (!pos) continue;
      const dx = mx - pos.x;
      const dy = my - pos.y;
      const r = node.type === "team" ? 10 : node.type === "system" ? 7 : 5;
      if (dx * dx + dy * dy < (r + 5) * (r + 5)) {
        selectNode(node.id);
        return;
      }
    }
    deselectNode();
  }

  function on2DMouseMove(e) {
    if (!canvas2d || !graphData) return;
    const rect = canvas2d.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    for (const node of graphData.nodes) {
      const pos = nodePositions[node.id];
      if (!pos) continue;
      const dx = mx - pos.x;
      const dy = my - pos.y;
      const r = node.type === "team" ? 10 : node.type === "system" ? 7 : 5;
      if (dx * dx + dy * dy < (r + 5) * (r + 5)) {
        canvas2d.style.cursor = "pointer";
        showTooltip(node, e.clientX, e.clientY);
        return;
      }
    }
    canvas2d.style.cursor = "default";
    hideTooltip();
  }

  // ─── Node Selection ────────────────────────────────────────────────────

  function selectNode(nodeId) {
    selectedNode = nodeId;
    const node = graphData?.nodes.find((n) => n.id === nodeId);
    if (!node) return;

    // Show evidence panel
    showNodePanel(node);
  }

  function deselectNode() {
    selectedNode = null;
    hideNodePanel();
  }

  // ─── Filtering ─────────────────────────────────────────────────────────

  function filterByType(type) {
    if (!graphData) return;
    // Show all, dim non-matching
    if (currentMode === "3d" && nodeGroup) {
      nodeGroup.children.forEach((child) => {
        if (!child.userData || !child.userData.nodeType) return;
        if (type === "all" || child.userData.nodeType === type) {
          if (child.material) child.material.opacity = 0.85;
        } else {
          if (child.material) child.material.opacity = 0.08;
        }
      });
    }
  }

  function filterByTeam(teamId) {
    if (!graphData) return;
    if (currentMode === "3d" && nodeGroup) {
      const teamNodes = new Set();
      if (teamId === "all") {
        // Show all
        nodeGroup.children.forEach((child) => {
          if (child.material) child.material.opacity = 0.85;
        });
        return;
      }
      // Find connected nodes
      graphData.edges.forEach((e) => {
        if (e.target === "team:" + teamId || e.source === "team:" + teamId) {
          teamNodes.add(e.source);
          teamNodes.add(e.target);
        }
      });
      graphData.nodes.forEach((n) => {
        if (n.teamId === teamId) teamNodes.add(n.id);
      });

      nodeGroup.children.forEach((child) => {
        if (!child.userData || !child.userData.nodeId) return;
        if (teamNodes.has(child.userData.nodeId) || child.userData.nodeType === "team") {
          if (child.material) child.material.opacity = 0.85;
        } else {
          if (child.material) child.material.opacity = 0.08;
        }
      });
    }
  }

  function search(query) {
    if (!graphData || !query) return;
    const q = query.toLowerCase();
    const matches = graphData.nodes.filter(
      (n) => n.label.toLowerCase().includes(q) || (n.description || "").toLowerCase().includes(q)
    );
    if (matches.length > 0) {
      focusNode(matches[0].id);
    }
  }

  function focusNode(nodeId) {
    const pos = nodePositions[nodeId];
    if (!pos) return;

    if (currentMode === "3d" && controls) {
      controls.target.set(pos.x, pos.y, pos.z);
      camera.position.set(pos.x + 100, pos.y + 50, pos.z + 100);
      controls.update();
    }
    selectNode(nodeId);
  }

  // ─── Mode Toggle ───────────────────────────────────────────────────────

  function setMode(mode) {
    currentMode = mode;
    const container = document.getElementById("graph-container");
    if (!container) return;

    if (mode === "3d" && typeof THREE !== "undefined") {
      destroy2D();
      init3D(container);
      if (graphData) renderGraph();
    } else {
      destroy3D();
      init2DCanvas(container);
      if (graphData) renderGraph();
    }
  }

  function destroy() {
    destroy3D();
    destroy2D();
    isInitialized = false;
  }

  function destroy3D() {
    if (animFrame) cancelAnimationFrame(animFrame);
    if (renderer) {
      renderer.dispose();
      renderer.domElement?.remove();
    }
    scene = null;
    camera = null;
    renderer = null;
    controls = null;
  }

  function destroy2D() {
    if (canvas2d) canvas2d.remove();
    canvas2d = null;
    ctx2d = null;
  }

  // ─── Tooltip ───────────────────────────────────────────────────────────

  function showTooltip(node, x, y) {
    let tooltip = document.getElementById("graph-tooltip");
    if (!tooltip) {
      tooltip = document.createElement("div");
      tooltip.id = "graph-tooltip";
      tooltip.style.cssText =
        "position:fixed;z-index:1000;background:rgba(10,15,24,0.95);border:1px solid #1a2538;border-radius:8px;padding:8px 12px;font-size:11px;color:#dce4ec;pointer-events:none;max-width:250px;box-shadow:0 4px 20px rgba(0,0,0,0.5)";
      document.body.appendChild(tooltip);
    }
    tooltip.innerHTML = `
      <div style="font-weight:600;color:${colorToHex(COLORS[node.type] || 0x888888)}">${esc(node.label)}</div>
      <div style="color:#8899aa;text-transform:uppercase;font-size:9px;margin-top:2px">${node.type} · quality ${(node.quality * 100).toFixed(0)}%</div>
      ${node.teamId ? '<div style="color:#00ff88;margin-top:2px">Team: ' + esc(node.teamId.toUpperCase()) + "</div>" : ""}
    `;
    tooltip.style.left = x + 12 + "px";
    tooltip.style.top = y - 10 + "px";
    tooltip.style.display = "block";
  }

  function hideTooltip() {
    const t = document.getElementById("graph-tooltip");
    if (t) t.style.display = "none";
  }

  // ─── Node Panel (Evidence Drawer) ──────────────────────────────────────

  function showNodePanel(node) {
    let panel = document.getElementById("map-info");
    if (!panel) return;

    const edges = (graphData?.edges || []).filter(
      (e) => e.source === node.id || e.target === node.id
    );

    panel.innerHTML = `
      <div class="map-info-title">${esc(node.label)}</div>
      <div class="map-info-type">${node.type} · quality ${(node.quality * 100).toFixed(0)}%${node.teamId ? " · team " + esc(node.teamId.toUpperCase()) : ""}</div>
      ${node.description ? '<div style="margin-top:6px;font-size:11px;color:var(--text2)">' + esc(node.description.substring(0, 200)) + "</div>" : ""}
      <div style="margin-top:8px;font-size:10px;color:var(--text3)">${edges.length} connection(s)</div>
      <div style="margin-top:4px;max-height:150px;overflow-y:auto">
        ${edges
          .slice(0, 10)
          .map(
            (e) =>
              '<div style="font-size:10px;color:var(--text2);margin-bottom:3px;padding:3px 6px;background:var(--bg3);border-radius:4px">' +
              '<span style="color:var(--accent)">' +
              esc(e.relationship) +
              "</span> → " +
              esc(e.source === node.id ? e.target : e.source) +
              ' <span style="color:var(--text3)">(' +
              (e.confidence * 100).toFixed(0) +
              "%)</span></div>"
          )
          .join("")}
      </div>
      <div style="margin-top:8px">
        <button class="btn-sm" onclick="askAboutNode('${esc(node.id)}')">Ask SANJAYA about this</button>
      </div>
    `;
    panel.classList.add("visible");
  }

  function hideNodePanel() {
    const panel = document.getElementById("map-info");
    if (panel) {
      panel.classList.remove("visible");
      panel.innerHTML = "";
    }
  }

  // ─── SANJAYA Context Handoff ───────────────────────────────────────────

  window.askAboutNode = async function (entityId) {
    try {
      const resp = await fetch("/api/graph/sanjaya-context?entity_id=" + encodeURIComponent(entityId));
      const data = await resp.json();
      if (data.suggestedQuestion) {
        // Switch to Ask view and pre-fill
        document.getElementById("view-map")?.classList.remove("active");
        document.getElementById("view-ask")?.classList.add("active");
        document.getElementById("query-input").value = data.suggestedQuestion;
        document.getElementById("query-input").focus();
        // Trigger send
        if (typeof sendMessage === "function") sendMessage();
      }
    } catch (e) {
      console.error("SANJAYA context error:", e);
    }
  };

  // ─── Helpers ───────────────────────────────────────────────────────────

  function colorToHex(c) {
    return "#" + c.toString(16).padStart(6, "0");
  }

  function esc(s) {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = String(s);
    return d.innerHTML;
  }
})();
