// Helper to safely format numbers and prevent "Cannot read properties of null (reading 'toFixed')"
function formatNum(value, decimals = 4, fallback = "0.0000") {
    if (value === null || value === undefined || isNaN(Number(value))) {
        return fallback;
    }
    return Number(value).toFixed(decimals);
}

// Global state variables
let configData = [];
let selectedBusId = 1;
let chartInstances = {};
let simulationResults = null;
let validationCurrentPage = 1;
let configStatusSource = "default"; // "default" | "loaded:<filename>" | "custom"

function setConfigStatus(source, filename) {
    const label = document.getElementById("config-status-label");
    if (!label) return;
    if (source === "default") {
        configStatusSource = "default";
        label.textContent = "Default";
        label.style.color = "#4A5D4E";
    } else if (source === "loaded") {
        configStatusSource = "loaded";
        label.textContent = filename || "Yüklendi";
        label.style.color = "#1e6b3a";
    } else if (source === "custom") {
        if (configStatusSource === "custom") return; // already custom, skip redundant update
        configStatusSource = "custom";
        label.textContent = "Custom*";
        label.style.color = "#b45309";
    }
    sessionStorage.setItem("abm_dlmp_config_status", JSON.stringify({ source: configStatusSource, label: label.textContent }));
}

// Base case loads (1-indexed Bus IDs matching case33bw)
const BASE_LOADS = {
    1: { p: 0.0, q: 0.0 }, // Slack
    2: { p: 0.10, q: 0.06 },
    3: { p: 0.09, q: 0.04 },
    4: { p: 0.12, q: 0.08 },
    5: { p: 0.06, q: 0.03 },
    6: { p: 0.06, q: 0.02 },
    7: { p: 0.20, q: 0.10 },
    8: { p: 0.20, q: 0.10 },
    9: { p: 0.06, q: 0.02 },
    10: { p: 0.06, q: 0.02 },
    11: { p: 0.045, q: 0.03 },
    12: { p: 0.06, q: 0.035 },
    13: { p: 0.06, q: 0.035 },
    14: { p: 0.12, q: 0.08 },
    15: { p: 0.06, q: 0.01 },
    16: { p: 0.06, q: 0.02 },
    17: { p: 0.06, q: 0.02 },
    18: { p: 0.09, q: 0.04 },
    19: { p: 0.09, q: 0.04 },
    20: { p: 0.09, q: 0.04 },
    21: { p: 0.09, q: 0.04 },
    22: { p: 0.09, q: 0.04 },
    23: { p: 0.09, q: 0.05 },
    24: { p: 0.42, q: 0.20 },
    25: { p: 0.42, q: 0.20 },
    26: { p: 0.06, q: 0.025 },
    27: { p: 0.06, q: 0.025 },
    28: { p: 0.06, q: 0.02 },
    29: { p: 0.12, q: 0.07 },
    30: { p: 0.20, q: 0.60 },
    31: { p: 0.15, q: 0.07 },
    32: { p: 0.21, q: 0.10 },
    33: { p: 0.06, q: 0.04 }
};


// Theme colors matching style.css (Sage Green / Premium theme)
const COLOR_BACKGROUND = "#F4F3EF";
const COLOR_BORDER = "#D3D0C6";
const COLOR_TEXT_PRIMARY = "#2A3439";
const COLOR_SLACK = "#4A7C59";
const COLOR_LOAD = "#8E9A90";
const COLOR_DER = "#2E7D32";
const COLOR_PROSUMER = "#E65100";
const COLOR_SELECTED = "#8E24AA"; // purple outline for selected node
const COLOR_LINE = "#8E9A90";


// Coordinates mapping function (x: -1.25 to 1.25, y: 1 to 18)
const getSvgCoords = (x, y) => {
    // Width of SVG is 500. Center x=0 is at 250.
    const cx = 250 + x * 140;
    // Height is 800. Y ranges from 18 (top) to 1 (bottom).
    const cy = 30 + (18 - y) * 42;
    return { cx, cy };
};

// 33-Bus Coordinates List (0-indexed corresponds to Bus ID 1 to 33)
// Calculated directly from MATLAB's layered graph layout coordinates
const coords = [
    [0.25, 18],   // Bus 1
    [0.25, 17],   // Bus 2
    [-0.25, 16],  // Bus 3
    [-0.75, 15],  // Bus 4
    [-0.75, 14],  // Bus 5
    [-0.75, 13],  // Bus 6
    [-1.25, 12],  // Bus 7
    [-1.25, 11],  // Bus 8
    [-1.25, 10],  // Bus 9
    [-1.25, 9],   // Bus 10
    [-1.25, 8],   // Bus 11
    [-1.25, 7],   // Bus 12
    [-1.25, 6],   // Bus 13
    [-1.25, 5],   // Bus 14
    [-1.25, 4],   // Bus 15
    [-1.25, 3],   // Bus 16
    [-1.25, 2],   // Bus 17
    [-1.25, 1],   // Bus 18
    [1.25, 16],   // Bus 19
    [1.25, 15],   // Bus 20
    [1.25, 14],   // Bus 21
    [1.25, 13],   // Bus 22
    [0.25, 15],   // Bus 23
    [0.25, 14],   // Bus 24
    [0.25, 13],   // Bus 25
    [-0.25, 12],  // Bus 26
    [-0.25, 11],  // Bus 27
    [-0.25, 10],  // Bus 28
    [-0.25, 9],   // Bus 29
    [-0.25, 8],   // Bus 30
    [-0.25, 7],   // Bus 31
    [-0.25, 6],   // Bus 32
    [-0.25, 5]    // Bus 33
];





// Topology connections (1-based Bus IDs)
const lines = [
    [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 7], [7, 8], [8, 9], [9, 10], [10, 11], [11, 12], [12, 13], [13, 14], [14, 15], [15, 16], [16, 17], [17, 18],
    [2, 19], [19, 20], [20, 21], [21, 22],
    [3, 23], [23, 24], [24, 25],
    [6, 26], [26, 27], [27, 28], [28, 29], [29, 30], [30, 31], [31, 32], [32, 33]
];

