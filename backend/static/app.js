const $ = (id) => document.getElementById(id);

let applications = [];
let deployments = [];
let incidents = [];

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;",
        '"': "&quot;", "'": "&#39;"
    })[char]);
}

function showMessage(message, type = "success") {
    const box = $("message");
    box.textContent = message;
    box.className = `message show ${type}`;
    setTimeout(() => box.classList.remove("show"), 4000);
}

function pill(value) {
    const text = String(value || "Unknown");
    const normalized = text.toLowerCase().replaceAll(" ", "-");
    let cls = normalized;

    if (["successful", "success"].includes(normalized)) cls = "success";
    if (["open"].includes(normalized)) cls = "open";
    if (["resolved", "closed"].includes(normalized)) cls = "resolved";
    if (["failed", "critical"].includes(normalized)) cls = normalized;
    if (["healthy"].includes(normalized)) cls = "healthy";
    if (["unhealthy"].includes(normalized)) cls = "unhealthy";
    if (["high"].includes(normalized)) cls = "high";

    return `<span class="pill ${escapeHtml(cls)}">${escapeHtml(text)}</span>`;
}

function formatDate(value) {
    if (!value) return "\u2014";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? escapeHtml(value) : date.toLocaleString();
}

async function api(path, options = {}) {
    const response = await fetch(path, {
        ...options,
        headers: {
            ...(options.body ? { "Content-Type": "application/json" } : {}),
            ...(options.headers || {})
        }
    });

    if (!response.ok) {
        const body = await response.text();
        throw new Error(`HTTP ${response.status}: ${body.slice(0, 250)}`);
    }

    if (response.status === 204) return null;
    return response.json();
}

function populateApplicationSelects() {
    for (const id of ["deploymentApp", "incidentApp"]) {
        const select = $(id);
        const previous = select.value;
        select.innerHTML = applications.length
            ? applications.map(app =>
                `<option value="${app.id}">${escapeHtml(app.name)} (#${app.id})</option>`
              ).join("")
            : '<option value="">Create an application first</option>';

        if (applications.some(app => String(app.id) === previous)) {
            select.value = previous;
        }
    }
}

function renderApplications() {
    $("appCount").textContent = applications.length;

    $("applicationsTable").innerHTML = applications.length
        ? applications.map(app => `
            <tr>
                <td>
                    <span class="app-name">${escapeHtml(app.name)}</span>
                    <span class="app-url" title="${escapeHtml(app.url)}">${escapeHtml(app.url)}</span>
                </td>
                <td>${escapeHtml(app.environment || "Development")}</td>
                <td>${pill(app.status || "Registered")}</td>
                <td>${formatDate(app.created_at)}</td>
                <td><button class="health-check-btn" type="button" data-health-check="${app.id}">Check health</button></td>
            </tr>
        `).join("")
        : '<tr><td colspan="5" class="empty">No applications yet. Add your first application.</td></tr>';

    populateApplicationSelects();
}

