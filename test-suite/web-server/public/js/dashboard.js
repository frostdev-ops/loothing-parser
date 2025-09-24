// Dashboard JavaScript for WoW Combat Log Parser Test Suite

class Dashboard {
  constructor() {
    this.socket = null;
    this.connectionStatus = document.getElementById("connection-status");
    this.activityFeed = document.getElementById("activity-feed");
    this.refreshEncountersBtn = document.getElementById("refresh-encounters");
    this.encounterstable = document.getElementById("encounters-table");

    this.stats = {
      dbEncounters: document.getElementById("db-encounters-count"),
      influxEvents: document.getElementById("influx-events-count"),
      dbCharacters: document.getElementById("db-characters-count"),
      wsConnections: document.getElementById("ws-connections-count"),
    };

    this.dbStatus = {
      postgres: document.getElementById("postgres-status"),
      influxdb: document.getElementById("influxdb-status"),
      redis: document.getElementById("redis-status"),
    };

    this.initialize();
  }

  async initialize() {
    try {
      // Initialize WebSocket connection
      this.initializeWebSocket();

      // Set up event listeners
      this.setupEventListeners();

      // Load initial data
      await this.loadInitialData();

      // Start periodic updates
      this.startPeriodicUpdates();

      // Update current time display
      this.updateCurrentTime();
      setInterval(() => this.updateCurrentTime(), 1000);
    } catch (error) {
      console.error("Dashboard initialization failed:", error);
      this.addActivity("error", "Dashboard initialization failed", new Date());
    }
  }

  initializeWebSocket() {
    try {
      this.socket = io();

      this.socket.on("connect", () => {
        console.log("WebSocket connected");
        this.updateConnectionStatus("connected");
        this.addActivity("success", "Connected to server", new Date());

        // Join general updates room
        this.socket.emit("join-guild", 1);
      });

      this.socket.on("disconnect", (reason) => {
        console.log("WebSocket disconnected:", reason);
        this.updateConnectionStatus("disconnected");
        this.addActivity("danger", `Disconnected: ${reason}`, new Date());
      });

      this.socket.on("reconnect", () => {
        console.log("WebSocket reconnected");
        this.updateConnectionStatus("connected");
        this.addActivity("success", "Reconnected to server", new Date());
      });

      this.socket.on("system-event", (data) => {
        this.handleSystemEvent(data);
      });

      this.socket.on("encounter-update", (data) => {
        this.handleEncounterUpdate(data);
      });

      this.socket.on("upload-progress", (data) => {
        this.handleUploadProgress(data);
      });

      this.socket.on("error", (error) => {
        console.error("WebSocket error:", error);
        this.addActivity("danger", `WebSocket error: ${error}`, new Date());
      });
    } catch (error) {
      console.error("WebSocket initialization failed:", error);
      this.updateConnectionStatus("disconnected");
    }
  }