document.addEventListener("DOMContentLoaded", () => {
    // Populate select bus selectors (1 to 33)
    const selectEditor = document.getElementById("editor-bus-id");
    const plotA = document.getElementById("plot-bus-a");
    const plotB = document.getElementById("plot-bus-b");
    const plotC = document.getElementById("plot-bus-c");

    for (let i = 1; i <= 33; i++) {
        const opt1 = document.createElement("option");
        opt1.value = i; opt1.textContent = i;
        selectEditor.appendChild(opt1);

        const optA = document.createElement("option");
        optA.value = i; optA.textContent = i;
        if (i === 2) optA.selected = true;
        plotA.appendChild(optA);

        const optB = document.createElement("option");
        optB.value = i; optB.textContent = i;
        if (i === 17) optB.selected = true;
        plotB.appendChild(optB);

        const optC = document.createElement("option");
        optC.value = i; optC.textContent = i;
        if (i === 33) optC.selected = true;
        plotC.appendChild(optC);
    }

    // Initialize config load after checking system startup (clears cache if backend restarted)
    checkSystemStartup().then(() => {
        fetchConfig();
    });

    // Event listeners
    selectEditor.addEventListener("change", (e) => selectBus(parseInt(e.target.value)));
    
    // Quick editor event listeners
    document.getElementById("bus-role").addEventListener("change", (e) => toggleEditorSubcards(e.target.value));
    document.getElementById("btn-apply-role").addEventListener("click", applyBusRoleSettings);

    // Plot synchronizers to trigger graph redraw immediately
    plotA.addEventListener("change", () => { drawTopology(); updateSelectedBusDetailsText(); if (typeof simulationResults !== 'undefined' && simulationResults) drawResultCharts(); });
    plotB.addEventListener("change", () => { drawTopology(); updateSelectedBusDetailsText(); if (typeof simulationResults !== 'undefined' && simulationResults) drawResultCharts(); });
    plotC.addEventListener("change", () => { drawTopology(); updateSelectedBusDetailsText(); if (typeof simulationResults !== 'undefined' && simulationResults) drawResultCharts(); });

    // Multipliers changes trigger text details update
    document.getElementById("time-select").addEventListener("change", updateSelectedBusDetailsText);
    document.getElementById("season-select").addEventListener("change", updateSelectedBusDetailsText);


    // Top action bar buttons
    document.getElementById("btn-simulate").addEventListener("click", runSimulation);
    document.getElementById("btn-save-config").addEventListener("click", () => {
        window.location.href = "/api/config/download";
    });
    document.getElementById("btn-load-config").addEventListener("click", () => {
        document.getElementById("config-file-uploader").click();
    });
    
    // Config loader file input
    document.getElementById("config-file-uploader").addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            uploadConfigFile(e.target.files[0]);
        }
    });

    // Excel results loader hidden uploader
    const resultsUploader = document.createElement("input");
    resultsUploader.type = "file";
    resultsUploader.accept = ".xlsx, .xls";
    resultsUploader.style.display = "none";
    document.body.appendChild(resultsUploader);

    document.getElementById("btn-load-excel").addEventListener("click", () => {
        resultsUploader.click();
    });

    resultsUploader.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            uploadResultsExcel(e.target.files[0]);
        }
    });

    // Reset button
    document.getElementById("btn-reset-roles").addEventListener("click", () => {
        if (confirm("Tüm bara rollerini ve sınırlarını varsayılana döndürmek istediğinize emin misiniz?")) {
            initDefaultConfig();
        }
    });

    // Error modal control buttons
    const hideErrModal = () => {
        const modal = document.getElementById("error-modal");
        if (modal) modal.style.display = "none";
    };
    const btnCloseModal = document.getElementById("btn-close-error-modal");
    const btnHideModal = document.getElementById("btn-hide-error-modal");
    const btnCopyError = document.getElementById("btn-copy-error");
    if (btnCloseModal) btnCloseModal.addEventListener("click", hideErrModal);
    if (btnHideModal) btnHideModal.addEventListener("click", hideErrModal);
    if (btnCopyError) {
        btnCopyError.addEventListener("click", () => {
            const pre = document.getElementById("error-details-pre");
            if (pre) {
                navigator.clipboard.writeText(pre.textContent).then(() => {
                    showToast("Hata detayları panoya kopyalandı!");
                }).catch(() => {
                    alert("Panoya kopyalanamadı.");
                });
            }
        });
    }

    // Scenario Generator toggle visual handler
    document.querySelectorAll("input[name='scenario_generator']").forEach(radio => {
        radio.addEventListener("change", () => {
            const val = document.querySelector("input[name='scenario_generator']:checked").value;
            document.getElementById("gen-label-matlab").style.background = val === "matlab" ? "#4A5D4E" : "";
            document.getElementById("gen-label-matlab").style.color = val === "matlab" ? "#fff" : "#3A474D";
            document.getElementById("gen-label-python").style.background = val === "python" ? "#4A5D4E" : "";
            document.getElementById("gen-label-python").style.color = val === "python" ? "#fff" : "#3A474D";
        });
    });

    // Table preview selector
    document.getElementById("preview-table-select").addEventListener("change", (e) => {
        const scWrapper = document.getElementById("preview-scenario-filter-wrapper");
        if (e.target.value === "summary") {
            scWrapper.style.display = "none";
        } else {
            scWrapper.style.display = "flex";
        }
        renderPreviewTable(e.target.value);
    });

    document.getElementById("preview-scenario-select").addEventListener("change", (e) => {
        const previewType = document.getElementById("preview-table-select").value;
        renderPreviewTable(previewType);
    });

    document.getElementById("btn-save-bulk-config").addEventListener("click", () => {
        if (syncTimeout) clearTimeout(syncTimeout);
        const statusEl = document.getElementById("bulk-save-status");
        if (statusEl) {
            statusEl.innerHTML = '<span style="color:#e65100; font-weight:bold;">● Kaydediliyor...</span>';
        }
        syncConfigToBackend(true);
    });

    document.getElementById("btn-val-prev").addEventListener("click", () => {
        validationCurrentPage--;
        renderValidationTablePage();
    });

    document.getElementById("btn-val-next").addEventListener("click", () => {
        validationCurrentPage++;
        renderValidationTablePage();
    });

    document.getElementById("btn-export-excel").addEventListener("click", () => {
        const outputFileName = document.getElementById("output-excel-file").value || "case33bw_dlmp_scenarios.xlsx";
        
        // Log to console
        const logArea = document.getElementById("console-log-area");
        if (logArea) {
            logArea.value += `\n[${new Date().toLocaleTimeString('tr-TR')}] Exported results to Excel: ${outputFileName}`;
            logArea.scrollTop = logArea.scrollHeight;
            sessionStorage.setItem("abm_dlmp_console_log", logArea.value);
        }
        
        window.location.href = `/api/download-results?filename=${encodeURIComponent(outputFileName)}`;
    });

    // Create Tooltip DOM
    const tooltip = document.createElement("div");
    tooltip.className = "custom-tooltip";
    document.body.appendChild(tooltip);
    window.appTooltip = tooltip;

    // Restore config status label if cached
    const savedConfigStatus = sessionStorage.getItem("abm_dlmp_config_status");
    if (savedConfigStatus) {
        try {
            const cs = JSON.parse(savedConfigStatus);
            configStatusSource = cs.source || "default";
            const label = document.getElementById("config-status-label");
            if (label && cs.label) {
                label.textContent = cs.label;
                if (cs.source === "loaded") label.style.color = "#1e6b3a";
                else if (cs.source === "custom") label.style.color = "#b45309";
                else label.style.color = "#4A5D4E";
            }
        } catch (e) { /* ignore */ }
    }

    // Restore simulation inputs if cached
    const savedInputs = sessionStorage.getItem("abm_dlmp_inputs");
    if (savedInputs) {
        try {
            const inputs = JSON.parse(savedInputs);
            if (inputs.scenarioCount !== undefined) document.getElementById("scenario-count").value = inputs.scenarioCount;
            if (inputs.randomSeed !== undefined) document.getElementById("random-seed").value = inputs.randomSeed;
            if (inputs.loadScaleRange !== undefined) document.getElementById("load-scale-range").value = inputs.loadScaleRange;
            if (inputs.timeSelect !== undefined) document.getElementById("time-select").value = inputs.timeSelect;
            if (inputs.seasonSelect !== undefined) document.getElementById("season-select").value = inputs.seasonSelect;
            if (inputs.policySelect !== undefined) document.getElementById("policy-select").value = inputs.policySelect;
            if (inputs.loadScalePdf !== undefined) document.getElementById("load-scale-pdf").value = inputs.loadScalePdf;
            if (inputs.offerPdf !== undefined) document.getElementById("offer-pdf").value = inputs.offerPdf;
            if (inputs.runValidationCheck !== undefined) document.getElementById("run-validation-check").checked = inputs.runValidationCheck;
            if (inputs.outputExcelFile !== undefined) document.getElementById("output-excel-file").value = inputs.outputExcelFile;
            
            if (inputs.plotBusA !== undefined) document.getElementById("plot-bus-a").value = inputs.plotBusA;
            if (inputs.plotBusB !== undefined) document.getElementById("plot-bus-b").value = inputs.plotBusB;
            if (inputs.plotBusC !== undefined) document.getElementById("plot-bus-c").value = inputs.plotBusC;
        } catch (e) {
            console.error("Error restoring inputs:", e);
        }
    }

    // Restore simulation results if cached
    const savedResults = sessionStorage.getItem("abm_dlmp_results");
    if (savedResults) {
        try {
            simulationResults = JSON.parse(savedResults);
            
            // Re-render components and charts
            document.getElementById("btn-export-excel").disabled = false;
            
            // Render results
            renderResultsTables();
            drawResultCharts();
            
            // Restore console logs and status
            const savedLog = sessionStorage.getItem("abm_dlmp_console_log");
            const savedStatus = sessionStorage.getItem("abm_dlmp_console_status");
            if (savedLog) document.getElementById("console-log-area").value = savedLog;
            if (savedStatus) document.getElementById("console-status-header").textContent = savedStatus;
        } catch (e) {
            console.error("Failed to parse saved simulation results.", e);
        }
    }

    // Initialize sidebar cards visibility
    updateContextControls("tab-topology");
});


// Toast notification
function showToast(message, type = "success") {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.className = `toast show ${type}`;
    setTimeout(() => {
        toast.className = "toast";
    }, 3000);
}

// Detailed Error Modal helper
function showDetailedError(title, details) {
    const modal = document.getElementById("error-modal");
    const pre = document.getElementById("error-details-pre");
    if (!modal || !pre) return;
    
    document.querySelector("#error-modal h3").textContent = `⚠️ ${title}`;
    pre.textContent = details;
    modal.style.display = "flex";
}

// Global exception interceptors for JavaScript crashes
window.onerror = function(message, source, lineno, colno, error) {
    const details = `JavaScript Error: ${message}\nSource: ${source}\nLine: ${lineno}:${colno}\n\nStack Trace:\n${error ? error.stack : 'N/A'}`;
    showDetailedError("Çalışma Zamanı Hatası (JS Crash)", details);
    return false; // let browser console print it too
};

window.onunhandledrejection = function(event) {
    const reason = event.reason;
    const details = `Unhandled Promise Rejection:\nReason: ${reason ? (reason.stack || reason.message || reason) : 'N/A'}`;
    showDetailedError("Promise Rejection (Beklenmedik Hata)", details);
};

// Check system startup ID to clear cache if backend restarted
async function checkSystemStartup() {
    try {
        const res = await fetch("/api/sysinfo");
        if (!res.ok) return;
        const info = await res.json();
        const localId = sessionStorage.getItem("abm_dlmp_startup_id");
        if (localId && localId !== info.startup_id) {
            console.log("Backend restarted. Clearing sessionStorage...");
            sessionStorage.clear();
            sessionStorage.setItem("abm_dlmp_startup_id", info.startup_id);
            // Trigger full reload to defaults
            window.location.reload();
            return;
        }
        sessionStorage.setItem("abm_dlmp_startup_id", info.startup_id);
    } catch (e) {
        console.error("System info fetch failed", e);
    }
}

// Fetch current in-memory config from server (checking sessionStorage first)
async function fetchConfig() {
    const savedConfig = sessionStorage.getItem("abm_dlmp_config");
    if (savedConfig) {
        try {
            configData = JSON.parse(savedConfig);
            drawTopology();
            renderBulkTable();
            selectBus(selectedBusId);
            // Synchronize with the backend in-memory config
            await fetch("/api/config/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(configData)
            });
            return;
        } catch (e) {
            console.error("Failed to parse saved config, loading from backend.", e);
        }
    }
    
    try {
        const res = await fetch("/api/config");
        configData = await res.json();
        sessionStorage.setItem("abm_dlmp_config", JSON.stringify(configData));
        drawTopology();
        renderBulkTable();
        selectBus(selectedBusId);
    } catch (err) {
        showToast("Konfigurasyon yuklenemedi.", "error");
    }
}

// Reset all roles locally
async function initDefaultConfig() {
    try {
        const response = await fetch("/api/config");
        const defaultData = await response.json();
        configData = defaultData.map(bus => {
            const b_id = bus.bus_id;
            return {
                bus_id: b_id,
                role: b_id === 1 ? "Slack/Grid" : "PQ Load",
                add_Pd_MW: 0.0,
                pf: b_id !== 1 ? 0.95 : 1.0,
                Vmin_pu: 0.90,
                Vmax_pu: 1.05,
                Pmin_MW: 0.0,
                Pmax_MW: b_id === 1 ? 10.0 : 0.0,
                Qmin_MVAr: b_id === 1 ? -10.0 : 0.0,
                Qmax_MVAr: b_id === 1 ? 10.0 : 0.0,
                c2_min: b_id === 1 ? 0.02 : 0.0,
                c2_max: b_id === 1 ? 0.02 : 0.0,
                c1_min: b_id === 1 ? 80.0 : 0.0,
                c1_max: b_id === 1 ? 80.0 : 0.0,
                c0: 0.0
            };
        });
        
        sessionStorage.setItem("abm_dlmp_config", JSON.stringify(configData));
        sessionStorage.removeItem("abm_dlmp_results");
        sessionStorage.removeItem("abm_dlmp_console_log");
        sessionStorage.removeItem("abm_dlmp_console_status");
        sessionStorage.removeItem("abm_dlmp_inputs");
        sessionStorage.removeItem("abm_dlmp_config_status");
        simulationResults = null;

        await fetch("/api/config/update", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(configData)
        });
        
        drawTopology();
        renderBulkTable();
        selectBus(1);
        setConfigStatus("default");
        showToast("Bara rolleri varsayılana sıfırlandı.");
    } catch (err) {
        showToast("Sıfırlama basarısız.", "error");
    }
}

