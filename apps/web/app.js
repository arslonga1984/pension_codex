const API_BASE = localStorage.getItem("pc_api_base") || "http://127.0.0.1:8000";
const FORM_KEY = "pc_recommend_form";
const RESULT_KEY = "pc_recommend_result";
const ALT_KEY = "pc_alt_badges";

const form = document.getElementById("recommend-form");
const statusEl = document.getElementById("status");
const submitBtn = document.getElementById("submit-btn");
const resultsEl = document.getElementById("results");
const downloadBtn = document.getElementById("download-report-btn");
const reportStatusEl = document.getElementById("report-status");
const alternativesCard = document.getElementById("alternatives-card");
const altStatusEl = document.getElementById("alt-status");
const badgesEl = document.getElementById("applied-badges");
const altContribBtn = document.getElementById("alt-contrib");
const altDelayBtn = document.getElementById("alt-delay");
const altMddBtn = document.getElementById("alt-mdd");

function fmtKrw(value) {
  return new Intl.NumberFormat("ko-KR", { style: "currency", currency: "KRW", maximumFractionDigits: 0 }).format(value || 0);
}

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function setReportStatus(message, isError = false) {
  reportStatusEl.textContent = message;
  reportStatusEl.classList.toggle("error", isError);
}

function setAltStatus(message, isError = false) {
  altStatusEl.textContent = message;
  altStatusEl.classList.toggle("error", isError);
}

function updateWithdrawalModeUI() {
  const mode = form.elements.namedItem("withdrawal_mode").value;
  document.getElementById("fixed-withdraw-wrap").classList.toggle("hidden", mode !== "fixed_monthly");
  document.getElementById("target-years-wrap").classList.toggle("hidden", mode !== "target_years");
}

function serializeForm() {
  const fd = new FormData(form);
  const payload = Object.fromEntries(fd.entries());
  const numberFields = [
    "current_balance_krw", "monthly_contribution_krw", "retirement_age", "current_age",
    "target_cagr", "max_mdd", "fee_annual", "inflation", "target_years",
    "fixed_monthly_withdrawal_krw", "retirement_return_haircut_pct", "retirement_fee_annual",
  ];

  for (const key of numberFields) {
    if (payload[key] === "" || payload[key] == null) delete payload[key];
    else payload[key] = Number(payload[key]);
  }

  if (!payload.retirement_date) delete payload.retirement_date;
  if (!payload.retirement_age && !payload.retirement_date) throw new Error("은퇴일 또는 은퇴나이 중 하나는 입력해야 합니다.");
  if (payload.withdrawal_mode === "fixed_monthly" && !payload.fixed_monthly_withdrawal_krw) {
    throw new Error("매달 수령액을 입력하세요.");
  }
  if (payload.withdrawal_mode === "target_years" && !payload.target_years) payload.target_years = 20;

  return payload;
}

function writeFormValues(patch) {
  for (const [key, value] of Object.entries(patch)) {
    const el = form.elements.namedItem(key);
    if (!el) continue;
    if (el instanceof RadioNodeList) {
      const target = form.querySelector(`input[name="${key}"][value="${value}"]`);
      if (target) target.checked = true;
    } else {
      el.value = value;
    }
  }
}

function populateFromStorage() {
  const raw = localStorage.getItem(FORM_KEY);
  if (!raw) return;
  writeFormValues(JSON.parse(raw));
}

function loadAltBadges() {
  try {
    return JSON.parse(localStorage.getItem(ALT_KEY) || "[]");
  } catch (_) {
    return [];
  }
}

function saveAltBadges(items) {
  localStorage.setItem(ALT_KEY, JSON.stringify(items));
}

function addAltBadge(text) {
  const current = loadAltBadges();
  current.push(text);
  saveAltBadges(current);
  renderAltBadges();
}

