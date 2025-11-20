// script.js - frontend logic for EmotiCare
const API_BASE = "http://127.0.0.1:8000"; // backend base - change if deployed elsewhere

// DOM
const textTab = document.getElementById("text-tab");
const imageTab = document.getElementById("image-tab");
const textForm = document.getElementById("text-form");
const imageForm = document.getElementById("image-form");
const userText = document.getElementById("user-text");
const analyzeTextBtn = document.getElementById("analyze-text-btn");
const analyzeImageBtn = document.getElementById("analyze-image-btn");
const userImage = document.getElementById("user-image");
const imagePreviewDiv = document.getElementById("image-preview");
const previewImg = document.getElementById("preview");
const resultsContainer = document.getElementById("results-container");
const noResults = document.getElementById("no-results");
const moodLabel = document.getElementById("mood-label");
const moodReason = document.getElementById("mood-reason");
const confidenceBadge = document.getElementById("confidence");
const adviceEl = document.getElementById("advice");
const actionsEl = document.getElementById("actions");
const journalPromptEl = document.getElementById("journal-prompt");
const followUpEl = document.getElementById("follow-up");
const riskAlert = document.getElementById("risk-alert");
const historyList = document.getElementById("history-list");
const clearHistoryBtn = document.getElementById("clear-history-btn");
const exportHistoryBtn = document.getElementById("export-history-btn");
const saveJournalBtn = document.getElementById("save-journal-btn");
const moodChartCtx = document.getElementById("mood-chart").getContext("2d");

let moodChart;
const MOOD_STORAGE_KEY = "emoticare_history_v1";
const MAX_HISTORY = 7;

// tabs
textTab.addEventListener("click", () => {
  textForm.classList.remove("hidden");
  imageForm.classList.add("hidden");
  textTab.classList.add("bg-primary", "text-white");
  imageTab.classList.remove("bg-primary");
});
imageTab.addEventListener("click", () => {
  imageForm.classList.remove("hidden");
  textForm.classList.add("hidden");
  imageTab.classList.add("bg-primary", "text-white");
  textTab.classList.remove("bg-primary");
});

// image preview
userImage.addEventListener("change", (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const url = URL.createObjectURL(f);
  previewImg.src = url;
  imagePreviewDiv.classList.remove("hidden");
});

