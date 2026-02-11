const API_BASE = localStorage.getItem("pc_api_base") || "http://127.0.0.1:8000";
const FORM_KEY = "pc_recommend_form";
const RESULT_KEY = "pc_recommend_result";

const form = document.getElementById("recommend-form");
const statusEl = document.getElementById("status");
const submitBtn = document.getElementById("submit-btn");
const resultsEl = document.getElementById("results");

function fmtKrw(value) {
  return new Intl.NumberFormat("ko-KR", { style: "currency", currency: "KRW", maximumFractionDigits: 0 }).format(value || 0);
}

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function serializeForm() {
  const fd = new FormData(form);
  const payload = Object.fromEntries(fd.entries());

  const numberFields = [
    "current_balance_krw",
    "monthly_contribution_krw",
    "retirement_age",
    "current_age",
    "target_cagr",
    "max_mdd",
    "fee_annual",
    "inflation",
  ];

  for (const key of numberFields) {
    if (payload[key] === "" || payload[key] == null) {
      delete payload[key];
    } else {
      payload[key] = Number(payload[key]);
    }
  }

  if (!payload.retirement_date) delete payload.retirement_date;
  if (!payload.retirement_age && !payload.retirement_date) {
    throw new Error("은퇴일 또는 은퇴나이 중 하나는 입력해야 합니다.");
  }

  return payload;
}

function populateFromStorage() {
  const raw = localStorage.getItem(FORM_KEY);
  if (!raw) return;
  const saved = JSON.parse(raw);
  for (const [k, v] of Object.entries(saved)) {
    const el = form.elements.namedItem(k);
    if (el && v !== null && v !== undefined) el.value = v;
  }
}

function drawLine(ctx, points, color) {
  if (!points.length) return;
  ctx.beginPath();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  points.forEach((p, idx) => {
    if (idx === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  });
  ctx.stroke();
}

function drawArea(ctx, points, baselineY, fillColor) {
  if (!points.length) return;
  ctx.beginPath();
  ctx.moveTo(points[0].x, baselineY);
  points.forEach((p) => ctx.lineTo(p.x, p.y));
  ctx.lineTo(points[points.length - 1].x, baselineY);
  ctx.closePath();
  ctx.fillStyle = fillColor;
  ctx.fill();
}

function renderCharts(series) {
  const stacked = document.getElementById("stacked-chart");
  const balance = document.getElementById("balance-chart");
  const sctx = stacked.getContext("2d");
  const bctx = balance.getContext("2d");

  sctx.clearRect(0, 0, stacked.width, stacked.height);
  bctx.clearRect(0, 0, balance.width, balance.height);

  if (!series.length) return;

  const maxValue = Math.max(...series.map((d) => d.balance), 1);
  const toPoint = (i, value, canvas) => ({
    x: 40 + (i * (canvas.width - 60)) / Math.max(1, series.length - 1),
    y: canvas.height - 30 - ((canvas.height - 50) * value) / maxValue,
  });

  const principalPts = series.map((d, i) => toPoint(i, d.principal, stacked));
  const balancePts = series.map((d, i) => toPoint(i, d.balance, stacked));
  drawArea(sctx, principalPts, stacked.height - 30, "rgba(21,94,239,0.25)");
  drawArea(sctx, balancePts, stacked.height - 30, "rgba(18,183,106,0.25)");
  drawLine(sctx, principalPts, "#155eef");
  drawLine(sctx, balancePts, "#12b76a");

  const linePts = series.map((d, i) => toPoint(i, d.balance, balance));
  drawLine(bctx, linePts, "#7a5af8");
}

function renderResult(result) {
  resultsEl.classList.remove("hidden");

  const last = result.accumulation_series.at(-1) || { balance: 0, principal: 0, gain: 0 };
  document.getElementById("kpi-balance").textContent = fmtKrw(last.balance);
  document.getElementById("kpi-principal").textContent = fmtKrw(last.principal);
  document.getElementById("kpi-gain").textContent = fmtKrw(last.gain);
  document.getElementById("kpi-mdd").textContent = `${(result.metrics.est_mdd * 100).toFixed(2)}%`;

  const tbody = document.getElementById("portfolio-body");
  tbody.innerHTML = "";
  result.portfolio.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${row.ticker}</td><td>${row.name_kr}</td><td>${(row.weight * 100).toFixed(1)}%</td>`;
    tbody.appendChild(tr);
  });

  renderCharts(result.accumulation_series || []);
}

async function callRecommend(payload) {
  const response = await fetch(`${API_BASE}/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const body = await response.json();
  if (!response.ok) {
    const msg = body?.detail?.message || body?.message || JSON.stringify(body);
    throw new Error(msg);
  }
  return body;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setStatus("요청 중...");
  submitBtn.disabled = true;

  try {
    const payload = serializeForm();
    localStorage.setItem(FORM_KEY, JSON.stringify(payload));
    const result = await callRecommend(payload);
    localStorage.setItem(RESULT_KEY, JSON.stringify(result));
    renderResult(result);
    setStatus("추천 결과를 불러왔습니다.");
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    submitBtn.disabled = false;
  }
});

populateFromStorage();
const cachedResult = localStorage.getItem(RESULT_KEY);
if (cachedResult) {
  try {
    renderResult(JSON.parse(cachedResult));
  } catch (_) {
    localStorage.removeItem(RESULT_KEY);
  }
}
