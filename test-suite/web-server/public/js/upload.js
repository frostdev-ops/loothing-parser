// Upload JavaScript for WoW Combat Log Parser Test Suite

class UploadManager {
  constructor() {
    this.socket = null;
    this.currentUpload = null;
    this.connectionStatus = document.getElementById("connection-status");

    // Form elements
    this.uploadForm = document.getElementById("upload-form");
    this.fileInput = document.getElementById("combat-log");
    this.fileUploadZone = document.getElementById("file-upload-zone");
    this.uploadPlaceholder = document.getElementById("upload-placeholder");
    this.fileInfo = document.getElementById("file-info");
    this.removeFileBtn = document.getElementById("remove-file");
    this.uploadBtn = document.getElementById("upload-btn");

    // Progress elements
    this.uploadProgress = document.getElementById("upload-progress");
    this.progressBar = document.getElementById("progress-bar");
    this.progressText = document.getElementById("progress-text");
    this.progressMessage = document.getElementById("progress-message");

    // Result elements
    this.uploadResult = document.getElementById("upload-result");

    // Recent uploads
    this.recentUploadsTable = document.getElementById("recent-uploads-tbody");
    this.refreshUploadsBtn = document.getElementById("refresh-uploads");

    this.initialize();
  }

  async initialize() {
    try {
      // Initialize WebSocket connection
      this.initializeWebSocket();

      // Set up event listeners
      this.setupEventListeners();

      // Load initial data
      await this.loadRecentUploads();
    } catch (error) {
      console.error("Upload manager initialization failed:", error);
      this.showError("Initialization failed", error.message);
    }
  }

  initializeWebSocket() {
    try {
      this.socket = io();

      this.socket.on("connect", () => {
        console.log("WebSocket connected");
        this.updateConnectionStatus("connected");
      });

      this.socket.on("disconnect", (reason) => {
        console.log("WebSocket disconnected:", reason);
        this.updateConnectionStatus("disconnected");
      });

      this.socket.on("reconnect", () => {
        console.log("WebSocket reconnected");
        this.updateConnectionStatus("connected");
      });

      this.socket.on("upload-progress", (data) => {
        this.handleUploadProgress(data);
      });

      this.socket.on("upload-complete", (data) => {
        this.handleUploadComplete(data);
      });

      this.socket.on("upload-error", (data) => {
        this.handleUploadError(data);
      });

      this.socket.on("parsing-progress", (data) => {
        this.handleParsingProgress(data);
      });
    } catch (error) {
      console.error("WebSocket initialization failed:", error);
      this.updateConnectionStatus("disconnected");
    }
  }

  setupEventListeners() {
    // Form submission
    if (this.uploadForm) {
      this.uploadForm.addEventListener("submit", (e) => {
        e.preventDefault();
        this.handleUpload();
      });
    }

    // File input change
    if (this.fileInput) {
      this.fileInput.addEventListener("change", (e) => {
        this.handleFileSelect(e.target.files);
      });
    }

    // Drag and drop
    if (this.fileUploadZone) {
      this.fileUploadZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        this.fileUploadZone.classList.add("dragover");
      });

      this.fileUploadZone.addEventListener("dragleave", (e) => {
        e.preventDefault();
        this.fileUploadZone.classList.remove("dragover");
      });

      this.fileUploadZone.addEventListener("drop", (e) => {
        e.preventDefault();
        this.fileUploadZone.classList.remove("dragover");
        this.handleFileSelect(e.dataTransfer.files);
      });

