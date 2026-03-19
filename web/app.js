const state = {
  pontosBanda: [],
  pontosDisco: [],
  maxPontos: 30,
};

const el = {
  statusPill: document.getElementById("status-pill"),
  clock: document.getElementById("clock"),
  rede: document.getElementById("metric-rede"),
  camera: document.getElementById("metric-camera"),
  banda: document.getElementById("metric-banda"),
  disco: document.getElementById("metric-disco"),
  progressDisco: document.getElementById("progress-disco"),
  sumCiclos: document.getElementById("sum-ciclos"),
  sumRede: document.getElementById("sum-rede"),
  sumCamera: document.getElementById("sum-camera"),
  sumBanda: document.getElementById("sum-banda"),
  lastUpdate: document.getElementById("last-update"),
  chart: document.getElementById("chart"),
};

function setStatusVisual(online) {
  if (online) {
    el.statusPill.textContent = "Sistema Online";
    el.statusPill.classList.remove("is-down");
    el.statusPill.classList.add("is-up");
  } else {
    el.statusPill.textContent = "Sistema com Falha";
    el.statusPill.classList.remove("is-up");
    el.statusPill.classList.add("is-down");
  }
}

function classByPercent(value) {
  if (value >= 90) return "is-up";
  if (value >= 70) return "is-warn";
  return "is-down";
}

function updateMetricClasses(evento, resumo) {
  el.rede.className = `metric ${evento.conectividade ? "is-up" : "is-down"}`;
  el.camera.className = `metric ${evento.sinal_video ? "is-up" : "is-down"}`;
  el.sumRede.className = classByPercent(resumo.uptime_rede_pct);
  el.sumCamera.className = classByPercent(resumo.camera_ok_pct);
}

function pushSerie(arr, value) {
  arr.push(value);
  if (arr.length > state.maxPontos) arr.shift();
}

function drawChart() {
  const canvas = el.chart;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;

  ctx.clearRect(0, 0, width, height);

  ctx.strokeStyle = "rgba(150, 193, 240, 0.35)";
  ctx.lineWidth = 1;
  for (let i = 1; i <= 4; i += 1) {
    const y = (height / 5) * i;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }

  const drawLine = (points, color, maxY) => {
    if (points.length < 2) return;
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.beginPath();
    points.forEach((value, idx) => {
      const x = (idx / (state.maxPontos - 1)) * width;
      const y = height - (Math.min(value, maxY) / maxY) * height;
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  };

  drawLine(state.pontosBanda, "#3ab0ff", 5);
  drawLine(state.pontosDisco, "#8be9ff", 100);

  ctx.fillStyle = "#7dc9ff";
  ctx.font = "600 13px Space Grotesk";
  ctx.fillText("Banda (Mbps)", 16, 24);
  ctx.fillText("Disco (%)", 16, 44);
}

function render(payload) {
  const evento = payload.evento;
  const resumo = payload.resumo;

  el.clock.textContent = new Date().toLocaleTimeString("pt-BR");

  setStatusVisual(Boolean(evento.conectividade));
  el.rede.textContent = evento.conectividade ? "Online" : "Offline";
  el.camera.textContent = evento.sinal_video ? "OK" : "Sem Sinal";
  el.banda.textContent = `${evento.banda_mbps.toFixed(2)} Mbps`;
  el.disco.textContent = `${evento.uso_disco_pct.toFixed(1)}%`;
  el.progressDisco.style.width = `${Math.max(0, Math.min(100, evento.uso_disco_pct))}%`;

  el.sumCiclos.textContent = Number(resumo.total_ciclos).toFixed(0);
  el.sumRede.textContent = `${resumo.uptime_rede_pct.toFixed(1)}%`;
  el.sumCamera.textContent = `${resumo.camera_ok_pct.toFixed(1)}%`;
  el.sumBanda.textContent = `${resumo.banda_media_mbps.toFixed(2)} Mbps`;

  updateMetricClasses(evento, resumo);

  pushSerie(state.pontosBanda, evento.banda_mbps);
  pushSerie(state.pontosDisco, evento.uso_disco_pct);
  drawChart();

  el.lastUpdate.textContent = `Ultima atualizacao: ${evento.timestamp} | ciclo ${evento.ciclo}`;
}

async function fetchStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();
    render(payload);
  } catch (error) {
    el.statusPill.textContent = "Falha de conexao";
    el.statusPill.classList.remove("is-up");
    el.statusPill.classList.add("is-down");
    el.lastUpdate.textContent = `Erro ao obter status: ${error.message}`;
  }
}

fetchStatus();
setInterval(fetchStatus, 2000);
setInterval(() => {
  el.clock.textContent = new Date().toLocaleTimeString("pt-BR");
}, 1000);
