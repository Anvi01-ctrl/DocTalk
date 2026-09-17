const API_URL = "http://127.0.0.1:8000";
let uploadedDocuments = [];
let selectedDocumentIds = new Set();
let busy = false;

const $ = (id) => document.getElementById(id);
const messages = $("messages");
const welcomeScreen = $("welcomeScreen");
const messageInput = $("messageInput");
const sendBtn = $("sendBtn");
const uploadInput = $("document-upload");
const uploadStatus = $("upload-status");
const progress = $("document-upload-progress");
const list = $("uploaded-documents-list");
const count = $("document-count");
const compareBtn = $("compare-selected-btn");
const comparisonPanel = $("comparisonPanel");
const chatArea = $("chatArea");
const insightsPanel = $("insightsPanel");

function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;", "'":"&#039;"}[c])); }
function setStatus(text, error = false) { if (uploadStatus) { uploadStatus.textContent = text; uploadStatus.classList.toggle("error", error); } }
function addMessage(text, role = "assistant") {
  if (!messages) return;
  welcomeScreen && (welcomeScreen.style.display = "none");
  messages.style.display = "flex";
  const el = document.createElement("div"); el.className = `message ${role}`;
  if (role === "assistant") { const avatar = document.createElement("div"); avatar.className = "avatar"; avatar.textContent = "✦"; el.appendChild(avatar); }
  const content = document.createElement("div"); content.className = "message-content"; content.textContent = text; el.appendChild(content); messages.appendChild(el); el.scrollIntoView({behavior:"smooth", block:"end"});
}
function showWorkspace(id) {
  document.querySelectorAll(".sidebar-item[data-target]").forEach(x => x.classList.toggle("active", x.dataset.target === id));
  if (chatArea) chatArea.style.display = id === "comparisonPanel" ? "none" : "block";
  if (comparisonPanel) comparisonPanel.classList.toggle("active", id === "comparisonPanel");
  if (insightsPanel) insightsPanel.classList.toggle("active", id === "insightsPanel");
  if (welcomeScreen) welcomeScreen.style.display = id === "chatArea" ? "block" : "none";
}
document.querySelectorAll(".sidebar-item[data-target]").forEach(x => x.addEventListener("click", () => showWorkspace(x.dataset.target)));

function renderDocuments() {
  if (!list) return;
  count.textContent = `${uploadedDocuments.length} document${uploadedDocuments.length === 1 ? "" : "s"} uploaded`;
  compareBtn.disabled = selectedDocumentIds.size < 2 || selectedDocumentIds.size > 2;
  list.innerHTML = uploadedDocuments.length ? uploadedDocuments.map(doc => `
    <article class="uploaded-document-card">
      <label><input type="checkbox" data-doc-id="${escapeHtml(doc.id)}" ${selectedDocumentIds.has(doc.id) ? "checked" : ""}> <strong>${escapeHtml(doc.filename)}</strong></label>
      <small>${doc.page_count ? `${doc.page_count} pages` : "Document"} · ${Number(doc.characters || 0).toLocaleString()} characters</small>
    </article>`).join("") : `<p class="empty-state">Upload PDF, DOCX, or TXT files to see them here.</p>`;
  list.querySelectorAll("input[data-doc-id]").forEach(box => box.addEventListener("change", () => { box.checked ? selectedDocumentIds.add(box.dataset.docId) : selectedDocumentIds.delete(box.dataset.docId); renderDocuments(); }));
}
async function uploadFile(file) {
  const form = new FormData(); form.append("file", file);
  const response = await fetch(`${API_URL}/upload`, {method:"POST", body:form});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Upload failed (${response.status})`);
  return data;
}
if (uploadInput) uploadInput.addEventListener("change", async () => {
  const files = [...uploadInput.files]; if (!files.length) return;
  setStatus(`Uploading ${files.length} file${files.length > 1 ? "s" : ""}…`); progress.textContent = "";
  for (let i = 0; i < files.length; i++) { try { const doc = await uploadFile(files[i]); uploadedDocuments.push(doc); progress.textContent = `Uploaded ${i + 1} of ${files.length}: ${files[i].name}`; } catch (e) { progress.textContent = `Could not upload ${files[i].name}: ${e.message}`; } }
  renderDocuments(); setStatus("Upload complete."); uploadInput.value = "";
});

async function sendMessage() {
  const message = messageInput?.value.trim(); if (!message || busy) return;
  busy = true; sendBtn && (sendBtn.disabled = true); addMessage(message, "user"); messageInput.value = "";
  const typing = document.createElement("div"); typing.className = "message assistant"; typing.id = "typingMessage"; typing.textContent = "DocTalk is thinking…"; messages.appendChild(typing);
  try { const r = await fetch(`${API_URL}/chat`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({message})}); const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.detail || `Request failed (${r.status})`); addMessage(d.response || "No response returned."); }
  catch (e) { addMessage(`Sorry, the request failed: ${e.message}. The backend/Azure connection may need attention.`); console.error(e); }
  finally { $("typingMessage")?.remove(); busy = false; sendBtn && (sendBtn.disabled = false); messageInput?.focus(); }
}
sendBtn?.addEventListener("click", sendMessage); messageInput?.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
document.querySelectorAll(".suggestion-card").forEach(x => x.addEventListener("click", () => { messageInput.value = x.dataset.prompt || x.textContent.trim(); sendMessage(); }));
$("newChatBtn")?.addEventListener("click", () => { messages.innerHTML = ""; welcomeScreen.style.display = "block"; showWorkspace("chatArea"); messageInput.focus(); });
compareBtn?.addEventListener("click", async () => {
  if (selectedDocumentIds.size !== 2 || busy) return;
  busy = true; compareBtn.disabled = true; showWorkspace("comparisonPanel");
  const selected = uploadedDocuments.filter(d => selectedDocumentIds.has(d.id));
  const result = comparisonPanel.querySelector(".comparison-result") || document.createElement("div"); result.className = "comparison-result"; result.textContent = "Comparing documents…"; comparisonPanel.appendChild(result);
  try { const r = await fetch(`${API_URL}/compare`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({documents:selected.map(d => ({id:d.id, filename:d.filename}))})}); const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.detail || `Comparison failed (${r.status})`); result.textContent = d.response || d.comparison || JSON.stringify(d, null, 2); }
  catch(e) { result.textContent = `Comparison failed: ${e.message}`; }
  finally { busy = false; renderDocuments(); }
});
renderDocuments();