      this.fileUploadZone.addEventListener("click", () => {
        if (this.fileInput && !this.fileInput.files.length) {
          this.fileInput.click();
        }
      });
    }

    // Remove file button
    if (this.removeFileBtn) {
      this.removeFileBtn.addEventListener("click", () => {
        this.clearFileSelection();
      });
    }

    // Refresh uploads button
    if (this.refreshUploadsBtn) {
      this.refreshUploadsBtn.addEventListener("click", () => {
        this.loadRecentUploads();
      });
    }
  }

  handleFileSelect(files) {
    if (!files || files.length === 0) return;

    const file = files[0];

    // Validate file
    if (!this.validateFile(file)) return;

    // Update UI
    this.showFileInfo(file);
    this.enableUploadButton();

    // Clear previous results
    this.hideProgress();
    this.hideResult();
  }

  validateFile(file) {
    const maxSize = 500 * 1024 * 1024; // 500MB
    const allowedTypes = [".txt", ".log"];

    // Check file size
    if (file.size > maxSize) {
      this.showError(
        "File too large",
        `File size (${this.formatFileSize(file.size)}) exceeds maximum allowed size (500MB)`,
      );
      return false;
    }

    // Check file type
    const fileExt = "." + file.name.split(".").pop().toLowerCase();
    if (!allowedTypes.includes(fileExt)) {
      this.showError(
        "Invalid file type",
        `Please select a .txt or .log file. Selected: ${fileExt}`,
      );
      return false;
    }

    return true;
  }

  showFileInfo(file) {
    if (!this.fileInfo) return;

    const fileName = document.getElementById("file-name");
    const fileSize = document.getElementById("file-size");

    if (fileName) fileName.textContent = file.name;
    if (fileSize) fileSize.textContent = this.formatFileSize(file.size);

    // Show file info, hide placeholder
    this.uploadPlaceholder?.classList.add("d-none");
    this.fileInfo.classList.remove("d-none");
  }

  clearFileSelection() {
    if (this.fileInput) {
      this.fileInput.value = "";
    }

    // Hide file info, show placeholder
    this.fileInfo?.classList.add("d-none");
    this.uploadPlaceholder?.classList.remove("d-none");

    this.disableUploadButton();
    this.hideProgress();
    this.hideResult();
  }

  enableUploadButton() {
    if (this.uploadBtn) {
      this.uploadBtn.disabled = false;
    }
  }

  disableUploadButton() {
    if (this.uploadBtn) {
      this.uploadBtn.disabled = true;
    }
  }

  async handleUpload() {
    try {
      if (!this.fileInput?.files?.[0]) {
        this.showError("No file selected", "Please select a combat log file");
        return;
      }

      const file = this.fileInput.files[0];
      const formData = new FormData();

      // Add file
      formData.append("combatLog", file);

      // Add other form data
      const guildId = document.getElementById("guild-id")?.value || "1";
      const guildName = document.getElementById("guild-name")?.value || "";
      const description = document.getElementById("description")?.value || "";

      formData.append("guildId", guildId);
      if (guildName) formData.append("guildName", guildName);
      if (description) formData.append("description", description);

      // Show progress
      this.showProgress();
      this.disableUploadButton();
      this.hideResult();

      // Create upload tracking
      this.currentUpload = {
        filename: file.name,
        size: file.size,
        startTime: Date.now(),
      };

      // Start upload
      const response = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(
          errorData.error ||
            `Upload failed: ${response.status} ${response.statusText}`,
        );
      }

      const result = await response.json();
      this.handleUploadSuccess(result);
    } catch (error) {
      console.error("Upload error:", error);
      this.handleUploadError({ error: error.message });
    }
  }

  handleUploadProgress(data) {
    if (data.filename !== this.currentUpload?.filename) return;

    console.log("Upload progress:", data);

    this.updateProgress(data.progress, `Uploading: ${data.progress}%`);
  }

  handleParsingProgress(data) {
    if (data.filename !== this.currentUpload?.filename) return;

    console.log("Parsing progress:", data);

    const message = data.stage
      ? `${data.stage}: ${data.progress}%`
      : `Parsing: ${data.progress}%`;
    this.updateProgress(data.progress, message);
  }

  handleUploadComplete(data) {
    console.log("Upload complete:", data);

    this.updateProgress(100, "Processing complete!");
    this.handleUploadSuccess(data);
  }

  handleUploadSuccess(data) {
    console.log("Upload success:", data);

    this.hideProgress();
    this.showResult(
      "success",
      "Upload successful!",
      `
      <div class="mb-3">
        <strong>File:</strong> ${this.escapeHtml(data.filename || this.currentUpload?.filename)}
      </div>
      ${data.uploadId ? `<div class="mb-3"><strong>Upload ID:</strong> ${data.uploadId}</div>` : ""}
      ${data.encounters ? `<div class="mb-3"><strong>Encounters found:</strong> ${data.encounters}</div>` : ""}
      ${data.events ? `<div class="mb-3"><strong>Events processed:</strong> ${data.events.toLocaleString()}</div>` : ""}
      <div class="mt-3">
        <a href="/" class="btn btn-primary btn-sm me-2">
          <i class="fas fa-chart-line me-1"></i>
          View Dashboard
        </a>
        <button class="btn btn-outline-secondary btn-sm" onclick="uploadManager.clearFileSelection()">
          <i class="fas fa-upload me-1"></i>
          Upload Another
        </button>
      </div>
    `,
    );

    this.enableUploadButton();
    this.loadRecentUploads();
    this.currentUpload = null;
  }

  handleUploadError(data) {
    console.error("Upload error:", data);

    this.hideProgress();
    this.showResult(
      "error",
      "Upload failed",
      `
      <div class="mb-3">
        <strong>Error:</strong> ${this.escapeHtml(data.error)}
      </div>
      ${data.details ? `<div class="mb-3"><small class="text-muted">${this.escapeHtml(data.details)}</small></div>` : ""}
      <div class="mt-3">
        <button class="btn btn-primary btn-sm" onclick="uploadManager.retryUpload()">
          <i class="fas fa-redo me-1"></i>
          Retry Upload
        </button>
      </div>
    `,
    );

    this.enableUploadButton();
    this.currentUpload = null;
  }

  retryUpload() {
    this.hideResult();
    this.handleUpload();
  }

  showProgress() {
    this.uploadProgress?.classList.remove("d-none");
    this.updateProgress(0, "Starting upload...");
  }

  hideProgress() {
    this.uploadProgress?.classList.add("d-none");
  }

  updateProgress(percent, message) {
    if (this.progressBar) {
      this.progressBar.style.width = `${percent}%`;
      this.progressBar.setAttribute("aria-valuenow", percent);
    }

    if (this.progressText) {
      this.progressText.textContent = `${Math.round(percent)}%`;
    }

    if (this.progressMessage && message) {
      this.progressMessage.textContent = message;
    }
  }

  showResult(type, title, content) {
    if (!this.uploadResult) return;

    const alertClass = type === "success" ? "alert-success" : "alert-danger";
    const iconClass =
      type === "success" ? "fas fa-check-circle" : "fas fa-exclamation-circle";

    this.uploadResult.innerHTML = `
      <div class="alert ${alertClass}" role="alert">
        <h5 class="alert-heading">
          <i class="${iconClass} me-2"></i>
          ${title}
        </h5>
        ${content}
      </div>
    `;

    this.uploadResult.classList.remove("d-none");
  }

  hideResult() {
    this.uploadResult?.classList.add("d-none");
  }

  showError(title, message) {
    this.showResult("error", title, `<div>${this.escapeHtml(message)}</div>`);
  }

  async loadRecentUploads() {
    try {
      if (!this.recentUploadsTable) return;

      // Show loading state
      this.recentUploadsTable.innerHTML = `
        <tr>
          <td colspan="6" class="text-center">
            <div class="spinner-border spinner-border-sm me-2" role="status">
              <span class="visually-hidden">Loading...</span>
            </div>
            Loading recent uploads...
          </td>
        </tr>
      `;

      const response = await fetch("/api/upload/recent?limit=10");

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();

      if (!data.uploads || data.uploads.length === 0) {
        this.recentUploadsTable.innerHTML = `
          <tr>
            <td colspan="6" class="text-center text-muted">
              <i class="fas fa-inbox me-2"></i>
              No recent uploads found
            </td>
          </tr>
        `;
        return;
      }

      // Clear and populate table
      this.recentUploadsTable.innerHTML = "";

      data.uploads.forEach((upload) => {
        const row = this.createUploadRow(upload);
        this.recentUploadsTable.appendChild(row);
      });
    } catch (error) {
      console.error("Failed to load recent uploads:", error);
      if (this.recentUploadsTable) {
        this.recentUploadsTable.innerHTML = `
          <tr>
            <td colspan="6" class="text-center text-danger">
              <i class="fas fa-exclamation-triangle me-2"></i>
              Failed to load uploads: ${error.message}
            </td>
          </tr>
        `;
      }
    }
  }

  createUploadRow(upload) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>
        <strong>${this.escapeHtml(upload.filename || "Unknown")}</strong>
        ${upload.description ? `<br><small class="text-muted">${this.escapeHtml(upload.description)}</small>` : ""}
      </td>
      <td>${upload.file_size_bytes ? this.formatFileSize(upload.file_size_bytes) : "-"}</td>
      <td>${this.escapeHtml(upload.guild_name || upload.guild_id || "-")}</td>
      <td>
        <span class="badge ${this.getStatusBadgeClass(upload.status)}">
          ${this.escapeHtml(upload.status || "Unknown")}
        </span>
      </td>
      <td>${upload.upload_time ? this.formatDateTime(upload.upload_time) : "-"}</td>
      <td>
        <div class="btn-group btn-group-sm" role="group">
          ${
            upload.status === "completed"
              ? `
            <button type="button" class="btn btn-outline-primary" onclick="uploadManager.viewUpload('${upload.id}')">
              <i class="fas fa-eye"></i>
            </button>
          `
              : ""
          }
          <button type="button" class="btn btn-outline-danger" onclick="uploadManager.deleteUpload('${upload.id}')">
            <i class="fas fa-trash"></i>
          </button>
        </div>
      </td>
    `;
    return row;
  }

  updateConnectionStatus(status) {
    if (!this.connectionStatus) return;

    this.connectionStatus.className = `badge ${status === "connected" ? "bg-success" : "bg-danger"}`;
    this.connectionStatus.innerHTML = `
      <i class="fas fa-circle"></i>
      ${status === "connected" ? "Connected" : "Disconnected"}
    `;
  }

  // Action handlers
  viewUpload(uploadId) {
    // TODO: Implement upload detail view
    console.log("View upload:", uploadId);
    // For now, redirect to dashboard
    window.location.href = "/";
  }

  async deleteUpload(uploadId) {
    if (!confirm("Are you sure you want to delete this upload?")) return;

    try {
      const response = await fetch(`/api/upload/${uploadId}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      // Refresh the list
      this.loadRecentUploads();
      this.showResult(
        "success",
        "Upload deleted",
        "The upload has been successfully deleted.",
      );
    } catch (error) {
      console.error("Failed to delete upload:", error);
      this.showError("Delete failed", error.message);
    }
  }

  // Utility functions
  escapeHtml(unsafe) {
    if (typeof unsafe !== "string") return unsafe;
    return unsafe
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  formatFileSize(bytes) {
    if (bytes === 0) return "0 Bytes";

    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  }

  formatDateTime(dateStr) {
    try {
      const date = new Date(dateStr);
      return date.toLocaleString();
    } catch (error) {
      return dateStr;
    }
  }

  getStatusBadgeClass(status) {
    const statusMap = {
      uploaded: "bg-info",
      processing: "bg-warning",
      completed: "bg-success",
      failed: "bg-danger",
      cancelled: "bg-secondary",
    };
    return statusMap[status] || "bg-secondary";
  }
}

// Initialize upload manager when DOM is loaded
document.addEventListener("DOMContentLoaded", () => {
  window.uploadManager = new UploadManager();
});

// Handle page visibility changes
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && window.uploadManager) {
    window.uploadManager.loadRecentUploads();
  }
});