  setupEventListeners() {
    // Refresh encounters button
    if (this.refreshEncountersBtn) {
      this.refreshEncountersBtn.addEventListener("click", () => {
        this.loadEncounters();
        this.addActivity("info", "Refreshing encounters list", new Date());
      });
    }

    // Auto-refresh on visibility change
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) {
        this.loadInitialData();
      }
    });
  }

  async loadInitialData() {
    try {
      // Load system statistics
      await this.loadSystemStats();

      // Load encounters
      await this.loadEncounters();

      // Load database status
      await this.checkDatabaseStatus();
    } catch (error) {
      console.error("Failed to load initial data:", error);
      this.addActivity("danger", "Failed to load dashboard data", new Date());
    }
  }

  async loadSystemStats() {
    try {
      const response = await fetch("/api/metrics/stats");

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const stats = await response.json();

      // Update stat cards
      if (stats.database) {
        this.stats.dbEncounters.textContent = stats.database.encounters || "-";
        this.stats.dbCharacters.textContent = stats.database.characters || "-";
      }

      if (stats.influxdb) {
        this.stats.influxEvents.textContent = stats.influxdb.events || "-";
      }

      // WebSocket connections will be updated via socket events
    } catch (error) {
      console.error("Failed to load system stats:", error);
      Object.values(this.stats).forEach((el) => (el.textContent = "Error"));
    }
  }

  async loadEncounters() {
    try {
      const tbody = this.encounterstable.querySelector("tbody");

      // Show loading state
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center">
            <div class="spinner-border spinner-border-sm me-2" role="status">
              <span class="visually-hidden">Loading...</span>
            </div>
            Loading encounters...
          </td>
        </tr>
      `;

      const response = await fetch(
        "/api/encounters?limit=10&sort=start_time&order=desc",
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();

      if (!data.encounters || data.encounters.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="7" class="text-center text-muted">
              <i class="fas fa-inbox me-2"></i>
              No encounters found. Upload a combat log to get started.
            </td>
          </tr>
        `;
        return;
      }

      // Clear and populate table
      tbody.innerHTML = "";

      data.encounters.forEach((encounter) => {
        const row = this.createEncounterRow(encounter);
        tbody.appendChild(row);
      });
    } catch (error) {
      console.error("Failed to load encounters:", error);
      const tbody = this.encounterstable.querySelector("tbody");
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center text-danger">
            <i class="fas fa-exclamation-triangle me-2"></i>
            Failed to load encounters: ${error.message}
          </td>
        </tr>
      `;
    }
  }

  createEncounterRow(encounter) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>
        <strong>${this.escapeHtml(encounter.encounter_name || "Unknown")}</strong>
        ${encounter.encounter_id ? `<br><small class="text-muted">ID: ${encounter.encounter_id}</small>` : ""}
      </td>
      <td>${this.escapeHtml(encounter.zone_name || "-")}</td>
      <td>
        <span class="badge bg-${this.getDifficultyColor(encounter.difficulty)}">
          ${this.escapeHtml(encounter.difficulty || "Unknown")}
        </span>
      </td>
      <td>${encounter.duration_seconds ? this.formatDuration(encounter.duration_seconds) : "-"}</td>
      <td>
        <span class="badge ${encounter.success ? "status-success" : "status-failed"}">
          <i class="fas fa-${encounter.success ? "check" : "times"} me-1"></i>
          ${encounter.success ? "Success" : "Failed"}
        </span>
      </td>
      <td>
        ${encounter.start_time ? this.formatDateTime(encounter.start_time) : "-"}
      </td>
      <td>
        <div class="btn-group btn-group-sm" role="group">
          <button type="button" class="btn btn-outline-primary" onclick="dashboard.viewEncounter(${encounter.id})">
            <i class="fas fa-eye"></i>
          </button>
          <button type="button" class="btn btn-outline-info" onclick="dashboard.viewMetrics(${encounter.id})">
            <i class="fas fa-chart-bar"></i>
          </button>
        </div>
      </td>
    `;
    return row;
  }

  async checkDatabaseStatus() {
    try {
      const response = await fetch("/api/health");

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const health = await response.json();

      // Update database status indicators
      this.updateDbStatus("postgres", health.postgres);
      this.updateDbStatus("influxdb", health.influxdb);
      this.updateDbStatus("redis", health.redis);
    } catch (error) {
      console.error("Failed to check database status:", error);

      // Set all to unknown status
      Object.keys(this.dbStatus).forEach((db) => {
        this.updateDbStatus(db, false);
      });
    }
  }

  updateDbStatus(dbName, isHealthy) {
    const statusEl = this.dbStatus[dbName];
    if (!statusEl) return;

    const icon = statusEl.querySelector("i");
    icon.className = `fas fa-circle ${isHealthy ? "text-success" : "text-danger"}`;
  }

  updateConnectionStatus(status) {
    if (!this.connectionStatus) return;

    this.connectionStatus.className = `badge ${status === "connected" ? "bg-success" : "bg-danger"}`;
    this.connectionStatus.innerHTML = `
      <i class="fas fa-circle"></i>
      ${status === "connected" ? "Connected" : "Disconnected"}
    `;
  }

  handleSystemEvent(data) {
    console.log("System event:", data);

    switch (data.event) {
      case "status-update":
        if (data.data.connections !== undefined) {
          this.stats.wsConnections.textContent = data.data.connections;
        }
        break;

      case "database-update":
        this.loadSystemStats();
        break;

      case "encounter-processed":
        this.addActivity(
          "success",
          `New encounter processed: ${data.data.name}`,
          data.timestamp,
        );
        this.loadEncounters();
        break;
    }
  }

  handleEncounterUpdate(data) {
    console.log("Encounter update:", data);
    this.addActivity(
      "info",
      `Encounter updated: ${data.encounter_name}`,
      data.timestamp,
    );
    this.loadEncounters();
  }

  handleUploadProgress(data) {
    console.log("Upload progress:", data);
    this.addActivity(
      "info",
      `Upload progress: ${data.filename} (${data.progress}%)`,
      data.timestamp,
    );
  }

  addActivity(type, message, timestamp) {
    if (!this.activityFeed) return;

    const iconClass =
      {
        success: "fas fa-check-circle text-success",
        info: "fas fa-info-circle text-info",
        warning: "fas fa-exclamation-triangle text-warning",
        danger: "fas fa-exclamation-circle text-danger",
        error: "fas fa-exclamation-circle text-danger",
      }[type] || "fas fa-info-circle text-info";

    const activityItem = document.createElement("div");
    activityItem.className = "activity-item";
    activityItem.innerHTML = `
      <i class="${iconClass}"></i>
      <span>${this.escapeHtml(message)}</span>
      <small class="text-muted ms-auto">${this.formatTime(timestamp)}</small>
    `;

    // Add to top of feed
    const firstItem = this.activityFeed.firstChild;
    if (firstItem) {
      this.activityFeed.insertBefore(activityItem, firstItem);
    } else {
      this.activityFeed.appendChild(activityItem);
    }

    // Limit to 50 items
    const items = this.activityFeed.querySelectorAll(".activity-item");
    if (items.length > 50) {
      items[items.length - 1].remove();
    }
  }

  startPeriodicUpdates() {
    // Update stats every 30 seconds
    setInterval(() => {
      if (!document.hidden && this.socket && this.socket.connected) {
        this.loadSystemStats();
      }
    }, 30000);

    // Check database status every 60 seconds
    setInterval(() => {
      if (!document.hidden) {
        this.checkDatabaseStatus();
      }
    }, 60000);
  }

  updateCurrentTime() {
    const timeEl = document.getElementById("current-time");
    if (timeEl) {
      timeEl.textContent = this.formatTime(new Date());
    }
  }

  // Action handlers
  viewEncounter(encounterId) {
    // TODO: Implement encounter detail view
    console.log("View encounter:", encounterId);
    this.addActivity("info", `Viewing encounter ${encounterId}`, new Date());
  }

  viewMetrics(encounterId) {
    // TODO: Implement metrics view
    console.log("View metrics:", encounterId);
    this.addActivity(
      "info",
      `Loading metrics for encounter ${encounterId}`,
      new Date(),
    );
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

  formatDateTime(dateStr) {
    try {
      const date = new Date(dateStr);
      return date.toLocaleString();
    } catch (error) {
      return dateStr;
    }
  }

  formatTime(dateStr) {
    try {
      const date = new Date(dateStr);
      return date.toLocaleTimeString();
    } catch (error) {
      return dateStr;
    }
  }

  formatDuration(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }

  getDifficultyColor(difficulty) {
    const diffMap = {
      LFR: "success",
      Normal: "primary",
      Heroic: "warning",
      Mythic: "danger",
    };
    return diffMap[difficulty] || "secondary";
  }
}

// Initialize dashboard when DOM is loaded
document.addEventListener("DOMContentLoaded", () => {
  window.dashboard = new Dashboard();
});

// Handle page visibility changes
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && window.dashboard) {
    window.dashboard.loadInitialData();
  }
});