function renderDeployments() {
    $("deploymentCount").textContent = deployments.length;

    $("deploymentsList").innerHTML = deployments.length
        ? [...deployments].reverse().slice(0, 8).map(item => {
            const app = applications.find(a => a.id === item.application_id);
            return `
                <div class="record">
                    <div class="record-top">
                        <span class="record-title">${escapeHtml(app?.name || `Application #${item.application_id}`)}</span>
                        ${pill(item.status)}
                    </div>
                    <div class="record-meta">Version ${escapeHtml(item.version)} Â· ${formatDate(item.deployed_at)}</div>
                </div>`;
        }).join("")
        : '<div class="empty">No deployment records yet.</div>';
}

function renderIncidents() {
    const open = incidents.filter(item =>
        !["resolved", "closed"].includes(String(item.status || "").toLowerCase())
    );
    const resolved = incidents.length - open.length;

    $("incidentCount").textContent = open.length;
    $("resolvedCount").textContent = resolved;

    $("incidentsList").innerHTML = incidents.length
        ? [...incidents].reverse().slice(0, 10).map(item => {
            const app = applications.find(a => a.id === item.application_id);
            const isOpen = !["resolved", "closed"].includes(String(item.status || "").toLowerCase());

            return `
                <div class="record">
                    <div class="record-top">
                        <span class="record-title">${escapeHtml(item.title)}</span>
                        ${pill(item.severity)}
                    </div>
                    <div class="record-meta">
                        ${escapeHtml(app?.name || `Application #${item.application_id}`)}
                        Â· ${pill(item.status)}
                        Â· ${formatDate(item.created_at)}
                    </div>
                    ${isOpen ? `<button class="resolve-btn" data-resolve="${item.id}">\u2713 Resolve incident</button>` : ""}
                </div>`;
        }).join("")
        : '<div class="empty">No incidents recorded. Your incident history will appear here.</div>';
}

async function loadDashboard() {
    $("refreshBtn").disabled = true;
    $("refreshBtn").textContent = "Loading...";

    try {
        const [appData, deploymentData, incidentData] = await Promise.all([
            api("/applications"),
            api("/deployments"),
            api("/incidents")
        ]);

        applications = appData;
        deployments = deploymentData;
        incidents = incidentData;

        renderApplications();
        renderDeployments();
        renderIncidents();
    } catch (error) {
        showMessage(`Could not load dashboard data. Check that FastAPI is running. ${error.message}`, "error");
    } finally {
        $("refreshBtn").disabled = false;
        $("refreshBtn").textContent = "\u21bb  Refresh data";
    }
}

$("refreshBtn").addEventListener("click", loadDashboard);

document.querySelectorAll(".nav-item").forEach((link) => {
    link.addEventListener("click", (event) => {
        const target = document.getElementById(link.hash.slice(1));
        if (!target) return;

        event.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        history.replaceState(null, "", link.hash);
        document.querySelectorAll(".nav-item").forEach((item) => {
            item.classList.remove("active");
        });
        link.classList.add("active");
    });
});

$("showAppForm").addEventListener("click", () => $("appForm").classList.toggle("hidden"));
$("showDeploymentForm").addEventListener("click", () => { const form = $("deploymentForm"); form.hidden = !form.hidden; });
$("showIncidentForm").addEventListener("click", () => { const form = $("incidentForm"); form.hidden = !form.hidden; });

$("applicationsTable").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-health-check]");
    if (!button) return;

    const applicationId = button.dataset.healthCheck;
    button.disabled = true;
    button.textContent = "Checking...";

    try {
        const result = await api(`/applications/${applicationId}/health-check`, {
            method: "POST"
        });
        await loadDashboard();
        const statusCode = result.http_status_code ? ` (HTTP ${result.http_status_code})` : "";
        showMessage(
            `${result.application}: ${result.health}${statusCode}. ${result.message}`,
            result.health === "Healthy" ? "success" : "error"
        );
    } catch (error) {
        button.disabled = false;
        button.textContent = "Check health";
        showMessage(`Health check failed: ${error.message}`, "error");
    }
});

$("appForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);

    try {
        await api("/applications", {
            method: "POST",
            body: JSON.stringify({
                name: form.get("name"),
                url: form.get("url"),
                environment: form.get("environment")
            })
        });

        formElement.reset();
        formElement.hidden = true;
        showMessage("Application registered successfully.");
        await loadDashboard();
    } catch (error) {
        showMessage(`Could not create application: ${error.message}`, "error");
    }
});

$("deploymentForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);

    try {
        await api("/deployments", {
            method: "POST",
            body: JSON.stringify({
                application_id: Number(form.get("application_id")),
                version: form.get("version"),
                status: form.get("status")
            })
        });

        formElement.reset();
        formElement.hidden = true;
        showMessage("Deployment record saved.");
        await loadDashboard();
    } catch (error) {
        showMessage(`Could not save deployment: ${error.message}`, "error");
    }
});

$("incidentForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);

    try {
        await api("/incidents", {
            method: "POST",
            body: JSON.stringify({
                application_id: Number(form.get("application_id")),
                title: form.get("title"),
                severity: form.get("severity"),
                status: "Open"
            })
        });

        formElement.reset();
        formElement.hidden = true;
        showMessage("Incident created successfully.");
        await loadDashboard();
    } catch (error) {
        showMessage(`Could not create incident: ${error.message}`, "error");
    }
});

$("incidentsList").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-resolve]");
    if (!button) return;

    try {
        await api(`/incidents/${button.dataset.resolve}/resolve`, {
            method: "PATCH"
        });
        showMessage("Incident resolved.");
        await loadDashboard();
    } catch (error) {
        showMessage(`Could not resolve incident: ${error.message}`, "error");
    }
});

loadDashboard();