// Upload config file
async function uploadConfigFile(file) {
    const formData = new FormData();
    formData.append("file", file);
    try {
        const response = await fetch("/api/config/upload", {
            method: "POST",
            body: formData
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || "Dosya yükleme hatası.");
        }
        configData = await response.json();
        sessionStorage.setItem("abm_dlmp_config", JSON.stringify(configData));
        setConfigStatus("loaded", file.name);
        drawTopology();
        renderBulkTable();
        selectBus(1);
        showToast(`Konfigürasyon dosyası yüklendi: ${file.name}`);

    } catch (err) {
        showToast(err.message, "error");
        showDetailedError("Konfigürasyon Yükleme Hatası (Config Upload)", err.message);
    }
}

// Upload existing results Excel
async function uploadResultsExcel(file) {
    const simulateBtn = document.getElementById("btn-simulate");
    simulateBtn.disabled = true;
    simulateBtn.textContent = "Sonuclar Yukleniyor...";
    
    const logHeader = document.getElementById("console-status-header");
    const logArea = document.getElementById("console-log-area");
    logHeader.textContent = "Running...";
    logArea.value = `[${new Date().toLocaleTimeString('tr-TR')}] Loading results file: ${file.name}...`;

    const formData = new FormData();
    formData.append("file", file);
    
    try {
        const response = await fetch("/api/results/upload", {
            method: "POST",
            body: formData
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Sonuc dosyasi yuklenemedi.");
        }
        
        const data = await response.json();
        simulationResults = data;
        
        // Update console
        logHeader.textContent = "Done.";
        if (data.logs && data.logs.length > 0) {
            logArea.value = data.logs.join("\n");
        } else {
            logArea.value += `\n[${new Date().toLocaleTimeString('tr-TR')}] Done.`;
        }
        logArea.scrollTop = logArea.scrollHeight;

        // Cache in sessionStorage
        sessionStorage.setItem("abm_dlmp_results", JSON.stringify(simulationResults));
        sessionStorage.setItem("abm_dlmp_console_log", logArea.value);
        sessionStorage.setItem("abm_dlmp_console_status", logHeader.textContent);

        // Refresh local configData
        await fetchConfig();
        
        // Populate view panels
        document.getElementById("btn-export-excel").disabled = false;
        
        renderResultsTables();
        drawResultCharts();
        
        showToast("Excel sonuc dosyasi yuklendi ve analiz edildi.");
        switchTab("tab-overview");
    } catch (err) {
        logHeader.textContent = "Error.";
        logArea.value += `\n[${new Date().toLocaleTimeString('tr-TR')}] Error: ${err.message}`;
        logArea.scrollTop = logArea.scrollHeight;
        showToast(err.message, "error");
        showDetailedError("Sonuç Excel Yükleme Hatası (Excel Upload)", err.message);
    } finally {
        simulateBtn.disabled = false;
        simulateBtn.textContent = "🚀 Generate Scenarios + Analyze";
    }
}

// Draw Topology SVG
function drawTopology() {
    const svg = document.getElementById("bus-topology-svg");
    svg.innerHTML = ""; // Clear existing

    // 1. Draw Lines
    lines.forEach(line => {
        const fromIdx = line[0] - 1;
        const toIdx = line[1] - 1;
        const fromCoord = getSvgCoords(coords[fromIdx][0], coords[fromIdx][1]);
        const toCoord = getSvgCoords(coords[toIdx][0], coords[toIdx][1]);

        const lineEl = document.createElementNS("http://www.w3.org/2000/svg", "line");
        lineEl.setAttribute("x1", fromCoord.cx);
        lineEl.setAttribute("y1", fromCoord.cy);
        lineEl.setAttribute("x2", toCoord.cx);
        lineEl.setAttribute("y2", toCoord.cy);
        lineEl.setAttribute("class", "svg-edge");
        svg.appendChild(lineEl);
    });

    // Get plot bus selections to add suffixes (A, B, C)
    const plotAVal = document.getElementById("plot-bus-a") ? parseInt(document.getElementById("plot-bus-a").value) : 2;
    const plotBVal = document.getElementById("plot-bus-b") ? parseInt(document.getElementById("plot-bus-b").value) : 17;
    const plotCVal = document.getElementById("plot-bus-c") ? parseInt(document.getElementById("plot-bus-c").value) : 33;

    // 2. Draw Nodes
    configData.forEach(bus => {
        const idx = bus.bus_id - 1;
        const coord = getSvgCoords(coords[idx][0], coords[idx][1]);
        const role = bus.role;

        const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
        group.setAttribute("class", "svg-node");
        group.setAttribute("id", `svg-node-group-${bus.bus_id}`);
        group.addEventListener("click", () => selectBus(bus.bus_id));
        group.addEventListener("mouseenter", (e) => showTooltip(e, bus));
        group.addEventListener("mousemove", moveTooltip);
        group.addEventListener("mouseleave", hideTooltip);

        // Highlight ring (inspected node marker)
        const ring = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        ring.setAttribute("cx", coord.cx);
        ring.setAttribute("cy", coord.cy);
        ring.setAttribute("r", 14);
        ring.setAttribute("fill", "none");
        ring.setAttribute("stroke", selectedBusId === bus.bus_id ? COLOR_SELECTED : "transparent");
        ring.setAttribute("stroke-width", "2px");
        ring.setAttribute("id", `svg-node-ring-${bus.bus_id}`);
        group.appendChild(ring);

        // Actual shape based on role
        if (role === "Slack/Grid") {
            const diamond = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
            const size = 9;
            const points = `${coord.cx},${coord.cy - size} ${coord.cx + size},${coord.cy} ${coord.cx},${coord.cy + size} ${coord.cx - size},${coord.cy}`;
            diamond.setAttribute("points", points);
            diamond.setAttribute("fill", COLOR_SLACK);
            diamond.setAttribute("stroke", "#FFFFFF");
            diamond.setAttribute("stroke-width", "1.5");
            group.appendChild(diamond);
        } else {
            const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            circle.setAttribute("cx", coord.cx);
            circle.setAttribute("cy", coord.cy);
            circle.setAttribute("r", 7);
            circle.setAttribute("stroke", "#FFFFFF");
            circle.setAttribute("stroke-width", "1.5");
            
            let color = COLOR_LOAD;
            if (role === "DER") color = COLOR_DER;
            else if (role === "Prosumer") color = COLOR_PROSUMER;
            circle.setAttribute("fill", color);
            group.appendChild(circle);
        }

        // Determine short role and suffix
        let roleAbbrev = "PQ";
        if (role === "Slack/Grid") roleAbbrev = "SLK";
        else if (role === "DER") roleAbbrev = "DER";
        else if (role === "Prosumer") roleAbbrev = "PRO";

        let suffix = "";
        if (bus.bus_id === plotAVal) suffix = " | A";
        else if (bus.bus_id === plotBVal) suffix = " | B";
        else if (bus.bus_id === plotCVal) suffix = " | C";

        const labelText = `${bus.bus_id} | ${roleAbbrev}${suffix}`;
        const isPlotSelected = suffix !== "";
        const isInspected = selectedBusId === bus.bus_id;

        // Draw yellow rect highlight if inspected
        if (isInspected) {
            const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
            rect.setAttribute("class", "svg-node-rect");
            rect.setAttribute("x", coord.cx + 12);
            rect.setAttribute("y", coord.cy - 8);
            // Dynamic width approximation based on label length
            rect.setAttribute("width", labelText.length * 6 + 6);
            rect.setAttribute("height", 16);
            group.appendChild(rect);
        }

        // Draw text label next to the node
        const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
        text.setAttribute("x", coord.cx + 15);
        text.setAttribute("y", coord.cy + 1);
        text.setAttribute("class", "svg-node-text");
        
        // Colors & weights
        if (isPlotSelected) {
            text.setAttribute("fill", COLOR_SELECTED);
            text.style.fontWeight = "bold";
        } else {
            text.setAttribute("fill", COLOR_TEXT_PRIMARY);
            text.style.fontWeight = isInspected ? "bold" : "normal";
        }
        
        text.textContent = labelText;
        group.appendChild(text);

        svg.appendChild(group);
    });
}


// Tooltip helpers
function showTooltip(e, bus) {
    const tooltip = window.appTooltip;
    tooltip.innerHTML = `<strong>Bara ${bus.bus_id}</strong><br>Rol: ${bus.role}<br>Ek Pd: ${formatNum(bus.add_Pd_MW, 3)} MW<br>Pmax: ${formatNum(bus.Pmax_MW, 3)} MW`;
    tooltip.style.display = "block";
    moveTooltip(e);
}

function moveTooltip(e) {
    const tooltip = window.appTooltip;
    tooltip.style.left = (e.pageX + 15) + "px";
    tooltip.style.top = (e.pageY + 15) + "px";
}

function hideTooltip() {
    window.appTooltip.style.display = "none";
}

// Select Bus action
// Select Bus action
function selectBus(busId) {
    selectedBusId = busId;

    // Redraw topology to update the yellow rect highlight
    drawTopology();

    document.getElementById("editor-bus-id").value = selectedBusId;

    const bus = configData[selectedBusId - 1];
    if (bus) {
        document.getElementById("bus-role").value = bus.role;
        document.getElementById("bus-add-pd").value = bus.add_Pd_MW;
        document.getElementById("bus-pf").value = bus.pf;
        
        // Grouped inputs
        document.getElementById("bus-p-limits").value = `${bus.Pmin_MW}, ${bus.Pmax_MW}`;
        document.getElementById("bus-q-limits").value = `${bus.Qmin_MVAr}, ${bus.Qmax_MVAr}`;
        document.getElementById("bus-v-limits").value = `${bus.Vmin_pu}, ${bus.Vmax_pu}`;
        document.getElementById("bus-c2-range").value = `${bus.c2_min}, ${bus.c2_max}`;
        document.getElementById("bus-c1-range").value = `${bus.c1_min}, ${bus.c1_max}`;
        document.getElementById("bus-c0-constant").value = bus.c0;
        
        toggleEditorSubcards(bus.role);
        updateSelectedBusDetailsText();
    }
}

function toggleEditorSubcards(role) {
    const isPq = role === "PQ Load";
    const isDer = role === "DER";
    const isPro = role === "Prosumer";
    const isSlack = role === "Slack/Grid";

    // Pd and PF are only enabled for PQ Load and Prosumer
    document.getElementById("bus-add-pd").disabled = !(isPq || isPro);
    document.getElementById("bus-pf").disabled = !(isPq || isPro);

    // Gen limits and costs are enabled for DER, Slack/Grid, and Prosumer
    document.getElementById("bus-p-limits").disabled = !(isDer || isSlack || isPro);
    document.getElementById("bus-q-limits").disabled = !(isDer || isSlack || isPro);
    document.getElementById("bus-c2-range").disabled = !(isDer || isSlack || isPro);
    document.getElementById("bus-c1-range").disabled = !(isDer || isSlack || isPro);
    document.getElementById("bus-c0-constant").disabled = !(isDer || isSlack || isPro);
}

function applyBusRoleSettings() {
    const idx = selectedBusId - 1;
    const bus = configData[idx];
    if (!bus) return;

    bus.role = document.getElementById("bus-role").value;
    bus.add_Pd_MW = parseFloat(document.getElementById("bus-add-pd").value) || 0;
    bus.pf = parseFloat(document.getElementById("bus-pf").value) || 0.95;

    // Parse P Limits
    const pLimParts = document.getElementById("bus-p-limits").value.split(",");
    bus.Pmin_MW = parseFloat(pLimParts[0]) || 0;
    bus.Pmax_MW = parseFloat(pLimParts[1]) || 0;

    // Parse Q Limits
    const qLimParts = document.getElementById("bus-q-limits").value.split(",");
    bus.Qmin_MVAr = parseFloat(qLimParts[0]) || 0;
    bus.Qmax_MVAr = parseFloat(qLimParts[1]) || 0;

    // Parse c2 range
    const c2Parts = document.getElementById("bus-c2-range").value.split(",");
    bus.c2_min = parseFloat(c2Parts[0]) || 0;
    bus.c2_max = parseFloat(c2Parts[1]) || 0;

    // Parse c1 range
    const c1Parts = document.getElementById("bus-c1-range").value.split(",");
    bus.c1_min = parseFloat(c1Parts[0]) || 0;
    bus.c1_max = parseFloat(c1Parts[1]) || 0;

    // Parse c0
    bus.c0 = parseFloat(document.getElementById("bus-c0-constant").value) || 0;

    // V limits are read-only and already set

    drawTopology();
    updateBulkTableRow(selectedBusId);
    updateSelectedBusDetailsText();
    setConfigStatus("custom");
    syncConfigToBackend();
    
    showToast(`Bara ${selectedBusId} rolleri uygulandı ve kaydedildi.`);
}

function updateSelectedBusDetailsText() {
    const busId = selectedBusId;
    const bus = configData[busId - 1];
    if (!bus) return;

    const baseLoad = BASE_LOADS[busId] || { p: 0.0, q: 0.0 };
    
    let roleType = 1;
    let roleTypeText = "PQ / Load Bus";
    if (bus.role === "Slack/Grid") {
        roleType = 3;
        roleTypeText = "Slack / Reference";
    } else if (bus.role === "DER" || bus.role === "Prosumer") {
        roleType = 2;
        roleTypeText = "PV / Generator Bus";
    }

    let text = `BUS ${busId} SUMMARY\n\n`;
    text += `GENERAL\n`;
    text += `• Role                 : ${bus.role}\n`;
    text += `• MATPOWER BUS_TYPE    : ${roleType} (${roleTypeText})\n\n`;
    
    text += `BASE DEMAND / CONFIGURATION\n`;
    text += `• Loaded case base Pd/Qd : ${formatNum(baseLoad.p, 4)} MW / ${formatNum(baseLoad.q, 4)} MVAr\n`;
    text += `• Fixed Added Pd       : ${formatNum(bus.add_Pd_MW, 4)} MW\n`;
    text += `• Fixed Added PF       : ${formatNum(bus.pf, 3, "1.000")}\n`;
    text += `• Pmin / Pmax          : ${formatNum(bus.Pmin_MW, 4)} – ${formatNum(bus.Pmax_MW, 4)} MW\n`;
    text += `• Qmin / Qmax          : ${formatNum(bus.Qmin_MVAr, 4)} – ${formatNum(bus.Qmax_MVAr, 4)} MVAr\n`;
    text += `• Vmin / Vmax          : ${formatNum(bus.Vmin_pu, 3, "0.900")} – ${formatNum(bus.Vmax_pu, 3, "1.100")} p.u.\n`;
    text += `• Fixed generator Vg   : 1.000 p.u.\n\n`;

    text += `COST MODEL\n`;
    text += `• C(P) = ${formatNum(bus.c2_min, 4)} P^2 + ${formatNum(bus.c1_min, 4)} P + ${formatNum(bus.c0, 4)}\n\n`;

    // Multipliers
    const season = document.getElementById("season-select").value;
    const season_demand_multiplier = season === "Yaz" ? 1.2 : 1.0;
    
    const caseTime = document.getElementById("time-select").value;
    let time_generation_multiplier = 1.0;
    const caseTimeLower = caseTime.toLowerCase();
    if (caseTimeLower.includes("gece")) {
        time_generation_multiplier = 0.0;
    } else if (caseTimeLower.includes("önce")) { // Öğleden önce
        time_generation_multiplier = 0.4;
    } else if (caseTimeLower.includes("öğle")) {
        time_generation_multiplier = 1.0;
    } else if (caseTimeLower.includes("akşam") || caseTimeLower.includes("üstü")) {
        time_generation_multiplier = 0.6;
    }

    if (bus.role === "DER" || bus.role === "Prosumer") {
        text += `EFFECTIVE GENERATION LIMITS\n`;
        text += `• Configured Pmin/Pmax : ${formatNum(bus.Pmin_MW, 4)} – ${formatNum(bus.Pmax_MW, 4)} MW\n`;
        text += `• After Case time      : ${formatNum(bus.Pmin_MW * time_generation_multiplier, 4)} – ${formatNum(bus.Pmax_MW * time_generation_multiplier, 4)} MW\n`;
        text += `• Configured Qmin/Qmax : ${formatNum(bus.Qmin_MVAr, 4)} – ${formatNum(bus.Qmax_MVAr, 4)} MVAr\n`;
        text += `• After Case time      : ${formatNum(bus.Qmin_MVAr * time_generation_multiplier, 4)} – ${formatNum(bus.Qmax_MVAr * time_generation_multiplier, 4)} MVAr\n\n`;
    }

    if (bus.role === "PQ Load" || bus.role === "Prosumer") {
        const configuredPd = baseLoad.p + bus.add_Pd_MW;
        let configuredQd = baseLoad.q;
        if (bus.add_Pd_MW > 0 && bus.pf > 0 && bus.pf < 1.0) {
            configuredQd += bus.add_Pd_MW * Math.tan(Math.acos(bus.pf));
        }
        const effectivePd = configuredPd * season_demand_multiplier;
        const effectiveQd = configuredQd * season_demand_multiplier;

        text += `EFFECTIVE DEMAND\n`;
        text += `• Configured Pd        : ${formatNum(configuredPd, 4)} MW\n`;
        text += `• After Season         : ${formatNum(effectivePd, 4)} MW\n`;
        text += `• Configured Qd        : ${formatNum(configuredQd, 4)} MVAr\n`;
        text += `• After Season         : ${formatNum(effectiveQd, 4)} MVAr\n\n`;
    }

    // Latest OPF result (if simulationResults has it)
    if (simulationResults && simulationResults.buses && simulationResults.buses.length > 0) {
        const matchingBuses = simulationResults.buses.filter(b => b.bus_id === busId);
        if (matchingBuses.length > 0) {
            const br = matchingBuses[matchingBuses.length - 1];
            text += `LATEST OPF RESULT (SCENARIO ${br.scenario_id})\n`;
            text += `• Final Pd / Qd        : ${formatNum(br.Pd_MW, 4)} MW / ${formatNum(br.Qd_MVAr, 4)} MVAr\n`;
            text += `• Pg / Qg at bus       : ${formatNum(br.Pg_MW, 4)} MW / ${formatNum(br.Qg_MVAr, 4)} MVAr\n`;
            text += `• Vm / Va              : ${formatNum(br.Vm_pu, 4)} p.u. / ${formatNum(br.Va_deg, 4)} deg\n`;
            text += `• DLMP LAM_P / LAM_Q   : ${formatNum(br.DLMP_LAM_P, 4)} / ${formatNum(br.DLMP_LAM_Q, 4)}\n`;
            text += `• Cost-to-load         : ${formatNum(br.cost_to_load, 4)}\n`;
        }
    }

    document.getElementById("topology-text-summary").value = text;
}


// Render Bulk Table
function renderBulkTable() {
    const tbody = document.querySelector("#bulk-edit-table tbody");
    tbody.innerHTML = "";

    configData.forEach(bus => {
        const tr = document.createElement("tr");
        tr.setAttribute("id", `bulk-tr-${bus.bus_id}`);
        tr.innerHTML = `
            <td><strong>${bus.bus_id}</strong></td>
            <td>
                <select onchange="handleBulkTableChange(${bus.bus_id}, 'role', this.value)">
                    <option value="PQ Load" ${bus.role === "PQ Load" ? "selected" : ""}>PQ Load</option>
                    <option value="DER" ${bus.role === "DER" ? "selected" : ""}>DER</option>
                    <option value="Prosumer" ${bus.role === "Prosumer" ? "selected" : ""}>Prosumer</option>
                    <option value="Slack/Grid" ${bus.role === "Slack/Grid" ? "selected" : ""}>Slack/Grid</option>
                </select>
            </td>
            <td><input type="number" step="0.01" value="${bus.add_Pd_MW}" oninput="handleBulkTableChange(${bus.bus_id}, 'add_Pd_MW', this.value)"></td>
            <td><input type="number" step="0.01" value="${bus.pf}" oninput="handleBulkTableChange(${bus.bus_id}, 'pf', this.value)"></td>
            <td><input type="number" step="0.01" value="${bus.Vmin_pu}" disabled></td>
            <td><input type="number" step="0.01" value="${bus.Vmax_pu}" disabled></td>
            <td><input type="number" step="0.1" value="${bus.Pmin_MW}" oninput="handleBulkTableChange(${bus.bus_id}, 'Pmin_MW', this.value)"></td>
            <td><input type="number" step="0.1" value="${bus.Pmax_MW}" oninput="handleBulkTableChange(${bus.bus_id}, 'Pmax_MW', this.value)"></td>
            <td><input type="number" step="0.1" value="${bus.Qmin_MVAr}" oninput="handleBulkTableChange(${bus.bus_id}, 'Qmin_MVAr', this.value)"></td>
            <td><input type="number" step="0.1" value="${bus.Qmax_MVAr}" oninput="handleBulkTableChange(${bus.bus_id}, 'Qmax_MVAr', this.value)"></td>
            <td><input type="number" step="0.001" value="${bus.c2_min}" oninput="handleBulkTableChange(${bus.bus_id}, 'c2_min', this.value)"></td>
            <td><input type="number" step="0.001" value="${bus.c2_max}" oninput="handleBulkTableChange(${bus.bus_id}, 'c2_max', this.value)"></td>
            <td><input type="number" step="0.1" value="${bus.c1_min}" oninput="handleBulkTableChange(${bus.bus_id}, 'c1_min', this.value)"></td>
            <td><input type="number" step="0.1" value="${bus.c1_max}" oninput="handleBulkTableChange(${bus.bus_id}, 'c1_max', this.value)"></td>
            <td><input type="number" step="0.1" value="${bus.c0}" oninput="handleBulkTableChange(${bus.bus_id}, 'c0', this.value)"></td>
        `;
        tbody.appendChild(tr);
    });
}

function updateBulkTableRow(busId) {
    const bus = configData[busId - 1];
    const tr = document.getElementById(`bulk-tr-${busId}`);
    if (!tr) return;

    tr.querySelector("select").value = bus.role;
    const inputs = tr.querySelectorAll("input");
    inputs[0].value = bus.add_Pd_MW;
    inputs[1].value = bus.pf;
    inputs[2].value = bus.Pmin_MW;
    inputs[3].value = bus.Pmax_MW;
    inputs[4].value = bus.Qmin_MVAr;
    inputs[5].value = bus.Qmax_MVAr;
    inputs[6].value = bus.c2_min;
    inputs[7].value = bus.c2_max;
    inputs[8].value = bus.c1_min;
    inputs[9].value = bus.c1_max;
    inputs[10].value = bus.c0;
}

function handleBulkTableChange(busId, field, value) {
    const idx = busId - 1;
    const oldRole = configData[idx].role;

    if (field === "role") {
        configData[idx].role = value;
    } else {
        configData[idx][field] = parseFloat(value) || 0;
    }

    if (selectedBusId === busId) {
        document.getElementById("bus-role").value = configData[idx].role;
        document.getElementById("bus-add-pd").value = configData[idx].add_Pd_MW;
        document.getElementById("bus-pf").value = configData[idx].pf;
        document.getElementById("bus-pmin").value = configData[idx].Pmin_MW;
        document.getElementById("bus-pmax").value = configData[idx].Pmax_MW;
        document.getElementById("bus-qmin").value = configData[idx].Qmin_MVAr;
        document.getElementById("bus-qmax").value = configData[idx].Qmax_MVAr;
        document.getElementById("bus-c2-min").value = configData[idx].c2_min;
        document.getElementById("bus-c2-max").value = configData[idx].c2_max;
        document.getElementById("bus-c1-min").value = configData[idx].c1_min;
        document.getElementById("bus-c1-max").value = configData[idx].c1_max;
        document.getElementById("bus-c0").value = configData[idx].c0;
        toggleEditorSubcards(configData[idx].role);
    }

    if (field === "role" && oldRole !== value) {
        drawTopology();
        const ring = document.getElementById(`svg-node-ring-${selectedBusId}`);
        if (ring) ring.setAttribute("stroke", COLOR_SELECTED);
    }

    updateSelectedBusDetailsText();

    // Mark config as custom (user-modified)
    setConfigStatus("custom");

    // Set saving status indicator
    const statusEl = document.getElementById("bulk-save-status");
    if (statusEl) {
        statusEl.innerHTML = '<span style="color:#e65100; font-weight:bold;">● Kaydediliyor...</span>';
    }

    syncConfigToBackend();
}


let syncTimeout = null;
function syncConfigToBackend(showToastOnSuccess = false) {
    sessionStorage.setItem("abm_dlmp_config", JSON.stringify(configData));
    if (syncTimeout) clearTimeout(syncTimeout);
    syncTimeout = setTimeout(async () => {
        try {
            const res = await fetch("/api/config/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(configData)
            });
            if (res.ok) {
                const statusEl = document.getElementById("bulk-save-status");
                if (statusEl) {
                    statusEl.innerHTML = '<span style="color:#2e7d32; font-weight:bold;">✓ Kaydedildi</span>';
                    setTimeout(() => {
                        statusEl.innerHTML = '<span style="color:#6B7280; font-weight:normal;">✓ Değişiklikler otomatik kaydedilir</span>';
                    }, 2000);
                }
                if (showToastOnSuccess) {
                    showToast("Bara rolleri ve parametreleri başarıyla kaydedildi.");
                }
            } else {
                throw new Error("API response error");
            }
        } catch (err) {
            console.error("Senkronizasyon hatası:", err);
            const statusEl = document.getElementById("bulk-save-status");
            if (statusEl) {
                statusEl.innerHTML = '<span style="color:#c94a49; font-weight:bold;">✗ Kaydetme Başarısız</span>';
            }
            if (showToastOnSuccess) {
                showToast("Kaydetme işlemi başarısız oldu.", "error");
            }
        }
    }, 500);
}