function renderAltBadges() {
  badgesEl.innerHTML = "";
  const badges = loadAltBadges();
  badges.forEach((txt) => {
    const span = document.createElement("span");
    span.className = "badge";
    span.textContent = txt;
    badgesEl.appendChild(span);
  });
}

function resetAltBadges() {
  saveAltBadges([]);
  renderAltBadges();
}

function drawLine(ctx, points, color) {
  if (!points.length) return;
  ctx.beginPath();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  points.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
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

function renderChart(canvasId, seriesA, keyA, colorA, seriesB = null, keyB = null, colorB = "#f79009", area = false) {
  const canvas = document.getElementById(canvasId);
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!seriesA.length) return;

  const allVals = [...seriesA.map((d) => d[keyA]), ...(seriesB ? seriesB.map((d) => d[keyB]) : [])];
  const maxValue = Math.max(...allVals, 1);
  const toPoint = (i, value) => ({
    x: 40 + (i * (canvas.width - 60)) / Math.max(1, seriesA.length - 1),
    y: canvas.height - 30 - ((canvas.height - 50) * value) / maxValue,
  });

  const pointsA = seriesA.map((d, i) => toPoint(i, d[keyA]));
  if (area) drawArea(ctx, pointsA, canvas.height - 30, "rgba(21,94,239,0.20)");
  drawLine(ctx, pointsA, colorA);

  if (seriesB && keyB) {
    const pointsB = seriesB.map((d, i) => toPoint(i, d[keyB]));
    drawLine(ctx, pointsB, colorB);
  }
}

function shouldShowAlternatives(warnings) {
  return (warnings || []).some((w) => {
    const t = String(w).toLowerCase();
    return t.includes("max_mdd") || t.includes("constraint") || t.includes("mdd");
  });
}

function renderWarnings(warnings) {
  const ul = document.getElementById("warnings-list");
  ul.innerHTML = "";
  const list = warnings && warnings.length ? warnings : ["경고 없음"];
  list.forEach((w) => {
    const li = document.createElement("li");
    li.textContent = w;
    if (w !== "경고 없음") {
      if (w.includes("depletes") || w.includes("소진")) li.textContent += " (힌트: 월 수령액을 낮추거나 목표 기간을 줄이세요)";
      if (w.includes("5%")) li.textContent += " (힌트: 목표 수령기간을 늘리거나 위험/수익 목표를 조정하세요)";
      if (w.toLowerCase().includes("max_mdd")) li.textContent += " (힌트: 아래 대안 버튼으로 재계산해보세요)";
    }
    ul.appendChild(li);
  });

  alternativesCard.classList.toggle("hidden", !shouldShowAlternatives(warnings));
}

function renderResult(result) {
  resultsEl.classList.remove("hidden");

  const last = result.accumulation_series.at(-1) || { balance: 0, principal: 0, gain: 0 };
  document.getElementById("kpi-balance").textContent = fmtKrw(last.balance);
  document.getElementById("kpi-principal").textContent = fmtKrw(last.principal);
  document.getElementById("kpi-gain").textContent = fmtKrw(last.gain);
  document.getElementById("kpi-mdd").textContent = `${(result.metrics.est_mdd * 100).toFixed(2)}%`;

  const rs = result.retirement_summary || { monthly_withdrawal: 0, duration_months: 0 };
  document.getElementById("kpi-withdrawal").textContent = fmtKrw(rs.monthly_withdrawal || 0);
  const years = Math.floor((rs.duration_months || 0) / 12);
  const months = (rs.duration_months || 0) % 12;
  document.getElementById("kpi-duration").textContent = `${years}년 ${months}개월`;

  const tbody = document.getElementById("portfolio-body");
  tbody.innerHTML = "";
  result.portfolio.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${row.ticker}</td><td>${row.name_kr}</td><td>${(row.weight * 100).toFixed(1)}%</td>`;
    tbody.appendChild(tr);
  });

  renderWarnings(result.warnings || []);
  renderChart("stacked-chart", result.accumulation_series || [], "balance", "#12b76a", result.accumulation_series || [], "principal", "#155eef", true);
  renderChart("balance-chart", result.accumulation_series || [], "balance", "#7a5af8");
  renderChart("retirement-chart", result.retirement_series || [], "balance", "#12b76a", result.retirement_series || [], "withdrawal", "#f79009");
}

async function callRecommend(payload) {
  const response = await fetch(`${API_BASE}/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail?.message || body?.message || JSON.stringify(body));
  return body;
}

