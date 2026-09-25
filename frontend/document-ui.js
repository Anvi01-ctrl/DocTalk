/**
 * DocTalk — Document UI Manager
 *
 * Manages the persistent "My Documents" section,
 * document deletion, and refresh after upload.
 *
 * Depends on: script.js globals (API_URL, escapeHtml, etc.)
 */

/* =========================================================
   LOAD PERSISTENT DOCUMENTS FROM BACKEND
   ========================================================= */

async function loadMyDocuments() {
    try {
        var response = await fetch(API_URL + "/documents");
        if (!response.ok) return;

        var docs = await response.json();
        renderMyDocuments(docs);
    } catch (e) {
        console.error("Failed to load My Documents:", e);
    }
}


/* =========================================================
   RENDER MY DOCUMENTS LIST
   ========================================================= */

function renderMyDocuments(docs) {
    var container = document.getElementById("my-documents-list");
    if (!container) return;

    var countEl = document.getElementById("my-documents-count");

    if (!docs || docs.length === 0) {
        container.innerHTML = '<p class="empty-state">No documents in your library.</p>';
        if (countEl) countEl.textContent = "0 documents";
        return;
    }

    if (countEl) countEl.textContent = docs.length + " document" + (docs.length === 1 ? "" : "s");

    container.innerHTML = "";

    for (var i = 0; i < docs.length; i++) {
        var doc = docs[i];
        var card = document.createElement("div");
        card.className = "my-doc-card";

        // Calculate expiry days
        var daysRemaining = 30;
        if (doc.uploaded_at) {
            var uploadDate = new Date(doc.uploaded_at);
            var now = new Date();
            var elapsed = Math.floor((now - uploadDate) / (1000 * 60 * 60 * 24));
            daysRemaining = Math.max(0, 30 - elapsed);
        }

        // Determine expiry badge class
        var expiryClass = "safe";
        if (daysRemaining <= 5) expiryClass = "danger";
        else if (daysRemaining <= 15) expiryClass = "warning";

        // Checkbox for selection
        var label = document.createElement("label");
        label.className = "my-doc-label";

        var cb = document.createElement("input");
        cb.type = "checkbox";
        cb.dataset.docId = doc.document_id;
        if (selectedDocumentIds.has(doc.document_id)) {
            cb.checked = true;
        }

        cb.addEventListener("change", (function(docId, docData) {
            return function(e) {
                if (e.target.checked) {
                    selectedDocumentIds.add(docId);
                    // Add to uploadedDocuments if not already there
                    if (!uploadedDocuments.find(function(d) { return d.id === docId; })) {
                        uploadedDocuments.push({
                            id: docId,
                            document_id: docId,
                            filename: docData.filename,
                            page_count: docData.page_count,
                            characters: docData.character_count
                        });
                    }
                } else {
                    selectedDocumentIds.delete(docId);
                }
                updateCompareButton();
                renderDocuments();
            };
        })(doc.document_id, doc));

        var nameSpan = document.createElement("strong");
        nameSpan.textContent = doc.filename || "Unknown";

        label.appendChild(cb);
        label.appendChild(nameSpan);
        card.appendChild(label);

        // Expiry badge
        var expiryBadge = document.createElement("span");
        expiryBadge.className = "doc-expiry-badge " + expiryClass;
        var dot = document.createElement("span");
        dot.className = "expiry-dot";
        expiryBadge.appendChild(dot);
        var expiryText = document.createTextNode(
            daysRemaining === 0 ? "Expiring today" :
            daysRemaining === 1 ? "Expires in 1 day" :
            "Expires in " + daysRemaining + " days"
        );
        expiryBadge.appendChild(expiryText);
        card.appendChild(expiryBadge);

        // Meta info
        var meta = document.createElement("small");
        meta.className = "my-doc-meta";
        var parts = [];
        if (doc.file_type) parts.push(doc.file_type.toUpperCase());
        if (doc.page_count) parts.push(doc.page_count + " pages");
        if (doc.character_count) parts.push(Number(doc.character_count).toLocaleString() + " chars");
        meta.textContent = parts.join(" \u00B7 ") || "Document";
        card.appendChild(meta);

        // Delete button
        var delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "my-doc-delete";
        delBtn.textContent = "\uD83D\uDDD1";
        delBtn.title = "Delete permanently";
        delBtn.addEventListener("click", (function(docId, filename) {
            return function(e) {
                e.stopPropagation();
                e.preventDefault();
                confirmDeleteDocument(docId, filename);
            };
        })(doc.document_id, doc.filename));

        card.appendChild(delBtn);
        container.appendChild(card);
    }
}