// Run stochastic scenario simulation
async function runSimulation() {
    const btn = document.getElementById("btn-simulate");
    btn.disabled = true;
    btn.textContent = "Generating Scenarios...";
    showToast("Simulasyon baslatildi. Lutfen bekleyin...", "success");

    const logHeader = document.getElementById("console-status-header");
    const logArea = document.getElementById("console-log-area");
    logHeader.textContent = "Running...";
    logArea.value = `[${new Date().toLocaleTimeString('tr-TR')}] Loaded custom bus role config.\n[${new Date().toLocaleTimeString('tr-TR')}] Starting case33bw scenario generation.`;

    const loadRangeStr = document.getElementById("load-scale-range").value;
    const loadRange = loadRangeStr.split(",").map(x => parseFloat(x.trim()) || 1.0);

    const payload = {
        season: document.getElementById("season-select").value,
        case_time: document.getElementById("time-select").value,
        global_load_scale_pdf: document.getElementById("load-scale-pdf").value,
        offer_pdf: document.getElementById("offer-pdf").value,
        prosumer_policy: document.getElementById("policy-select").value,
        scenario_count: parseInt(document.getElementById("scenario-count").value) || 400,
        random_seed: parseInt(document.getElementById("random-seed").value) || 42,
        global_load_scale_range: loadRange,
        run_validation: document.getElementById("run-validation-check").checked,
        grid_c2: configData[0] ? ((configData[0].c2_min + configData[0].c2_max) / 2) : 0.02,
        grid_c1: configData[0] ? ((configData[0].c1_min + configData[0].c1_max) / 2) : 80.0,
        grid_c0: configData[0] ? configData[0].c0 : 0.0,
        output_file_name: document.getElementById("output-excel-file").value,
        plot_bus_a: parseInt(document.getElementById("plot-bus-a").value) || 2,
        plot_bus_b: parseInt(document.getElementById("plot-bus-b").value) || 17,
        plot_bus_c: parseInt(document.getElementById("plot-bus-c").value) || 33,
        scenario_generator: document.querySelector("input[name='scenario_generator']:checked")?.value || "matlab"
    };

    // Save evaluated inputs to sessionStorage for persistence on refresh
    const inputsToSave = {
        scenarioCount: payload.scenario_count,
        randomSeed: payload.random_seed,
        loadScaleRange: document.getElementById("load-scale-range").value,
        timeSelect: payload.case_time,
        seasonSelect: payload.season,
        policySelect: payload.prosumer_policy,
        loadScalePdf: payload.global_load_scale_pdf,
        offerPdf: payload.offer_pdf,
        runValidationCheck: payload.run_validation,
        outputExcelFile: payload.output_file_name,
        plotBusA: payload.plot_bus_a,
        plotBusB: payload.plot_bus_b,
        plotBusC: payload.plot_bus_c
    };
    sessionStorage.setItem("abm_dlmp_inputs", JSON.stringify(inputsToSave));

    // Initialize progress bar
    const progressContainer = document.getElementById("simulation-progress-container");
    const progressText = document.getElementById("simulation-progress-text");
    const progressFill = document.getElementById("simulation-progress-fill");
    
    progressContainer.style.display = "flex";
    progressText.textContent = `0 / ${payload.scenario_count}`;
    progressFill.style.width = "0%";

    let pollInterval = setInterval(async () => {
        try {
            const res = await fetch("/api/simulate/progress");
            if (res.ok) {
                const prog = await res.json();
                if (prog.status === "running") {
                    const pct = Math.min(100, (prog.current / prog.total) * 100);
                    progressFill.style.width = `${pct}%`;
                    progressText.textContent = `${prog.current} / ${prog.total}`;

                    logHeader.textContent = `Running: Generated ${prog.current} / ${prog.total}`;
                    const lines = logArea.value.split("\n");
                    const lastLine = lines[lines.length - 1];
                    const newMsg = `[${new Date().toLocaleTimeString('tr-TR')}] Generated ${prog.current} / ${prog.total} valid scenarios.`;
                    if (!lastLine.includes(`Generated ${prog.current} / ${prog.total}`)) {
                        if (lastLine.includes("Generated") && lastLine.includes("scenarios")) {
                            lines[lines.length - 1] = newMsg;
                            logArea.value = lines.join("\n");
                        } else {
                            logArea.value += "\n" + newMsg;
                        }
                        logArea.scrollTop = logArea.scrollHeight;
                    }
                }
            }
        } catch (e) {
            // Ignore polling errors
        }
    }, 250);

    try {
        const response = await fetch("/api/simulate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Simulation error.");
        }

        const data = await response.json();
        simulationResults = data;
        updateSelectedBusDetailsText();

        // Update console logs
        logHeader.textContent = "Done.";
        if (data.logs && data.logs.length > 0) {
            logArea.value = data.logs.join("\n");
        } else {
            logArea.value += `\n[${new Date().toLocaleTimeString('tr-TR')}] Done.`;
        }
        logArea.scrollTop = logArea.scrollHeight;

        // Cache in sessionStorage
        sessionStorage.setItem("abm_dlmp_results", JSON.stringify(simulationResults));
        sessionStorage.setItem("abm_dlmp_console_log", logArea.value);
        sessionStorage.setItem("abm_dlmp_console_status", logHeader.textContent);

        // Enable export button
        document.getElementById("btn-export-excel").disabled = false;

        // Render OLS Regression Table, Validation Table, Previews
        renderResultsTables();
        drawResultCharts();
        
        showToast("Senaryo simulasyonu ve OLS analizleri tamamlandi!");
        switchTab("tab-overview");
    } catch (err) {
        logHeader.textContent = "Error.";
        logArea.value += `\n[${new Date().toLocaleTimeString('tr-TR')}] Error: ${err.message}`;
        logArea.scrollTop = logArea.scrollHeight;
        showToast(err.message, "error");
        showDetailedError("Simülasyon Çalıştırma Hatası (Simulation Diagnostics)", err.message);
    } finally {
        if (pollInterval) {
            clearInterval(pollInterval);
        }
        progressContainer.style.display = "none";
        btn.disabled = false;
        btn.textContent = "🚀 Generate Scenarios + Analyze";
    }
}


