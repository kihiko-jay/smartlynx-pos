/**
 * Smartlynx Setup Wizard
 *
 * First-run configuration wizard for technicians/shop owners.
 * Guides setup of: server address, terminal ID, printer, and store details.
 *
 * Implemented as standalone Electron window with embedded HTML/CSS/JS.
 * Uses vanilla JS (no React) to keep it lightweight and independent of main app state.
 */

/**
 * Generate the complete HTML/CSS/JS for the setup wizard.
 * Self-contained, no external dependencies.
 * 
 * @param {BrowserWindow|null} parentWindow - Not used (kept for backwards compatibility)
 * @returns {string} Complete HTML string for data URL loading
 */
function getSetupWizardHTML(parentWindow) {
  return `
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>SmartlynX Setup Wizard</title>
  <style>
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      font-family: 'Tahoma', 'Verdana', 'Arial', sans-serif;
      background: linear-gradient(180deg, #f6f8fb 0%, #edf2f8 100%);
      color: #1a1a1a;
      padding: 0;
      margin: 0;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    /* Progress indicator */
    .wizard-header {
      background: linear-gradient(180deg, #155eef 0%, #003eb3 100%);
      color: #fff;
      padding: 20px;
      text-align: center;
      border-bottom: 2px solid #0b3186;
      flex-shrink: 0;
    }

    .wizard-header h1 {
      font-size: 20px;
      font-weight: 700;
      letter-spacing: 0.02em;
      margin-bottom: 12px;
    }

    .progress-indicator {
      display: flex;
      justify-content: center;
      gap: 8px;
      align-items: center;
    }

    .progress-dot {
      width: 24px;
      height: 24px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.3);
      border: 2px solid rgba(255, 255, 255, 0.5);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 11px;
      font-weight: 700;
      color: #fff;
      transition: all 0.3s ease;
    }

    .progress-dot.active {
      background: #fff;
      color: #155eef;
      border-color: #fff;
    }

    .progress-dot.completed {
      background: #4ade80;
      border-color: #4ade80;
      color: #fff;
    }

    .progress-separator {
      width: 12px;
      height: 2px;
      background: rgba(255, 255, 255, 0.3);
    }

    /* Main content */
    .wizard-container {
      flex: 1;
      overflow-y: auto;
      padding: 30px;
      display: flex;
      flex-direction: column;
    }

    .step {
      display: none;
      animation: fadeIn 0.2s ease;
    }

    .step.active {
      display: block;
    }

    @keyframes fadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }

    .step h2 {
      font-size: 24px;
      font-weight: 700;
      margin-bottom: 12px;
      color: #155eef;
    }

    .step .description {
      font-size: 14px;
      color: #666;
      margin-bottom: 28px;
      line-height: 1.5;
    }

    .step .group {
      margin-bottom: 24px;
    }

    label {
      display: block;
      font-size: 12px;
      color: #999;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-bottom: 8px;
      font-weight: 600;
    }

    input[type="text"],
    input[type="email"],
    input[type="password"],
    select {
      width: 100%;
      padding: 12px 14px;
      border: 1px solid #92a8c9;
      border-radius: 4px;
      font-family: inherit;
      font-size: 14px;
      color: #1a1a1a;
      background: #fff;
      outline: none;
      transition: border-color 0.2s, box-shadow 0.2s;
    }

    input[type="text"]:focus,
    input[type="email"]:focus,
    input[type="password"]:focus,
    select:focus {
      border-color: #155eef;
      box-shadow: 0 0 0 2px rgba(21, 94, 239, 0.12);
    }

    input[type="text"]:disabled,
    select:disabled {
      background: #f0f0f0;
      color: #999;
      cursor: not-allowed;
    }

    .help-text {
      font-size: 12px;
      color: #888;
      margin-top: 6px;
      line-height: 1.4;
    }

    .example-text {
      font-size: 12px;
      color: #bbb;
      font-family: 'Courier New', monospace;
      margin-top: 4px;
      padding: 6px 8px;
      background: #f5f5f5;
      border-radius: 3px;
    }

    /* Mode cards (Step 2) */
    .mode-cards {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-bottom: 24px;
    }

    .mode-card {
      padding: 20px;
      border: 2px solid #9eb2ce;
      border-radius: 6px;
      cursor: pointer;
      background: #fff;
      transition: all 0.2s ease;
    }

    .mode-card:hover {
      border-color: #155eef;
      background: #f8fafc;
    }

    .mode-card input[type="radio"] {
      margin-right: 8px;
    }

    .mode-card.selected {
      border-color: #155eef;
      background: #eff6ff;
      box-shadow: 0 0 0 3px rgba(21, 94, 239, 0.1);
    }

    .mode-card-title {
      font-weight: 700;
      font-size: 13px;
      margin-bottom: 6px;
      display: flex;
      align-items: center;
    }

    .mode-card-desc {
      font-size: 12px;
      color: #666;
      line-height: 1.4;
    }

    /* Checkbox toggle */
    .checkbox-group {
      display: flex;
      align-items: flex-start;
      gap: 12px;
    }

    .checkbox-group input[type="checkbox"] {
      width: auto;
      margin-top: 2px;
      cursor: pointer;
    }

    .checkbox-group label {
      margin: 0;
      text-transform: none;
      letter-spacing: normal;
      color: #666;
      font-weight: 400;
      font-size: 14px;
      flex: 1;
    }

    /* Status messages */
    .status-message {
      padding: 12px 14px;
      border-radius: 4px;
      font-size: 13px;
      margin-top: 12px;
      display: none;
      animation: slideIn 0.2s ease;
    }

    @keyframes slideIn {
      from { opacity: 0; transform: translateY(-4px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .status-success {
      background: #d1e7dd;
      color: #0f5132;
      border: 1px solid #badbcc;
      display: block;
    }

    .status-error {
      background: #f8d7da;
      color: #842029;
      border: 1px solid #f5c2c7;
      display: block;
    }

    .status-warning {
      background: #fff3cd;
      color: #664d03;
      border: 1px solid #ffecb5;
      display: block;
    }

    /* Buttons */
    .step-actions {
      display: flex;
      gap: 12px;
      justify-content: flex-start;
      margin-top: 40px;
      flex-shrink: 0;
    }

    button {
      padding: 12px 24px;
      border: none;
      border-radius: 4px;
      font-family: inherit;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
      outline: none;
    }

    button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .btn-primary {
      background: #155eef;
      color: #fff;
    }

    .btn-primary:hover:not(:disabled) {
      background: #0d47bb;
    }

    .btn-secondary {
      background: #e5e7eb;
      color: #374151;
    }

    .btn-secondary:hover:not(:disabled) {
      background: #d1d5db;
    }

    .btn-secondary-outline {
      background: transparent;
      border: 1px solid #9eb2ce;
      color: #155eef;
    }

    .btn-secondary-outline:hover:not(:disabled) {
      background: #f0f6ff;
      border-color: #155eef;
    }

    .btn-sm {
      padding: 8px 14px;
      font-size: 12px;
    }

    /* Checklist (Step 7) */
    .checklist {
      list-style: none;
      flex: 1;
    }

    .checklist li {
      padding: 12px 0;
      border-bottom: 1px solid #e5e7eb;
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 14px;
    }

    .checklist li:last-child {
      border-bottom: none;
    }

    .checklist-icon {
      width: 20px;
      height: 20px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      font-size: 12px;
      font-weight: 700;
    }

    .checklist-icon.success {
      background: #d1e7dd;
      color: #0f5132;
    }

    .checklist-icon.error {
      background: #f8d7da;
      color: #842029;
    }

    .checklist-icon.warning {
      background: #fff3cd;
      color: #664d03;
    }

    /* Summary (Step 8) */
    .summary-block {
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      border-radius: 4px;
      padding: 16px;
      margin-bottom: 16px;
    }

    .summary-item {
      display: flex;
      justify-content: space-between;
      padding: 8px 0;
      font-size: 14px;
    }

    .summary-label {
      color: #666;
      font-weight: 500;
    }

    .summary-value {
      color: #1a1a1a;
      font-weight: 600;
    }

    /* Test login modal */
    .test-login-modal {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(3, 15, 39, 0.58);
      z-index: 1000;
      align-items: center;
      justify-content: center;
    }

    .test-login-modal.active {
      display: flex;
    }

    .test-login-modal-content {
      background: #fff;
      border-radius: 6px;
      padding: 24px;
      width: 90%;
      max-width: 380px;
      box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15);
    }

    .test-login-modal-content h3 {
      font-size: 16px;
      font-weight: 700;
      margin-bottom: 16px;
      color: #155eef;
    }

    .test-login-modal-content .group {
      margin-bottom: 14px;
    }

    .test-login-modal-actions {
      display: flex;
      gap: 12px;
      margin-top: 20px;
      justify-content: flex-end;
    }

    /* Scrollbar styling */
    .wizard-container::-webkit-scrollbar {
      width: 8px;
    }

    .wizard-container::-webkit-scrollbar-track {
      background: transparent;
    }

    .wizard-container::-webkit-scrollbar-thumb {
      background: #9fb3d6;
      border-radius: 4px;
    }

    .wizard-container::-webkit-scrollbar-thumb:hover {
      background: #7a8fb5;
    }
  </style>
</head>
<body>
  <div class="wizard-header">
    <h1>Welcome to SmartlynX Setup</h1>
    <div class="progress-indicator">
      <div class="progress-dot active" id="dot-1">1</div>
      <div class="progress-separator"></div>
      <div class="progress-dot" id="dot-2">2</div>
      <div class="progress-separator"></div>
      <div class="progress-dot" id="dot-3">3</div>
      <div class="progress-separator"></div>
      <div class="progress-dot" id="dot-4">4</div>
      <div class="progress-separator"></div>
      <div class="progress-dot" id="dot-5">5</div>
      <div class="progress-separator"></div>
      <div class="progress-dot" id="dot-6">6</div>
      <div class="progress-separator"></div>
      <div class="progress-dot" id="dot-7">7</div>
      <div class="progress-separator"></div>
      <div class="progress-dot" id="dot-8">8</div>
    </div>
  </div>

  <div class="wizard-container">
    <!-- Step 1: Welcome -->
    <div class="step active" data-step="1">
      <h2>Welcome to SmartlynX</h2>
      <div class="description">
        This wizard will help you connect this computer to your SmartlynX point-of-sale system. We'll configure your server address, terminal ID, printer, and store details.
        <br><br>
        You can complete this setup now or revisit it later from the Settings menu.
      </div>
      <div class="step-actions">
        <button class="btn-primary" onclick="goToStep(2)">Start Setup</button>
        <button class="btn-secondary" onclick="closeWizard()">Cancel</button>
      </div>
    </div>

    <!-- Step 2: Setup Mode -->
    <div class="step" data-step="2">
      <h2>How is your system set up?</h2>
      <div class="description">Choose where your SmartlynX backend server is located.</div>
      
      <div class="mode-cards">
        <div class="mode-card" onclick="selectMode('single', this)">
          <div class="mode-card-title">
            <input type="radio" name="setupMode" value="single">
            Single Computer
          </div>
          <div class="mode-card-desc">Backend is on this same machine</div>
        </div>
        
        <div class="mode-card" onclick="selectMode('server', this)">
          <div class="mode-card-title">
            <input type="radio" name="setupMode" value="server">
            Shop Server
          </div>
          <div class="mode-card-desc">Backend runs on another computer</div>
        </div>
      </div>
      
      <div class="step-actions">
        <button class="btn-secondary" onclick="goToStep(1)">Back</button>
        <button class="btn-primary" id="btn-step2-next" disabled onclick="goToStep(3)">Next</button>
      </div>
    </div>

    <!-- Step 3: Server Connection -->
    <div class="step" data-step="3">
      <h2>Shop Server Address</h2>
      <div class="description">Enter the address of your SmartlynX backend server.</div>
      
      <div class="group">
        <label>Server Address</label>
        <input type="text" id="apiBase" placeholder="http://192.168.1.10:8000/api/v1" />
        <div class="example-text">Example: http://192.168.1.10:8000/api/v1</div>
      </div>

      <div class="group">
        <button class="btn-secondary btn-sm" onclick="testConnection()" id="btn-test-conn">Test Connection</button>
        <div class="status-message" id="status-connection"></div>
      </div>

      <div class="help-text">
        Need help? Ask your SmartlynX technician or installer for your server address.
      </div>

      <div class="step-actions">
        <button class="btn-secondary" onclick="goToStep(2)">Back</button>
        <button class="btn-primary" id="btn-step3-next" disabled onclick="goToStep(4)">Next</button>
      </div>
    </div>

    <!-- Step 4: Terminal ID -->
    <div class="step" data-step="4">
      <h2>Terminal Identifier</h2>
      <div class="description">Each cashier machine needs a unique terminal ID for tracking sales.</div>
      
      <div class="group">
        <label>Terminal ID</label>
        <input type="text" id="terminalId" placeholder="T01" maxlength="20" />
        <div class="help-text">Examples: T01, T02, FRONTDESK, CASHIER1</div>
      </div>

      <div class="step-actions">
        <button class="btn-secondary" onclick="goToStep(3)">Back</button>
        <button class="btn-primary" id="btn-step4-next" disabled onclick="goToStep(5)">Next</button>
      </div>
    </div>

    <!-- Step 5: Printer Setup -->
    <div class="step" data-step="5">
      <h2>Receipt Printer</h2>
      <div class="description">Select your receipt printer and optional settings.</div>
      
      <div class="group">
        <label>Receipt Printer</label>
        <select id="printerName">
          <option value="">-- Select Printer --</option>
        </select>
        <button class="btn-secondary btn-sm" onclick="refreshPrinters()" id="btn-refresh-printers" style="margin-top: 8px;">Refresh Printers</button>
      </div>

      <div class="help-text" id="printer-warning" style="display: none;">
        ⚠ No printer selected. Receipts will not print, but the system will continue to function.
      </div>

      <div class="group">
        <button class="btn-secondary btn-sm" onclick="testPrintReceipt()" id="btn-test-print" disabled>Print Test Receipt</button>
        <div class="status-message" id="status-print"></div>
      </div>

      <div class="group">
        <div class="checkbox-group">
          <input type="checkbox" id="kioskMode">
          <label for="kioskMode">Fullscreen cashier mode (use in production)</label>
        </div>
        <div class="help-text">Disables title bar and window controls for a cleaner, distraction-free interface.</div>
      </div>

      <div class="step-actions">
        <button class="btn-secondary" onclick="goToStep(4)">Back</button>
        <button class="btn-primary" onclick="goToStep(6)">Next</button>
      </div>
    </div>

    <!-- Step 6: Store Details -->
    <div class="step" data-step="6">
      <h2>Store Information</h2>
      <div class="description">These details appear on receipts and reports.</div>
      
      <div class="group">
        <label>Store Name</label>
        <input type="text" id="storeName" placeholder="My Duka Store" />
      </div>

      <div class="group">
        <label>Store Location</label>
        <input type="text" id="storeLocation" placeholder="Nairobi, Kenya" />
      </div>

      <div class="group">
        <label>KRA PIN</label>
        <input type="text" id="kraPin" placeholder="P001234567N" />
        <div class="help-text">Your KRA Personal Identification Number (printed on receipts)</div>
      </div>

      <div class="step-actions">
        <button class="btn-secondary" onclick="goToStep(5)">Back</button>
        <button class="btn-primary" onclick="goToStep(7)">Next</button>
      </div>
    </div>

    <!-- Step 7: Final Checks -->
    <div class="step" data-step="7">
      <h2>Final Verification</h2>
      <div class="description">Review your configuration before completing setup.</div>
      
      <ul class="checklist">
        <li>
          <div class="checklist-icon success" id="check-server">✓</div>
          <div id="check-server-text">Server reachable</div>
        </li>
        <li>
          <div class="checklist-icon success" id="check-terminal">✓</div>
          <div id="check-terminal-text">Terminal ID configured</div>
        </li>
        <li>
          <div class="checklist-icon" id="check-printer">?</div>
          <div id="check-printer-text">Printer selected (optional)</div>
        </li>
        <li>
          <div class="checklist-icon success" id="check-required">✓</div>
          <div id="check-required-text">All required fields complete</div>
        </li>
      </ul>

      <div class="group" style="margin-top: 24px;">
        <button class="btn-secondary btn-sm" onclick="showTestLoginModal()">Test Login (Optional)</button>
        <div class="status-message" id="status-login"></div>
      </div>

      <div class="step-actions">
        <button class="btn-secondary" onclick="goToStep(6)">Back</button>
        <button class="btn-primary" onclick="goToStep(8)">Finish Setup</button>
      </div>
    </div>

    <!-- Step 8: Finish -->
    <div class="step" data-step="8">
      <h2>Setup Complete!</h2>
      <div class="description">Your SmartlynX system is now configured.</div>
      
      <div class="summary-block">
        <div class="summary-item">
          <span class="summary-label">Setup Mode:</span>
          <span class="summary-value" id="summary-mode">-</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">Server Address:</span>
          <span class="summary-value" id="summary-server">-</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">Terminal ID:</span>
          <span class="summary-value" id="summary-terminal">-</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">Printer:</span>
          <span class="summary-value" id="summary-printer">-</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">Store Name:</span>
          <span class="summary-value" id="summary-store">-</span>
        </div>
      </div>

      <div class="step-actions">
        <button class="btn-primary" onclick="finishSetup()">Open SmartlynX</button>
        <button class="btn-secondary" onclick="openSettings()">Open Settings</button>
        <button class="btn-secondary" onclick="closeWizard()">Close</button>
      </div>
    </div>
  </div>

  <!-- Test Login Modal -->
  <div class="test-login-modal" id="testLoginModal">
    <div class="test-login-modal-content">
      <h3>Test Account Login</h3>
      
      <div class="group">
        <label>Email</label>
        <input type="email" id="testEmail" placeholder="admin@dukapos.com" />
      </div>

      <div class="group">
        <label>Password</label>
        <input type="password" id="testPassword" placeholder="••••••••" />
      </div>

      <div class="status-message" id="status-test-login"></div>

      <div class="test-login-modal-actions">
        <button class="btn-secondary" onclick="closeTestLoginModal()">Cancel</button>
        <button class="btn-primary" id="btn-test-login-submit" onclick="submitTestLogin()">Test Login</button>
      </div>
    </div>
  </div>

  <script>
    // State
    let currentStep = 1;
    let connectionTested = false;
    let setupMode = null;
    let config = {
      apiBase: "",
      terminalId: "",
      storeName: "",
      storeLocation: "",
      kraPin: "",
      kioskMode: false,
      printerName: "",
    };

    // Initialize
    async function init() {
      if (!window.electron) {
        console.error("Electron API not available");
        return;
      }

      try {
        const cfg = await window.electron.config.getAll();
        config = { ...config, ...cfg };
        
        // Load current values into form fields
        if (config.apiBase) document.getElementById("apiBase").value = config.apiBase;
        if (config.terminalId) document.getElementById("terminalId").value = config.terminalId;
        if (config.storeName) document.getElementById("storeName").value = config.storeName;
        if (config.storeLocation) document.getElementById("storeLocation").value = config.storeLocation;
        if (config.kraPin) document.getElementById("kraPin").value = config.kraPin;
        document.getElementById("kioskMode").checked = config.kioskMode || false;

        // Load printers
        await refreshPrinters();
      } catch (err) {
        console.error("Init error:", err);
      }
    }

    function goToStep(step) {
      // Validate current step before moving forward
      if (step > currentStep && !validateStep(currentStep)) {
        return;
      }

      // Save current step data
      saveStepData(currentStep);

      // Update UI
      document.querySelectorAll(".step").forEach(el => el.classList.remove("active"));
      document.querySelector(\`[data-step="\${step}"]\`).classList.add("active");

      // Update progress
      updateProgress(step);
      currentStep = step;

      // Trigger step-specific logic
      onStepEnter(step);
    }

    function validateStep(step) {
      switch (step) {
        case 2:
          if (!setupMode) {
            alert("Please select a setup mode");
            return false;
          }
          return true;
        case 3:
          const apiBase = document.getElementById("apiBase").value.trim();
          if (!apiBase) {
            alert("Please enter a server address");
            return false;
          }
          if (!connectionTested) {
            alert("Please test the connection before proceeding");
            return false;
          }
          return true;
        case 4:
          const terminalId = document.getElementById("terminalId").value.trim();
          if (!terminalId) {
            alert("Please enter a terminal ID");
            return false;
          }
          return true;
        default:
          return true;
      }
    }

    function saveStepData(step) {
      switch (step) {
        case 3:
          config.apiBase = document.getElementById("apiBase").value.trim();
          break;
        case 4:
          config.terminalId = document.getElementById("terminalId").value.trim();
          break;
        case 5:
          config.kioskMode = document.getElementById("kioskMode").checked;
          config.printerName = document.getElementById("printerName").value;
          break;
        case 6:
          config.storeName = document.getElementById("storeName").value.trim();
          config.storeLocation = document.getElementById("storeLocation").value.trim();
          config.kraPin = document.getElementById("kraPin").value.trim();
          break;
      }
    }

    function onStepEnter(step) {
      switch (step) {
        case 5:
          updatePrinterWarning();
          break;
        case 7:
          runFinalChecks();
          break;
        case 8:
          populateSummary();
          break;
      }
    }

    function updateProgress(step) {
      for (let i = 1; i <= 8; i++) {
        const dot = document.getElementById(\`dot-\${i}\`);
        if (i < step) {
          dot.classList.remove("active");
          dot.classList.add("completed");
        } else if (i === step) {
          dot.classList.add("active");
          dot.classList.remove("completed");
        } else {
          dot.classList.remove("active", "completed");
        }
      }
    }

    function selectMode(mode, element) {
      setupMode = mode;
      document.querySelectorAll(".mode-card").forEach(el => el.classList.remove("selected"));
      element.classList.add("selected");
      element.querySelector("input[type='radio']").checked = true;
      document.getElementById("btn-step2-next").disabled = false;

      // Auto-prefill apiBase based on mode
      if (mode === "single") {
        document.getElementById("apiBase").value = "http://127.0.0.1:8000/api/v1";
      } else {
        document.getElementById("apiBase").value = "http://192.168.1.10:8000/api/v1";
      }
    }

    async function testConnection() {
      const apiBase = document.getElementById("apiBase").value.trim();
      if (!apiBase) {
        showStatus("connection", "error", "Please enter a server address");
        return;
      }

      const btnTest = document.getElementById("btn-test-conn");
      const statusDiv = document.getElementById("status-connection");
      btnTest.disabled = true;
      btnTest.textContent = "Testing...";

      try {
        const result = await window.electron.setup.testConnection({ apiBase });
        
        if (result.success) {
          showStatus("connection", "success", "✓ Connected successfully");
          connectionTested = true;
          document.getElementById("btn-step3-next").disabled = false;
        } else {
          showStatus("connection", "error", \`✗ \${result.error}\`);
          connectionTested = false;
          document.getElementById("btn-step3-next").disabled = true;
        }
      } catch (err) {
        showStatus("connection", "error", \`✗ Error: \${err.message}\`);
        connectionTested = false;
        document.getElementById("btn-step3-next").disabled = true;
      } finally {
        btnTest.disabled = false;
        btnTest.textContent = "Test Connection";
      }
    }

    async function refreshPrinters() {
      const btnRefresh = document.getElementById("btn-refresh-printers");
      btnRefresh.disabled = true;
      btnRefresh.textContent = "Loading...";

      try {
        const printers = await window.electron.setup.getPrinterList();
        const select = document.getElementById("printerName");
        
        // Keep the selected value
        const currentValue = select.value;
        select.innerHTML = '<option value="">-- Select Printer --</option>';
        
        printers.forEach(p => {
          const opt = document.createElement("option");
          opt.value = p.name;
          opt.textContent = p.name + (p.isDefault ? " (Default)" : "");
          if (p.name === currentValue) opt.selected = true;
          select.appendChild(opt);
        });

        updatePrinterWarning();
      } catch (err) {
        console.error("Printer list error:", err);
      } finally {
        btnRefresh.disabled = false;
        btnRefresh.textContent = "Refresh Printers";
      }
    }

    function updatePrinterWarning() {
      const printerName = document.getElementById("printerName").value;
      const warning = document.getElementById("printer-warning");
      const btnPrint = document.getElementById("btn-test-print");
      
      if (!printerName) {
        warning.style.display = "block";
        btnPrint.disabled = true;
      } else {
        warning.style.display = "none";
        btnPrint.disabled = false;
      }
    }

    async function testPrintReceipt() {
      const printerName = document.getElementById("printerName").value;
      if (!printerName) {
        showStatus("print", "warning", "⚠ No printer selected");
        return;
      }

      const btnPrint = document.getElementById("btn-test-print");
      btnPrint.disabled = true;
      btnPrint.textContent = "Printing...";

      try {
        const result = await window.electron.setup.testPrintReceipt({ printerName });
        if (result.success) {
          showStatus("print", "success", "✓ Test receipt sent to printer");
        } else {
          showStatus("print", "error", \`✗ Print failed: \${result.error}\`);
        }
      } catch (err) {
        showStatus("print", "error", \`✗ Error: \${err.message}\`);
      } finally {
        btnPrint.disabled = false;
        btnPrint.textContent = "Print Test Receipt";
      }
    }

    async function runFinalChecks() {
      // Server check
      const serverOk = connectionTested;
      updateCheckItem("server", serverOk, "Server reachable");
      
      // Terminal ID check
      const terminalOk = config.terminalId && config.terminalId.trim() !== "";
      updateCheckItem("terminal", terminalOk, "Terminal ID configured");
      
      // Printer check (optional, show warning if missing)
      const printerOk = !!config.printerName;
      updateCheckItem("printer", printerOk ? "success" : "warning", 
        printerOk ? "Printer selected" : "No printer selected (optional)");
      
      // Required fields check
      const requiredOk = config.apiBase && config.terminalId;
      updateCheckItem("required", requiredOk, "All required fields complete");
    }

    function updateCheckItem(id, success, text) {
      const icon = document.getElementById(\`check-\${id}\`);
      const textEl = document.getElementById(\`check-\${id}-text\`);
      
      if (success === "warning") {
        icon.className = "checklist-icon warning";
        icon.textContent = "⚠";
      } else if (success) {
        icon.className = "checklist-icon success";
        icon.textContent = "✓";
      } else {
        icon.className = "checklist-icon error";
        icon.textContent = "✗";
      }
      
      textEl.textContent = text;
    }

    function showTestLoginModal() {
      document.getElementById("testLoginModal").classList.add("active");
      document.getElementById("testEmail").focus();
    }

    function closeTestLoginModal() {
      document.getElementById("testLoginModal").classList.remove("active");
    }

    async function submitTestLogin() {
      const email = document.getElementById("testEmail").value.trim();
      const password = document.getElementById("testPassword").value;

      if (!email || !password) {
        showStatus("test-login", "error", "Please enter email and password");
        return;
      }

      const btnSubmit = document.getElementById("btn-test-login-submit");
      btnSubmit.disabled = true;
      btnSubmit.textContent = "Testing...";

      try {
        const result = await window.electron.setup.testLogin({ 
          apiBase: config.apiBase, 
          email, 
          password 
        });

        if (result.success) {
          showStatus("test-login", "success", 
            \`✓ Login successful! Welcome \${result.userName || "back"}\`);
          setTimeout(() => closeTestLoginModal(), 2000);
        } else {
          showStatus("test-login", "error", \`✗ \${result.error}\`);
        }
      } catch (err) {
        showStatus("test-login", "error", \`✗ Error: \${err.message}\`);
      } finally {
        btnSubmit.disabled = false;
        btnSubmit.textContent = "Test Login";
      }
    }

    function populateSummary() {
      document.getElementById("summary-mode").textContent = setupMode === "single" ? "Single Computer" : "Shop Server";
      document.getElementById("summary-server").textContent = config.apiBase || "-";
      document.getElementById("summary-terminal").textContent = config.terminalId || "-";
      document.getElementById("summary-printer").textContent = config.printerName || "(Not configured)";
      document.getElementById("summary-store").textContent = config.storeName || "(Not set)";
    }

    async function finishSetup() {
      saveStepData(6);

      try {
        // Batch save config
        const result = await window.electron.setup.saveConfig(config);
        if (!result.success) {
          alert("Failed to save configuration: " + result.error);
          return;
        }

        // Mark wizard completed
        await window.electron.setup.markCompleted();

        // Signal to parent that setup is done
        if (window.electron?.on) {
          // Emit via main process that wizard completed
        }

        // Close wizard
        closeWizard();
      } catch (err) {
        alert("Error finishing setup: " + err.message);
      }
    }

    async function openSettings() {
      // This would trigger reopen of settings from main process if needed
      // For now, just close the wizard
      closeWizard();
    }

    function closeWizard() {
      if (window.electron?.app?.close) {
        window.electron.app.close();
      } else {
        window.close();
      }
    }

    function showStatus(statusId, type, message) {
      const el = document.getElementById(\`status-\${statusId}\`);
      el.textContent = message;
      el.className = "status-message";
      el.classList.add(\`status-\${type}\`);
      el.style.display = "block";
    }

    // Input validation
    document.getElementById("terminalId")?.addEventListener("input", (e) => {
      document.getElementById("btn-step4-next").disabled = !e.target.value.trim();
    });

    document.getElementById("printerName")?.addEventListener("change", updatePrinterWarning);

    // Initialize on load
    init();
  </script>
</body>
</html>`;
}

module.exports = { getSetupWizardHTML };