/* =========================================================
   DELETE DOCUMENT
   ========================================================= */

/**
 * Show a custom confirmation modal (replaces native confirm()).
 * Returns a Promise that resolves true/false.
 */
function _showDeleteModal(filename) {
    return new Promise(function(resolve) {
        // Remove any existing modal
        var old = document.getElementById("delete-confirm-modal");
        if (old) old.remove();

        var overlay = document.createElement("div");
        overlay.id = "delete-confirm-modal";
        overlay.className = "delete-modal-overlay";

        var modal = document.createElement("div");
        modal.className = "delete-modal-card";

        modal.innerHTML =
            '<div class="delete-modal-icon">' +
                '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#f43f5e" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
                    '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>' +
                    '<path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>' +
                    '<line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>' +
                '</svg>' +
            '</div>' +
            '<h3 class="delete-modal-title">Delete Document</h3>' +
            '<p class="delete-modal-text">Are you sure you want to permanently delete <strong>' + escapeHtml(filename) + '</strong>?</p>' +
            '<p class="delete-modal-sub">This will remove it from Azure Storage and the search index. This cannot be undone.</p>' +
            '<div class="delete-modal-actions">' +
                '<button type="button" class="delete-modal-btn cancel" id="delete-modal-cancel">Cancel</button>' +
                '<button type="button" class="delete-modal-btn confirm" id="delete-modal-confirm">Delete</button>' +
            '</div>';

        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        // Animate in
        requestAnimationFrame(function() {
            overlay.classList.add("visible");
        });

        function close(result) {
            overlay.classList.remove("visible");
            setTimeout(function() { overlay.remove(); }, 200);
            resolve(result);
        }

        document.getElementById("delete-modal-cancel").addEventListener("click", function() { close(false); });
        document.getElementById("delete-modal-confirm").addEventListener("click", function() { close(true); });
        overlay.addEventListener("click", function(e) {
            if (e.target === overlay) close(false);
        });
    });
}

async function confirmDeleteDocument(docId, filename) {
    var confirmed = await _showDeleteModal(filename);
    if (!confirmed) return;

    try {
        var response = await fetch(API_URL + "/documents/" + docId, {
            method: "DELETE"
        });

        if (!response.ok) {
            var data = await response.json().catch(function() { return {}; });
            throw new Error(data.detail || "Delete failed (" + response.status + ")");
        }

        // Remove from local state
        selectedDocumentIds.delete(docId);
        uploadedDocuments = uploadedDocuments.filter(function(d) {
            return d.id !== docId && d.document_id !== docId;
        });

        renderDocuments();
        updateCompareButton();
        loadMyDocuments();

        setStatus("Deleted: " + filename);

    } catch (e) {
        console.error("Delete failed:", e);
        setStatus("Failed to delete: " + e.message);
    }
}


/* =========================================================
   DELETE ALL DOCUMENTS
   ========================================================= */