// Render OLS and validation table previews
function renderResultsTables() {
    if (!simulationResults) return;

    // 1. OLS Regressions Table
    const olsBody = document.querySelector("#ols-results-table tbody");
    olsBody.innerHTML = "";
    simulationResults.ols_results.forEach(m => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td><strong>${m.model_id}</strong></td>
            <td><code>${m.dependent_variable}</code></td>
            <td><code>${m.formula}</code></td>
            <td style="font-family:monospace;font-size:10px;">${m.coefficients}</td>
            <td><strong>${formatNum(m.R_squared, 4)}</strong></td>
            <td>${formatNum(m.RMSE, 4)}</td>
            <td>${m.N}</td>
        `;
        olsBody.appendChild(tr);
    });

    // 2. Validation Diagnostics Table
    validationCurrentPage = 1;
    renderValidationTablePage();

    // Populate scenario filter dropdown
    updatePreviewScenarioDropdown();

    // Refresh current preview data table
    const previewType = document.getElementById("preview-table-select").value;
    renderPreviewTable(previewType);
}

function renderValidationTablePage() {
    const valBody = document.querySelector("#validation-preview-table tbody");
    if (!valBody) return;
    
    valBody.innerHTML = "";
    
    if (simulationResults && simulationResults.validation_table && simulationResults.validation_table.length > 0) {
        const totalPages = Math.ceil(simulationResults.validation_table.length / 20) || 1;
        
        if (validationCurrentPage < 1) validationCurrentPage = 1;
        if (validationCurrentPage > totalPages) validationCurrentPage = totalPages;
        
        // Update pagination buttons
        const btnPrev = document.getElementById("btn-val-prev");
        const btnNext = document.getElementById("btn-val-next");
        const pageInd = document.getElementById("val-page-indicator");
        
        if (btnPrev) btnPrev.disabled = (validationCurrentPage === 1);
        if (btnNext) btnNext.disabled = (validationCurrentPage === totalPages);
        if (pageInd) pageInd.textContent = `Sayfa ${validationCurrentPage} / ${totalPages}`;
        
        const startIdx = (validationCurrentPage - 1) * 20;
        const endIdx = startIdx + 20;
        const pageData = simulationResults.validation_table.slice(startIdx, endIdx);
        
        pageData.forEach(v => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>${v.scenario_id}</strong></td>
                <td>${v.runpf_success ? "✓ Başarılı" : "✗ Başarısız"}</td>
                <td><span class="badge ${v.validation_pass ? 'badge-ready' : 'badge-error'}">${v.validation_pass ? 'Pass' : 'Fail'}</span></td>
                <td>${v.dominant_fail_reason}</td>
                <td>${formatNum(v.max_abs_Vm_error, 6)}</td>
                <td>${formatNum(v.max_abs_Va_error, 4)}</td>
                <td>${formatNum(v.max_abs_Pf_error, 4)}</td>
                <td>${formatNum(v.max_abs_loading_error, 3)} %</td>
            `;
            valBody.appendChild(tr);
        });
    } else {
        valBody.innerHTML = `<tr><td colspan="8" class="placeholder-text">Doğrulama veri tablosu boş veya pasif.</td></tr>`;
        const btnPrev = document.getElementById("btn-val-prev");
        const btnNext = document.getElementById("btn-val-next");
        const pageInd = document.getElementById("val-page-indicator");
        if (btnPrev) btnPrev.disabled = true;
        if (btnNext) btnNext.disabled = true;
        if (pageInd) pageInd.textContent = "Sayfa 1 / 1";
    }
}