// analyze text
analyzeTextBtn.addEventListener("click", async () => {
  const text = userText.value.trim();
  if (!text) {
    alert("Please type something to analyze.");
    return;
  }
  setLoading(true);
  try {
    const res = await fetch(`${API_BASE}/analyze_text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    });
    const j = await res.json();
    handleResult(j);
  } catch (err) {
    console.error(err);
    alert("Error calling backend. See console.");
  } finally {
    setLoading(false);
  }
});

// analyze image
analyzeImageBtn.addEventListener("click", async () => {
  const f = userImage.files[0];
  if (!f) {
    alert("Please upload an image first.");
    return;
  }
  setLoading(true);
  const fd = new FormData();
  fd.append("file", f);
  try {
    const res = await fetch(`${API_BASE}/analyze_image`, {
      method: "POST",
      body: fd
    });
    const j = await res.json();
    handleResult(j);
  } catch (err) {
    console.error(err);
    alert("Error calling backend. See console.");
  } finally {
    setLoading(false);
  }
});

// save journal entry locally (just add to input text)
saveJournalBtn.addEventListener("click", () => {
  const text = userText.value.trim();
  if (!text) return alert("Type your journal entry first.");
  // For demo, call analyze then save is similar to pressing Analyze
  analyzeTextBtn.click();
});

// clear image
document.getElementById("clear-image-btn").addEventListener("click", () => {
  userImage.value = "";
  imagePreviewDiv.classList.add("hidden");
  previewImg.src = "#";
});

// history helpers
function loadHistory() {
  const raw = localStorage.getItem(MOOD_STORAGE_KEY);
  return raw ? JSON.parse(raw) : [];
}
function saveHistory(arr) {
  localStorage.setItem(MOOD_STORAGE_KEY, JSON.stringify(arr.slice(-100)));
}
function addToHistory(entry) {
  const arr = loadHistory();
  arr.push(entry);
  saveHistory(arr);
  renderHistory();
}
function clearHistory() {
  localStorage.removeItem(MOOD_STORAGE_KEY);
  renderHistory();
}
clearHistoryBtn.addEventListener("click", () => {
  if (!confirm("Clear local mood history?")) return;
  clearHistory();
});
exportHistoryBtn.addEventListener("click", () => {
  const arr = loadHistory();
  const blob = new Blob([JSON.stringify(arr, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "emoticare_history.json";
  a.click();
});

// render history
function renderHistory() {
  const arr = loadHistory().slice(-MAX_HISTORY).reverse();
  historyList.innerHTML = arr.length ? arr.map(e => `<div class="mb-2"><strong>${e.mood}</strong> — ${new Date(e.timestamp).toLocaleString()}<div class="text-sm text-gray-600">${e.summary || e.reason || ''}</div></div>`).join('') : "<div class='text-gray-500'>No saved history</div>";
  renderChart();
}

// render chart with counts per mood
function renderChart() {
  const arr = loadHistory();
  const counts = {};
  arr.forEach(x => { counts[x.mood] = (counts[x.mood] || 0) + 1; });
  const labels = Object.keys(counts);
  const data = labels.map(l => counts[l]);
  if (moodChart) moodChart.destroy();
  moodChart = new Chart(moodChartCtx, {
    type: 'bar',
    data: { labels, datasets: [{ label: 'Mood count', data }] },
    options: { responsive: true, maintainAspectRatio: false }
  });
}

renderHistory();

// display results
function handleResult(j) {
  if (j.error) {
    alert("Server error: " + j.error);
    return;
  }
  // structure expected from backend:
  // { mood_label, confidence, mood_intensity, key_phrases, therapy: { empathetic_response, immediate_actions, journaling_prompt, follow_up_suggestion }, crisis: { is_high_risk, safety_script } }
  resultsContainer.classList.remove("hidden");
  noResults.classList.add("hidden");

  const mood = j.mood_label || j.mood || "neutral";
  moodLabel.textContent = mood;
  confidenceBadge.textContent = `Confidence ${typeof j.confidence === 'number' ? (j.confidence*100).toFixed(0) + '%' : ''}`;
  moodReason.textContent = (j.key_phrases || []).join(", ") || (j.reason || '');

  if (j.crisis && j.crisis.is_high_risk) {
    riskAlert.classList.remove("hidden");
    riskAlert.innerHTML = `<strong>HIGH RISK DETECTED</strong><p>${j.crisis.safety_script || 'Please seek immediate help.'}</p>`;
  } else {
    riskAlert.classList.add("hidden");
    riskAlert.innerHTML = "";
  }

  // therapy
  const therapy = j.therapy || {};
  adviceEl.textContent = therapy.empathetic_response || '';
  actionsEl.innerHTML = (therapy.immediate_actions || []).map(a => `<li>${a}</li>`).join('');
  journalPromptEl.textContent = therapy.journaling_prompt || '';
  followUpEl.textContent = therapy.follow_up_suggestion || '';

  // save to local history
  const entry = {
    mood,
    confidence: j.confidence || 0,
    mood_intensity: j.mood_intensity || 0,
    reason: (j.key_phrases || []).join(", "),
    summary: therapy.empathetic_response || '',
    timestamp: j.timestamp || new Date().toISOString()
  };
  addToHistory(entry);
}

// loading UI
function setLoading(on) {
  [analyzeTextBtn, analyzeImageBtn].forEach(b => b.disabled = on);
  if (on) {
    analyzeTextBtn.textContent = "Analyzing...";
    analyzeImageBtn.textContent = "Analyzing...";
  } else {
    analyzeTextBtn.textContent = "Analyze Mood";
    analyzeImageBtn.textContent = "Analyze Expression";
  }
}