function _showDeleteAllModal(docCount) {
    return new Promise(function(resolve) {
        var old = document.getElementById("delete-confirm-modal");
        if (old) old.remove();

        var overlay = document.createElement("div");
        overlay.id = "delete-confirm-modal";
        overlay.className = "delete-modal-overlay";

        var modal = document.createElement("div");
        modal.className = "delete-modal-card";

        modal.innerHTML =
            '<div class="delete-modal-icon">' +
                '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#f43f5e" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
                    '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>' +
                    '<path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>' +
                '</svg>' +
            '</div>' +
            '<h3 class="delete-modal-title">Delete All Documents</h3>' +
            '<p class="delete-modal-text">This will permanently delete all <strong>' + docCount + ' documents</strong> from Azure Storage and the search index.</p>' +
            '<p class="delete-modal-sub">This action cannot be undone. Your search quota will be freed up.</p>' +
            '<div class="delete-modal-actions">' +
                '<button type="button" class="delete-modal-btn cancel" id="delete-modal-cancel">Cancel</button>' +
                '<button type="button" class="delete-modal-btn confirm" id="delete-modal-confirm">Delete All</button>' +
            '</div>';

        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        requestAnimationFrame(function() {
            overlay.classList.add("visible");
        });

        function close(result) {
            overlay.classList.remove("visible");
            setTimeout(function() { overlay.remove(); }, 200);
            resolve(result);
        }

        document.getElementById("delete-modal-cancel").addEventListener("click", function() { close(false); });
        document.getElementById("delete-modal-confirm").addEventListener("click", function() { close(true); });
        overlay.addEventListener("click", function(e) {
            if (e.target === overlay) close(false);
        });
    });
}

async function confirmDeleteAllDocuments() {
    // Get current count
    var countEl = document.getElementById("my-documents-count");
    var countText = countEl ? countEl.textContent : "all";
    var docCount = parseInt(countText) || "all";

    var confirmed = await _showDeleteAllModal(docCount);
    if (!confirmed) return;

    var btn = document.getElementById("delete-all-docs-btn");
    if (btn) {
        btn.disabled = true;
        btn.textContent = "Deleting...";
    }

    try {
        var response = await fetch(API_URL + "/documents/all/bulk", {
            method: "DELETE"
        });

        if (!response.ok) {
            throw new Error("Bulk delete failed (" + response.status + ")");
        }

        var data = await response.json();

        // Clear local state
        selectedDocumentIds.clear();
        uploadedDocuments = [];

        renderDocuments();
        updateCompareButton();
        loadMyDocuments();

        setStatus(data.message || "All documents deleted.");

    } catch (e) {
        console.error("Bulk delete failed:", e);
        setStatus("Failed to delete all: " + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<span class="material-symbols-outlined" style="font-size:16px;">delete_sweep</span> Delete All';
        }
    }
}

/* =========================================================
   COMPARE BUTTON STATE
   ========================================================= */

function updateCompareButton() {
    var btn = document.getElementById("compare-selected-btn");
    if (btn) {
        btn.disabled = selectedDocumentIds.size < 2;
    }
}


/* =========================================================
   INITIAL LOAD
   ========================================================= */

document.addEventListener("DOMContentLoaded", function() {
    loadMyDocuments();

    // Wire up the My Documents panel upload input
    var libUpload = document.getElementById("document-upload-library");
    if (libUpload) {
        libUpload.addEventListener("change", async function() {
            var files = Array.from(libUpload.files);
            if (!files.length) return;

            setStatus("");

            // Show progress (reuse inline progress if available)
            if (typeof _showUploadProgress === "function") {
                _showUploadProgress(files);
            }

            for (var i = 0; i < files.length; i++) {
                try {
                    var doc = await uploadFileWithProgress(files[i], (function(idx) {
                        return function(phase, percent, loadedBytes) {
                            if (typeof _updateUploadProgress === "function") {
                                _updateUploadProgress(idx, phase, percent, loadedBytes);
                            }
                        };
                    })(i));

                    uploadedDocuments.push(doc);
                    if (doc.id) selectedDocumentIds.add(doc.id);
                } catch (e) {
                    if (typeof _updateUploadProgress === "function") {
                        _updateUploadProgress(i, "error", 0, 0);
                    }
                    alert("Failed to upload " + files[i].name + ": " + e.message);
                }
            }

            renderDocuments();
            loadMyDocuments();
            setStatus("");

            // Fade out progress
            if (typeof _clearUploadProgress === "function") {
                setTimeout(_clearUploadProgress, 2000);
            }

            libUpload.value = "";
        });
    }
});