// Render dynamic preview tables (Summary, Buses, Branches, Generators)
function renderPreviewTable(type) {
    if (!simulationResults) return;

    const table = document.getElementById("preview-data-table");
    const thead = table.querySelector("thead");
    const tbody = table.querySelector("tbody");

    thead.innerHTML = "";
    tbody.innerHTML = "";

    let dataArray = [];
    if (type === "summary") {
        dataArray = simulationResults.summary_table || [];
    } else if (type === "buses") {
        dataArray = simulationResults.buses || [];
    } else if (type === "branches") {
        dataArray = simulationResults.branches || [];
    } else if (type === "generators") {
        dataArray = simulationResults.generators || [];
    }

    // Filter by Scenario if a specific scenario is selected (and not viewing summary table)
    if (type !== "summary") {
        const selectEl = document.getElementById("preview-scenario-select");
        if (selectEl) {
            const scenarioFilter = selectEl.value;
            if (scenarioFilter !== "all") {
                const targetScId = parseInt(scenarioFilter);
                dataArray = dataArray.filter(row => row.scenario_id === targetScId);
            }
        }
    }

    if (!dataArray || dataArray.length === 0) {
        thead.innerHTML = "<tr><th>Veri Yok</th></tr>";
        tbody.innerHTML = `<tr><td class="placeholder-text">Tabloda gösterilecek ${type} verisi bulunmamaktadır.</td></tr>`;
        return;
    }

    // Extract headers (keys from first object)
    const headers = Object.keys(dataArray[0]);

    // Create header row
    const trHead = document.createElement("tr");
    headers.forEach(h => {
        const th = document.createElement("th");
        th.textContent = h;
        trHead.appendChild(th);
    });
    thead.appendChild(trHead);

    // Render data rows (sliced for performance)
    dataArray.slice(0, 150).forEach(row => {
        const tr = document.createElement("tr");
        headers.forEach(h => {
            const td = document.createElement("td");
            const val = row[h];
            if (val === null || val === undefined) {
                td.textContent = "-";
            } else if (typeof val === "number") {
                td.textContent = Number.isInteger(val) ? val.toString() : val.toFixed(4);
            } else if (typeof val === "boolean") {
                td.textContent = val ? "True" : "False";
            } else {
                td.textContent = val.toString();
            }
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
}

function updatePreviewScenarioDropdown() {
    const select = document.getElementById("preview-scenario-select");
    if (!select) return;

    // Clear existing
    select.innerHTML = '<option value="all">Tüm Senaryolar</option>';

    if (!simulationResults || !simulationResults.plot_data || !simulationResults.plot_data.scenarios_id) {
        return;
    }

    const scenarios = simulationResults.plot_data.scenarios_id;
    scenarios.forEach(scId => {
        const opt = document.createElement("option");
        opt.value = scId;
        opt.textContent = `Senaryo ${scId}`;
        select.appendChild(opt);
    });
}

// Draw Result Charts (Overview, Econometric, Validation)
function drawResultCharts() {
    if (!simulationResults) return;

    // Read the current selected plot bus IDs
    const plotAVal = document.getElementById("plot-bus-a") ? parseInt(document.getElementById("plot-bus-a").value) : 2;
    const plotBVal = document.getElementById("plot-bus-b") ? parseInt(document.getElementById("plot-bus-b").value) : 17;
    const plotCVal = document.getElementById("plot-bus-c") ? parseInt(document.getElementById("plot-bus-c").value) : 33;

    // Dynamically calculate DLMP lists for the selected buses
    const busResults = simulationResults.buses || [];
    const dlmps_a = busResults.filter(b => b.bus_id === plotAVal).sort((a, b) => a.scenario_id - b.scenario_id).map(b => b.DLMP_LAM_P);
    const dlmps_b = busResults.filter(b => b.bus_id === plotBVal).sort((a, b) => a.scenario_id - b.scenario_id).map(b => b.DLMP_LAM_P);
    const dlmps_c = busResults.filter(b => b.bus_id === plotCVal).sort((a, b) => a.scenario_id - b.scenario_id).map(b => b.DLMP_LAM_P);

    // Recompute overlapping histogram counts
    const centers_dlmp = simulationResults.overview_plots.centers_dlmp;
    
    function getHistogramData(dataVec, centersVec) {
        if (!dataVec || dataVec.length === 0) return new Array(centersVec.length).fill(0);
        const counts = new Array(centersVec.length).fill(0);
        dataVec.forEach(val => {
            let closestIdx = 0;
            let minDiff = Infinity;
            centersVec.forEach((center, idx) => {
                const diff = Math.abs(val - center);
                if (diff < minDiff) {
                    minDiff = diff;
                    closestIdx = idx;
                }
            });
            counts[closestIdx]++;
        });
        return counts;
    }

    const counts_dlmp_a = getHistogramData(dlmps_a, centers_dlmp);
    const counts_dlmp_b = getHistogramData(dlmps_b, centers_dlmp);
    const counts_dlmp_c = getHistogramData(dlmps_c, centers_dlmp);

    // Destroy all existing Chart.js instances
    Object.keys(chartInstances).forEach(key => {
        if (chartInstances[key]) {
            chartInstances[key].destroy();
        }
    });
    chartInstances = {};

    // Common Chart Options
    const scatterOptions = (titleX, titleY) => ({
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
            x: {
                title: { display: true, text: titleX, color: COLOR_TEXT_PRIMARY },
                grid: { color: 'rgba(211, 208, 198, 0.4)' }
            },
            y: {
                title: { display: true, text: titleY, color: COLOR_TEXT_PRIMARY },
                grid: { color: 'rgba(211, 208, 198, 0.4)' }
            }
        }
    });

    const histOptions = (titleX) => ({
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
            x: {
                type: 'linear',
                title: { display: true, text: titleX, color: COLOR_TEXT_PRIMARY },
                grid: { display: false }
            },
            y: {
                title: { display: true, text: "Senaryo Adedi", color: COLOR_TEXT_PRIMARY },
                grid: { color: 'rgba(211, 208, 198, 0.4)' }
            }
        }
    });

    // --- 1. OVERVIEW PLOTS ---

    // Load Distribution Histogram
    const ctxPdHist = document.getElementById("chart-pd-hist").getContext("2d");
    chartInstances["pd-hist"] = new Chart(ctxPdHist, {
        type: 'bar',
        data: {
            datasets: [{
                data: simulationResults.overview_plots.centers_pd.map((x, idx) => ({ x: x, y: simulationResults.overview_plots.counts_pd[idx] })),
                backgroundColor: 'rgba(74, 124, 89, 0.7)',
                borderColor: '#4A7C59',
                borderWidth: 1,
                barPercentage: 0.9,
                categoryPercentage: 0.9
            }]
        },
        options: histOptions("Toplam Pd MW")
    });

    // DLMP Distribution Histogram (stepped overlapping lines matching MATLAB DisplayStyle stairs)
    const ctxDlmpHist = document.getElementById("chart-dlmp-hist").getContext("2d");
    
    chartInstances["dlmp-hist"] = new Chart(ctxDlmpHist, {
        type: 'line',
        data: {
            datasets: [
                {
                    label: `Bus ${plotAVal}`,
                    data: counts_dlmp_a.map((y, idx) => ({ x: centers_dlmp[idx], y: y })),
                    borderColor: '#3b82f6',
                    borderWidth: 3,
                    stepped: 'middle',
                    fill: false,
                    tension: 0,
                    pointRadius: 2
                },
                {
                    label: `Bus ${plotBVal}`,
                    data: counts_dlmp_b.map((y, idx) => ({ x: centers_dlmp[idx] + 0.1, y: y + 0.05 })),
                    borderColor: '#f59e0b',
                    borderWidth: 2,
                    borderDash: [5, 5],
                    stepped: 'middle',
                    fill: false,
                    tension: 0,
                    pointRadius: 0
                },
                {
                    label: `Bus ${plotCVal}`,
                    data: counts_dlmp_c.map((y, idx) => ({ x: centers_dlmp[idx] - 0.1, y: y - 0.05 })),
                    borderColor: '#e65100',
                    borderWidth: 1.5,
                    borderDash: [2, 2],
                    stepped: 'middle',
                    fill: false,
                    tension: 0,
                    pointRadius: 0
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: true } },
            scales: {
                x: {
                    type: 'linear',
                    title: { display: true, text: 'LAM_P', color: COLOR_TEXT_PRIMARY },
                    grid: { display: false }
                },
                y: {
                    min: 0,
                    title: { display: true, text: 'Count', color: COLOR_TEXT_PRIMARY },
                    grid: { color: 'rgba(211, 208, 198, 0.4)' }
                }
            }
        }
    });

    // Voltage Bounds Mean/Min/Max Line chart
    const vProfile = simulationResults.overview_plots.voltage_profile;
    const vLabels = vProfile.map(vp => vp.bus_id);
    const ctxVBounds = document.getElementById("chart-voltage-bounds").getContext("2d");
    chartInstances["v-bounds"] = new Chart(ctxVBounds, {
        type: 'line',
        data: {
            labels: vLabels,
            datasets: [
                {
                    label: 'Mean Vm',
                    data: vProfile.map(vp => vp.mean),
                    borderColor: '#2e7d32',
                    borderWidth: 2.5,
                    tension: 0.1,
                    fill: false,
                    pointRadius: 3
                },
                {
                    label: 'Min Vm',
                    data: vProfile.map(vp => vp.min - 0.002),
                    borderColor: '#c94a49',
                    borderWidth: 1.5,
                    borderDash: [5, 5],
                    tension: 0.1,
                    fill: false,
                    pointRadius: 0
                },
                {
                    label: 'Max Vm',
                    data: vProfile.map(vp => vp.max + 0.002),
                    borderColor: '#3b82f6',
                    borderWidth: 1.5,
                    borderDash: [5, 5],
                    tension: 0.1,
                    fill: false,
                    pointRadius: 0
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { title: { display: true, text: "Bara ID", color: COLOR_TEXT_PRIMARY } },
                y: {
                    title: { display: true, text: "Voltage [p.u.]", color: COLOR_TEXT_PRIMARY },
                    grid: { color: 'rgba(211, 208, 198, 0.4)' }
                }
            }
        }
    });

    // Maximum Branch Loading by Scenario Line Chart
    const scenarioIds = simulationResults.plot_data.scenarios_id;
    const maxLoadingPerScenario = simulationResults.plot_data.max_branch_loading_percent;
    const ctxBLoading = document.getElementById("chart-branch-loading-mean").getContext("2d");
    
    chartInstances["b-loading"] = new Chart(ctxBLoading, {
        type: 'line',
        data: {
            labels: scenarioIds,
            datasets: [{
                label: 'Max Branch Loading [%]',
                data: maxLoadingPerScenario,
                borderColor: '#4A7C59',
                borderWidth: 1.5,
                pointRadius: scenarioIds.length > 100 ? 0 : 2,
                fill: false,
                tension: 0.1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: {
                    title: { display: true, text: 'Scenario', color: COLOR_TEXT_PRIMARY },
                    grid: { color: 'rgba(211, 208, 198, 0.4)' }
                },
                y: {
                    title: { display: true, text: 'Max Branch Loading [%]', color: COLOR_TEXT_PRIMARY },
                    grid: { color: 'rgba(211, 208, 198, 0.4)' },
                    ticks: {
                        callback: function(value) {
                            return value.toExponential(2);
                        }
                    }
                }
            }
        }
    });

    // --- 2. ECONOMETRIC PLOTS (OLS Scatters & Demand Distributions) ---

    const pdMW = simulationResults.plot_data.total_Pd_MW;
    const centers_pd = simulationResults.overview_plots.centers_pd || [];
    const counts_pd = simulationResults.overview_plots.counts_pd || [];

    // Update panel titles dynamically to show selected bus numbers
    if (document.getElementById("ttl-ols-a")) {
        document.getElementById("ttl-ols-a").textContent = `Bus ${plotAVal} DLMP vs Total Demand`;
    }
    if (document.getElementById("ttl-ols-b")) {
        document.getElementById("ttl-ols-b").textContent = `Bus ${plotBVal} DLMP vs Total Demand`;
    }
    if (document.getElementById("ttl-ols-c")) {
        document.getElementById("ttl-ols-c").textContent = `Bus ${plotCVal} DLMP vs Total Demand`;
    }

    const scatterColor = '#1e40af'; // Premium blue color matching MATLAB's default scatter
    const distLineColor = '#dc2626'; // Premium red color matching MATLAB's 'r-' line

    const makeOlsDualChart = (ctx, dlmpData, busId) => {
        return new Chart(ctx, {
            data: {
                datasets: [
                    {
                        type: 'scatter',
                        label: `Bus ${busId} DLMP`,
                        data: pdMW.map((pd, i) => ({ x: pd, y: dlmpData[i] })),
                        backgroundColor: scatterColor,
                        yAxisID: 'y'
                    },
                    {
                        type: 'line',
                        label: 'Total Pd distribution',
                        data: centers_pd.map((c, i) => ({ x: c, y: counts_pd[i] })),
                        borderColor: distLineColor,
                        borderWidth: 1.5,
                        fill: false,
                        tension: 0.1,
                        pointRadius: 0,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: {
                        type: 'linear',
                        title: { display: true, text: 'Total Pd [MW]', color: COLOR_TEXT_PRIMARY },
                        grid: { display: false }
                    },
                    y: {
                        type: 'linear',
                        position: 'left',
                        title: { display: true, text: `Bus ${busId} DLMP`, color: COLOR_TEXT_PRIMARY },
                        grid: { color: 'rgba(211, 208, 198, 0.4)' }
                    },
                    y1: {
                        type: 'linear',
                        position: 'right',
                        min: 0,
                        title: { display: true, text: 'Total Pd distribution [count]', color: COLOR_TEXT_PRIMARY },
                        grid: { drawOnChartArea: false },
                        ticks: {
                            precision: 0
                        }
                    }
                }
            }
        });
    };

    const makeOlsBottomChart = (ctx, yData, labelY) => {
        return new Chart(ctx, {
            type: 'scatter',
            data: {
                datasets: [{
                    data: pdMW.map((pd, i) => ({ x: pd, y: yData[i] })),
                    backgroundColor: scatterColor
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: {
                        type: 'linear',
                        title: { display: true, text: 'Total Pd [MW]', color: COLOR_TEXT_PRIMARY },
                        grid: { display: false }
                    },
                    y: {
                        type: 'linear',
                        position: 'left',
                        title: { display: true, text: labelY, color: COLOR_TEXT_PRIMARY },
                        grid: { color: 'rgba(211, 208, 198, 0.4)' }
                    },
                    y1: {
                        type: 'linear',
                        position: 'right',
                        min: 0,
                        max: 1,
                        grid: { drawOnChartArea: false },
                        ticks: {
                            stepSize: 0.1
                        }
                    }
                }
            }
        });
    };

    // Instantiate Top Row (Dual Axis Charts)
    const ctxOlsA = document.getElementById("chart-dlmp-vs-demand-a").getContext("2d");
    chartInstances["ols-a"] = makeOlsDualChart(ctxOlsA, dlmps_a, plotAVal);

    const ctxOlsB = document.getElementById("chart-dlmp-vs-demand-b").getContext("2d");
    chartInstances["ols-b"] = makeOlsDualChart(ctxOlsB, dlmps_b, plotBVal);

    const ctxOlsC = document.getElementById("chart-dlmp-vs-demand-c").getContext("2d");
    chartInstances["ols-c"] = makeOlsDualChart(ctxOlsC, dlmps_c, plotCVal);

    // Instantiate Bottom Row (Scatter Charts with Right Y-Axis Ticks)
    const ctxCost = document.getElementById("chart-cost-vs-demand").getContext("2d");
    chartInstances["ols-cost"] = makeOlsBottomChart(ctxCost, simulationResults.plot_data.objective_cost, 'Objective Cost');

    const ctxLosses = document.getElementById("chart-losses-vs-demand").getContext("2d");
    chartInstances["ols-losses"] = makeOlsBottomChart(ctxLosses, simulationResults.plot_data.total_P_loss_MW, 'Total P Loss [MW]');

    const ctxC2l = document.getElementById("chart-c2l-vs-demand").getContext("2d");
    chartInstances["ols-c2l"] = makeOlsBottomChart(ctxC2l, simulationResults.plot_data.cost_to_load_total, 'C2L');


    // --- 3. VALIDATION DIAGNOSTICS PLOTS ---

    if (simulationResults.validation_table && simulationResults.validation_table.length > 0) {
        const valData = simulationResults.validation_table;
        const valIds = valData.map(v => v.scenario_id);
        const vmErrors = valData.map(v => v.max_abs_Vm_error);
        const vaErrors = valData.map(v => v.max_abs_Va_error);
        const flowErrors = valData.map(v => v.max_abs_Pf_error);

        // Validation error severity plot
        const ctxValSev = document.getElementById("chart-val-severity").getContext("2d");
        chartInstances["val-sev"] = new Chart(ctxValSev, {
            type: 'line',
            data: {
                labels: valIds,
                datasets: [
                    {
                        label: 'Max Vm Error (pu)',
                        data: vmErrors,
                        borderColor: '#2e7d32',
                        borderWidth: 1.5,
                        fill: false
                    },
                    {
                        label: 'Max Va Error (deg)',
                        data: vaErrors,
                        borderColor: '#3b82f6',
                        borderWidth: 1.5,
                        fill: false
                    },
                    {
                        label: 'Max Pf Flow Error (MW)',
                        data: flowErrors,
                        borderColor: '#e65100',
                        borderWidth: 1.5,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { title: { display: true, text: "Senaryo ID" } },
                    y: { type: 'logarithmic', title: { display: true, text: "Hata Büyüklüğü (Log)" } }
                }
            }
        });

        // Fail reasons distribution pie chart
        const ctxFailPie = document.getElementById("chart-val-failures").getContext("2d");
        const failLabels = Object.keys(simulationResults.validation_fail_reasons);
        const failCounts = Object.values(simulationResults.validation_fail_reasons);
        
        chartInstances["fail-pie"] = new Chart(ctxFailPie, {
            type: 'pie',
            data: {
                labels: failLabels.length > 0 ? failLabels : ["Pass / No Mismatch"],
                datasets: [{
                    data: failCounts.length > 0 ? failCounts : [valData.length],
                    backgroundColor: ['#4A7C59', '#c94a49', '#3b82f6', '#e65100', '#f4c430', '#8e24aa']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });
    }
}

// Switch Tab Navigation & update sidebar controls context
function switchTab(tabId) {
    document.querySelectorAll(".tab-btn").forEach(btn => {
        if (btn.getAttribute("onclick").includes(tabId)) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    });

    document.querySelectorAll(".tab-panel").forEach(panel => {
        if (panel.id === tabId) {
            panel.classList.add("active");
        } else {
            panel.classList.remove("active");
        }
    });

    updateContextControls(tabId);
}

// MATLAB-like dynamic sidebar visibility updates
function updateContextControls(tabId) {
    const sidebarPanel = document.getElementById("sidebar-panel");
    const sidebarTitle = document.getElementById("sidebar-title");
    
    if (tabId === "tab-bulk-editor") {
        sidebarPanel.style.display = "none";
        return;
    } else {
        sidebarPanel.style.display = "flex";
    }

    const cardScenario = document.getElementById("card-scenario-settings");
    const cardEditor = document.getElementById("card-quick-editor");
    const cardPlot = document.getElementById("card-plot-selectors");
    const cardVal = document.getElementById("card-validation-export");
    const cardContext = document.getElementById("card-context-info");
    const valGroup = document.getElementById("run-validation-group");
    const cardCase = document.getElementById("card-case-selectors");

    // Default: hide all
    cardScenario.style.display = "none";
    cardEditor.style.display = "none";
    cardPlot.style.display = "none";
    cardVal.style.display = "none";
    cardContext.style.display = "none";
    cardCase.style.display = "none";
    valGroup.style.display = "flex";

    const textarea = document.getElementById("sidebar-context-info");

    if (tabId === "tab-topology") {
        sidebarTitle.textContent = "Context Controls | Network Topology";
        cardScenario.style.display = "block";
        cardEditor.style.display = "block";
        cardCase.style.display = "block";
    } else if (tabId === "tab-overview") {
        sidebarTitle.textContent = "Context Controls | Overview";
        cardContext.style.display = "block";
        cardPlot.style.display = "block";
        updateOverviewContextInfo();
    } else if (tabId === "tab-econometric") {
        sidebarTitle.textContent = "Context Controls | Econometric Outputs";
        cardPlot.style.display = "block";
        cardContext.style.display = "block";
        textarea.value = "ECONOMETRIC PLOT CONTROLS\n\n• Select Plot Bus A/B/C.\n• The three selected buses define DLMP-vs-demand plots.\n• Purple labels on topology show selected plot buses.\n• Scatter points show scenario-level DLMP behavior.\n• Red curve shows total demand distribution.";
    } else if (tabId === "tab-validation") {
        sidebarTitle.textContent = "Context Controls | Validation Diagnostics";
        cardVal.style.display = "block";
        cardContext.style.display = "block";
        textarea.value = "VALIDATION GUIDE\n\n• RUNPF success: reconstructed power flow converged.\n• Validation pass: RUNPF output matches OPF output.\n• Vm tolerance      : 1e-5 p.u.\n• Va tolerance      : 1e-3 deg.\n• P/Q tolerance     : 1e-4 MW/MVAr.\n• Loading tolerance : 1e-3 % if RATE_A is defined.\n• If RATE_A is zero/undefined, loading check is N/A.\n\nTip: Enable Run validation before scenario generation.";
    } else if (tabId === "tab-preview") {
        sidebarTitle.textContent = "Context Controls | Data Preview / Export";
        cardVal.style.display = "block";
        valGroup.style.display = "none"; // Hide checkbox in data preview
        cardContext.style.display = "block";
        textarea.value = "DATA PREVIEW / EXPORT\n\n• scenario_dataset: scenario-level summary.\n• bus_results_long: one row per scenario-bus.\n• branch_results_long: one row per scenario-branch.\n• gen_results_long: one row per scenario-generator.\n• Save Current Results exports the current dataset.";
    }
}

function updateOverviewContextInfo() {
    const textarea = document.getElementById("sidebar-context-info");
    if (!simulationResults) {
        textarea.value = "OVERVIEW\n\n• No scenario dataset generated yet.\n• Configure the network in Network Topology.\n• Click Generate Scenarios + Analyze.\n• Overview plots will summarize demand, DLMP, voltage and loading.";
        return;
    }

    const nScenarios = simulationResults.plot_data.scenarios_id.length;
    const pdVec = simulationResults.plot_data.total_Pd_MW;
    const minPd = Math.min(...pdVec);
    const maxPd = Math.max(...pdVec);
    const meanPd = pdVec.reduce((a,b)=>a+b, 0) / pdVec.length;

    // Max loading
    let maxLoading = 0;
    if (simulationResults.branches && simulationResults.branches.length > 0) {
        maxLoading = Math.max(...simulationResults.branches.map(b => b.loading_percent));
    }

    // Mean DLMP
    let meanDlmp = 0;
    if (simulationResults.buses && simulationResults.buses.length > 0) {
        meanDlmp = simulationResults.buses.reduce((a,b) => a + b.DLMP_LAM_P, 0) / simulationResults.buses.length;
    }

    let text = "DATASET SUMMARY\n\n";
    text += `• Scenarios              : ${nScenarios}\n`;
    text += `• Total Pd range [MW]    : ${formatNum(minPd, 3)} – ${formatNum(maxPd, 3)}\n`;
    text += `• Mean total Pd [MW]     : ${formatNum(meanPd, 3)}\n`;
    text += `• Max loading [%]        : ${formatNum(maxLoading, 3)}\n`;
    text += `• Mean DLMP LAM_P        : ${formatNum(meanDlmp, 3)}\n\n`;
    text += "Use Overview plots to inspect system-level behavior.";

    textarea.value = text;
}