async function downloadReport(payload) {
  const response = await fetch(`${API_BASE}/report`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let body = {};
    try { body = await response.json(); } catch (_) {}
    throw new Error(body?.detail?.message || body?.message || `PDF 생성 실패 (${response.status})`);
  }

  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/);
  const filename = match ? match[1] : "retirement_etf_report.pdf";

  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

async function submitRecommend(payload, successMessage) {
  const result = await callRecommend(payload);
  localStorage.setItem(FORM_KEY, JSON.stringify(payload));
  localStorage.setItem(RESULT_KEY, JSON.stringify(result));
  renderResult(result);
  setStatus(successMessage || "추천 결과를 불러왔습니다.");
}

async function applyAlternative(type) {
  const payload = serializeForm();
  const patch = {};

  if (type === "contrib") {
    const next = Math.round((Number(payload.monthly_contribution_krw || 0) * 1.1));
    patch.monthly_contribution_krw = next;
    addAltBadge(`월불입 +10% → ${fmtKrw(next)}`);
  } else if (type === "delay") {
    if (!payload.start_date) throw new Error("시작일이 필요합니다.");
    const d = new Date(payload.start_date);
    d.setFullYear(d.getFullYear() + 2);
    const next = d.toISOString().slice(0, 10);
    patch.start_date = next;
    addAltBadge(`개시시점 +2년 → ${next}`);
  } else if (type === "mdd") {
    const next = Math.min(99.9, Number(payload.max_mdd || 0) + 5);
    patch.max_mdd = Number(next.toFixed(1));
    addAltBadge(`허용MDD +5%p → ${patch.max_mdd}%`);
  }

  writeFormValues(patch);
  updateWithdrawalModeUI();
  const nextPayload = serializeForm();
  setAltStatus("대안 적용 후 재계산 중...");
  await submitRecommend(nextPayload, "대안 적용 결과를 갱신했습니다.");
  setAltStatus("대안 적용 완료");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setStatus("요청 중...");
  submitBtn.disabled = true;
  try {
    resetAltBadges();
    const payload = serializeForm();
    await submitRecommend(payload, "추천 결과를 불러왔습니다.");
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    submitBtn.disabled = false;
  }
});

downloadBtn.addEventListener("click", async () => {
  setReportStatus("PDF 생성 중...");
  downloadBtn.disabled = true;
  try {
    const payload = serializeForm();
    await downloadReport(payload);
    setReportStatus("PDF 다운로드를 시작했습니다.");
  } catch (error) {
    setReportStatus(error.message, true);
  } finally {
    downloadBtn.disabled = false;
  }
});

altContribBtn.addEventListener("click", async () => {
  try { await applyAlternative("contrib"); } catch (error) { setAltStatus(error.message, true); }
});
altDelayBtn.addEventListener("click", async () => {
  try { await applyAlternative("delay"); } catch (error) { setAltStatus(error.message, true); }
});
altMddBtn.addEventListener("click", async () => {
  try { await applyAlternative("mdd"); } catch (error) { setAltStatus(error.message, true); }
});

form.querySelectorAll('input[name="withdrawal_mode"]').forEach((el) => el.addEventListener("change", updateWithdrawalModeUI));
populateFromStorage();
renderAltBadges();
updateWithdrawalModeUI();
const cachedResult = localStorage.getItem(RESULT_KEY);
if (cachedResult) {
  try { renderResult(JSON.parse(cachedResult)); } catch (_) { localStorage.removeItem(RESULT_KEY); }
}
