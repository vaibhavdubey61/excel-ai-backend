// Excel AI - Classy ChatGPT-style Mobile & Desktop Engine

let selectedFile = null;
let isRecording = false;
let speechRecognizer = null;
let currentSessionId = null;
let chatSessions = [];

document.addEventListener("DOMContentLoaded", () => {
    lucide.createIcons();
    initClipboardPaste();
    initSpeechRecognition();
    loadSessionsFromStorage();
    initStudentTrack();
});

// Student Course & Level Track
function initStudentTrack() {
    const course = localStorage.getItem("excel_user_course");
    const level = localStorage.getItem("excel_user_level");
    if (!course || !level) {
        openOnboardingModal(false);
    } else {
        updateCourseLevelBadges(course, level);
    }
}

function updateCourseLevelBadges(course, level) {
    const label = `${course} ${level}`;
    const hBadge = document.getElementById("header-course-level-badge");
    const sBadge = document.getElementById("sidebar-course-level-badge");
    if (hBadge) hBadge.innerText = label;
    if (sBadge) sBadge.innerText = label;
}

function openOnboardingModal(allowClose = true) {
    const modal = document.getElementById("onboarding-modal");
    if (!modal) return;
    const course = localStorage.getItem("excel_user_course") || "CA";
    const level = localStorage.getItem("excel_user_level") || "Inter";

    const cSelect = document.getElementById("onboarding-course-select");
    if (cSelect) cSelect.value = course;
    onOnboardingCourseChanged();
    const lSelect = document.getElementById("onboarding-level-select");
    if (lSelect) lSelect.value = level;

    modal.style.display = "flex";
    modal.classList.remove("hidden");
    lucide.createIcons();
}

function onOnboardingCourseChanged() {
    const cSelect = document.getElementById("onboarding-course-select");
    const lSelect = document.getElementById("onboarding-level-select");
    if (!cSelect || !lSelect) return;
    const course = cSelect.value;
    lSelect.innerHTML = "";

    const levelOptions = {
        "CA": ["Foundation", "Inter", "Final"],
        "CS": ["Executive", "Professional"],
        "CMA": ["Foundation", "Inter", "Final"]
    };

    const levels = levelOptions[course] || ["Foundation", "Inter", "Final"];
    levels.forEach(lvl => {
        const opt = document.createElement("option");
        opt.value = lvl;
        opt.innerText = lvl;
        lSelect.appendChild(opt);
    });
}

function saveStudentOnboarding() {
    const cSelect = document.getElementById("onboarding-course-select");
    const lSelect = document.getElementById("onboarding-level-select");
    const course = cSelect ? cSelect.value : "CA";
    const level = lSelect ? lSelect.value : "Inter";

    localStorage.setItem("excel_user_course", course);
    localStorage.setItem("excel_user_level", level);
    updateCourseLevelBadges(course, level);
    if (typeof populateMcqSubjects === "function") {
        populateMcqSubjects();
    }

    const modal = document.getElementById("onboarding-modal");
    if (modal) {
        modal.style.display = "none";
        modal.classList.add("hidden");
    }
}

// Auto-resize textarea
function autoResize(textarea) {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 140) + "px";
}

// Enter to send
function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

// Toggle Sidebar (Mobile & Desktop)
function toggleSidebar(forceState) {
    const sidebar = document.getElementById("chat-sidebar");
    const backdrop = document.getElementById("sidebar-backdrop");
    if (!sidebar) return;

    const isMobile = window.innerWidth < 768;

    if (isMobile) {
        const isClosed = sidebar.classList.contains("-translate-x-full");
        const nextState = forceState !== undefined ? forceState : isClosed;
        if (nextState) {
            sidebar.classList.remove("-translate-x-full");
            if (backdrop) backdrop.classList.remove("hidden");
        } else {
            sidebar.classList.add("-translate-x-full");
            if (backdrop) backdrop.classList.add("hidden");
        }
    } else {
        // Desktop collapse / expand
        const isClosed = sidebar.classList.contains("sidebar-closed-desktop");
        const nextState = forceState !== undefined ? forceState : isClosed;
        if (nextState) {
            sidebar.classList.remove("sidebar-closed-desktop");
        } else {
            sidebar.classList.add("sidebar-closed-desktop");
        }
    }
}

// Quick Prompt Click
function usePrompt(text) {
    if (text.toLowerCase().includes("mcq")) {
        openMcqModal();
        return;
    }
    const input = document.getElementById("chat-input");
    input.value = text;
    autoResize(input);
    input.focus();
    sendMessage();
}

// ----------------- CHAT SESSIONS & HISTORY -----------------

function loadSessionsFromStorage() {
    try {
        const stored = localStorage.getItem("excel_ai_sessions");
        chatSessions = stored ? JSON.parse(stored) : [];
    } catch (e) {
        chatSessions = [];
    }

    if (chatSessions.length === 0) {
        startNewChat();
    } else {
        // Load most recent session
        currentSessionId = chatSessions[0].id;
        renderHistory();
        renderActiveSessionMessages();
    }
}

function saveSessionsToStorage() {
    try {
        localStorage.setItem("excel_ai_sessions", JSON.stringify(chatSessions));
    } catch (e) {
        console.error("Storage save failed:", e);
    }
    renderHistory();
}

function startNewChat() {
    currentSessionId = "session_" + Date.now();
    const newSession = {
        id: currentSessionId,
        title: "New Chat",
        createdAt: Date.now(),
        messages: []
    };
    chatSessions.unshift(newSession);
    saveSessionsToStorage();

    // Reset UI to welcome screen
    document.getElementById("messages-container").innerHTML = "";
    document.getElementById("messages-container").classList.add("hidden");
    document.getElementById("welcome-view").classList.remove("hidden");
    document.getElementById("chat-input").value = "";
    autoResize(document.getElementById("chat-input"));
    clearAttachment();

    // Close sidebar on mobile
    toggleSidebar(false);
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
    }
}

function switchSession(id) {
    currentSessionId = id;
    renderHistory();
    renderActiveSessionMessages();
    toggleSidebar(false);
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
    }
}

function deleteSession(event, id) {
    event.stopPropagation();
    chatSessions = chatSessions.filter(s => s.id !== id);
    if (currentSessionId === id) {
        if (chatSessions.length > 0) {
            currentSessionId = chatSessions[0].id;
            renderActiveSessionMessages();
        } else {
            startNewChat();
            return;
        }
    }
    saveSessionsToStorage();
}

function renderHistory() {
    const list = document.getElementById("history-list");
    if (!list) return;

    if (chatSessions.length === 0) {
        list.innerHTML = `<p class="px-3 py-2 text-xs text-neutral-500 italic">No previous chats</p>`;
        return;
    }

    list.innerHTML = chatSessions.map(session => {
        const isActive = session.id === currentSessionId;
        const activeClass = isActive 
            ? "bg-[#212121] text-white font-semibold border border-[#333333]" 
            : "text-neutral-400 hover:text-white hover:bg-[#1f1f1f]";

        return `
            <div onclick="switchSession('${session.id}')" class="group flex items-center justify-between px-3 py-2 rounded-xl text-xs cursor-pointer transition ${activeClass}">
                <div class="flex items-center gap-2 truncate flex-1 min-w-0">
                    <i data-lucide="message-square" class="w-3.5 h-3.5 flex-shrink-0 ${isActive ? 'text-amber-400' : 'text-neutral-500'}"></i>
                    <span class="truncate">${escapeHtml(session.title || 'Conversation')}</span>
                </div>
                <button onclick="deleteSession(event, '${session.id}')" title="Delete chat" class="opacity-0 group-hover:opacity-100 hover:text-red-400 p-1 rounded transition">
                    <i data-lucide="trash-2" class="w-3 h-3"></i>
                </button>
            </div>
        `;
    }).join("");
    lucide.createIcons();
}

function renderActiveSessionMessages() {
    const session = chatSessions.find(s => s.id === currentSessionId);
    const container = document.getElementById("messages-container");
    const welcome = document.getElementById("welcome-view");

    if (!session || session.messages.length === 0) {
        container.innerHTML = "";
        container.classList.add("hidden");
        welcome.classList.remove("hidden");
        return;
    }

    welcome.classList.add("hidden");
    container.classList.remove("hidden");
    container.innerHTML = "";

    session.messages.forEach(msg => {
        if (msg.role === "user") {
            appendUserBubble(msg.content, msg.imageUrl, false);
        } else {
            appendAssistantBubble(msg.content, false);
        }
    });

    const viewport = document.getElementById("chat-viewport");
    viewport.scrollTop = viewport.scrollHeight;
    lucide.createIcons();
}

// ----------------- FILE ATTACHMENTS -----------------

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    setAttachment(file);
}

function setAttachment(file) {
    selectedFile = file;
    const previewContainer = document.getElementById("attachment-preview");
    const thumb = document.getElementById("attachment-thumb");
    const icon = document.getElementById("attachment-icon");
    const nameSpan = document.getElementById("attachment-name");

    nameSpan.innerText = file.name;
    previewContainer.classList.remove("hidden");

    if (file.type.startsWith("image/")) {
        const reader = new FileReader();
        reader.onload = (e) => {
            thumb.src = e.target.result;
            thumb.classList.remove("hidden");
            icon.classList.add("hidden");
        };
        reader.readAsDataURL(file);
    } else {
        thumb.classList.add("hidden");
        icon.classList.remove("hidden");
    }
    lucide.createIcons();
}

function clearAttachment() {
    selectedFile = null;
    document.getElementById("file-input").value = "";
    document.getElementById("attachment-preview").classList.add("hidden");
    document.getElementById("attachment-thumb").src = "";
}

// Clipboard Paste
function initClipboardPaste() {
    window.addEventListener("paste", (event) => {
        const items = (event.clipboardData || event.originalEvent.clipboardData).items;
        for (let item of items) {
            if (item.type.indexOf("image") === 0) {
                const blob = item.getAsFile();
                setAttachment(blob);
                break;
            }
        }
    });
}

// ----------------- VOICE RECOGNITION -----------------

function initSpeechRecognition() {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRec) {
        speechRecognizer = new SpeechRec();
        speechRecognizer.continuous = false;
        speechRecognizer.interimResults = false;
        speechRecognizer.lang = "en-IN";

        speechRecognizer.onstart = () => {
            isRecording = true;
            document.getElementById("voice-indicator").classList.remove("hidden");
            document.getElementById("mic-icon").setAttribute("data-lucide", "square");
            document.getElementById("voice-btn").classList.add("text-red-400", "bg-red-950/40");
            lucide.createIcons();
        };

        speechRecognizer.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            const input = document.getElementById("chat-input");
            input.value = (input.value ? input.value + " " : "") + transcript;
            autoResize(input);
        };

        speechRecognizer.onend = () => {
            isRecording = false;
            document.getElementById("voice-indicator").classList.add("hidden");
            document.getElementById("mic-icon").setAttribute("data-lucide", "mic");
            document.getElementById("voice-btn").classList.remove("text-red-400", "bg-red-950/40");
            lucide.createIcons();
        };

        speechRecognizer.onerror = (e) => {
            console.error("Speech Recognition Error:", e);
            isRecording = false;
            document.getElementById("voice-indicator").classList.add("hidden");
            document.getElementById("mic-icon").setAttribute("data-lucide", "mic");
            document.getElementById("voice-btn").classList.remove("text-red-400", "bg-red-950/40");
            lucide.createIcons();
        };
    }
}

function toggleVoiceInput() {
    if (!speechRecognizer) {
        alert("Voice input is supported in Google Chrome, Microsoft Edge, and Safari.");
        return;
    }
    if (isRecording) {
        speechRecognizer.stop();
    } else {
        speechRecognizer.start();
    }
}

// ----------------- SENDING MESSAGES -----------------

async function sendMessage() {
    const input = document.getElementById("chat-input");
    const text = input.value.trim();
    const currentAttachment = selectedFile;

    if (!text && !currentAttachment) return;

    // Ensure session exists
    let session = chatSessions.find(s => s.id === currentSessionId);
    if (!session) {
        startNewChat();
        session = chatSessions[0];
    }

    // Auto-name chat title on first message
    if (session.messages.length === 0 && text) {
        session.title = text.length > 28 ? text.substring(0, 28) + "..." : text;
    }

    // Switch view
    document.getElementById("welcome-view").classList.add("hidden");
    const container = document.getElementById("messages-container");
    container.classList.remove("hidden");

    // 1. Render User Bubble
    let imageUrl = "";
    if (currentAttachment && currentAttachment.type.startsWith("image/")) {
        imageUrl = URL.createObjectURL(currentAttachment);
    }
    appendUserBubble(text, imageUrl, true);

    // Save user message to session
    session.messages.push({
        role: "user",
        content: text,
        imageUrl: imageUrl
    });
    saveSessionsToStorage();

    // Reset input
    input.value = "";
    autoResize(input);
    clearAttachment();

    // 2. Render Loading State (Confined Box Style)
    const loadingId = "loader-" + Date.now();
    const loadingDiv = document.createElement("div");
    loadingDiv.id = loadingId;
    loadingDiv.className = "w-full";
    loadingDiv.innerHTML = `
        <div class="assistant-card w-full bg-[#262626] border border-[#383838] rounded-2xl p-5 md:p-6 shadow-sm space-y-4">
            <div class="flex items-center justify-between pb-3 border-b border-[#333333]">
                <div class="flex items-center gap-2.5">
                    <div class="w-6 h-6 rounded-lg bg-[#303030] border border-[#444444] flex items-center justify-center text-amber-400 shadow-sm flex-shrink-0">
                        <i data-lucide="sparkles" class="w-3.5 h-3.5 animate-spin"></i>
                    </div>
                    <span class="text-xs font-semibold text-neutral-200 tracking-tight">Excel AI</span>
                </div>
                <span class="text-[11px] text-neutral-400">Thinking...</span>
            </div>
            <div class="flex items-center gap-2 text-xs text-neutral-400 py-1">
                <span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
                <span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse" style="animation-delay: 0.2s"></span>
                <span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse" style="animation-delay: 0.4s"></span>
                <span class="ml-1.5 text-neutral-300 font-medium">Formulating clear response...</span>
            </div>
        </div>
    `;
    container.appendChild(loadingDiv);
    scrollChatToBottom();
    lucide.createIcons();

    // 3. Make API Call
    const formData = new FormData();
    if (text) formData.append("message", text);
    if (currentAttachment) formData.append("file", currentAttachment);

    const course = localStorage.getItem("excel_user_course") || "CA";
    const level = localStorage.getItem("excel_user_level") || "Inter";
    formData.append("course", course);
    formData.append("level", level);

    const historyList = (session.messages || []).slice(-6).map(m => ({
        role: m.role || "user",
        text: m.content || m.text || ""
    }));
    formData.append("history", JSON.stringify(historyList));

    const activeSessionId = session.id || currentSessionId || "";
    if (activeSessionId) formData.append("session_id", activeSessionId);

    try {
        const resp = await fetch("/api/chat", {
            method: "POST",
            body: formData
        });
        let data = {};
        try {
            data = await resp.json();
        } catch (jsonErr) {
            console.warn("Non-JSON server response:", jsonErr);
        }

        // Remove loading state
        const loader = document.getElementById(loadingId);
        if (loader) loader.remove();

        let replyMarkdown = data.reply || data.detail;
        if (!replyMarkdown) {
            if (resp.status === 503) {
                replyMarkdown = "The AI is busy summarizing the lecture or analyzing materials. Please try again in a moment.";
            } else if (resp.status >= 500) {
                replyMarkdown = "⚠️ The Excel AI server encountered a temporary delay. Please re-send your question or try again.";
            } else {
                replyMarkdown = "I could not generate an answer right now. Please try again.";
            }
        }

        // 4. Render Assistant Bubble
        appendAssistantBubble(replyMarkdown, true);

        // Save assistant message to session
        session.messages.push({
            role: "assistant",
            content: replyMarkdown
        });
        saveSessionsToStorage();

    } catch (err) {
        console.error("Chat communication error:", err);
        const loader = document.getElementById(loadingId);
        if (loader) loader.remove();
        appendAssistantBubble("⚠️ **Connection Notice:** Unable to reach the Excel AI server right now. Please check your network connection or try again in a moment.", true);
    }
}

function appendUserBubble(text, imageUrl, scroll) {
    const container = document.getElementById("messages-container");
    const userDiv = document.createElement("div");
    userDiv.className = "flex justify-end w-full";

    let imgHtml = "";
    if (imageUrl) {
        imgHtml = `
            <div class="mb-2.5">
                <img src="${imageUrl}" class="max-h-56 rounded-xl border border-neutral-700 shadow-md" alt="upload">
            </div>
        `;
    }

    userDiv.innerHTML = `
        <div class="bg-[#2f2f2f] text-neutral-100 rounded-2xl px-5 py-3.5 max-w-xl text-[14.5px] leading-relaxed shadow-sm border border-[#3d3d3d]">
            ${imgHtml}
            ${text ? `<p class="whitespace-pre-wrap">${escapeHtml(text)}</p>` : ''}
        </div>
    `;
    container.appendChild(userDiv);
    if (scroll) scrollChatToBottom();
}

// ----------------- FORMULA & EXAM TEXT CLEANER -----------------

function cleanExamMarkdown(text) {
    if (!text) return "";
    let cleaned = text;

    // 1. Remove internal self-correction monologue
    cleaned = cleaned.replace(/\s*\([Ww]ait,\s*let'?s\s*recalculate[^)]*\)/gi, "");
    cleaned = cleaned.replace(/\s*\([Ww]ait,\s*let'?s\s*check[^)]*\)/gi, "");
    cleaned = cleaned.replace(/Correction in options:[^\n.]*(\.|$)/gi, "");

    // 2. Replace LaTeX math symbols with clean readable commerce characters
    cleaned = cleaned.replace(/\\times\b/g, "×");
    cleaned = cleaned.replace(/\\cdot\b/g, "·");
    cleaned = cleaned.replace(/\\div\b/g, "÷");
    cleaned = cleaned.replace(/\\pm\b/g, "±");
    cleaned = cleaned.replace(/\\(leq|le)\b/g, "≤");
    cleaned = cleaned.replace(/\\(geq|ge)\b/g, "≥");
    cleaned = cleaned.replace(/\\(neq|ne)\b/g, "≠");
    cleaned = cleaned.replace(/\\approx\b/g, "≈");

    // 3. Clean \text{...} wrappers (e.g. \text{₹} -> ₹, \text{LRV} -> LRV, \text{ hours} -> hours)
    for (let i = 0; i < 3; i++) {
        cleaned = cleaned.replace(/\\text\{([^{}]*)\}/g, "$1");
    }

    // 4. Clean \frac{a}{b} -> (a / b)
    cleaned = cleaned.replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, "($1 / $2)");

    // 5. Clean LaTeX spacing and delimiters
    cleaned = cleaned.replace(/\\(quad|qquad|,|;|!)/g, " ");
    cleaned = cleaned.replace(/\\left\s*([(\[{|])/g, "$1");
    cleaned = cleaned.replace(/\\right\s*([)\]}|])/g, "$1");

    // 6. Clean escaped brackets \[ \] \( \)
    cleaned = cleaned.replace(/\\\[/g, "[").replace(/\\\]/g, "]").replace(/\\\(/g, "(").replace(/\\\)/g, ")");

    // 7. Strip $$ and $ wrappers around plain words and numbers
    cleaned = cleaned.replace(/\$\$([\s\S]*?)\$\$/g, (match, p1) => {
        return "\n\n" + p1.trim() + "\n\n";
    });
    cleaned = cleaned.replace(/\$([^\$\n]+)\$/g, (match, p1) => {
        return p1.trim();
    });
    cleaned = cleaned.replace(/\$/g, "");

    // 8. Clean up double spaces
    cleaned = cleaned.replace(/[ \t]{2,}/g, " ");

    return cleaned.trim();
}

function appendAssistantBubble(markdownText, scroll) {
    const container = document.getElementById("messages-container");
    const aiDiv = document.createElement("div");
    aiDiv.className = "w-full";

    // Clean broken LaTeX and format nicely
    const cleanedText = cleanExamMarkdown(markdownText);
    let renderedHtml = marked.parse(cleanedText);

    // Responsive container for financial & calculation tables
    renderedHtml = renderedHtml
        .replace(/<table>/g, '<div class="table-container overflow-x-auto my-3 rounded-xl border border-[#383838]"><table class="w-full text-left">')
        .replace(/<\/table>/g, '</table></div>');

    aiDiv.innerHTML = `
        <div class="assistant-card w-full bg-[#262626] border border-[#383838] hover:border-[#484848] rounded-2xl p-5 md:p-6 shadow-sm space-y-4 transition-colors duration-200">
            <!-- Box Header -->
            <div class="flex items-center justify-between pb-3 border-b border-[#333333]">
                <div class="flex items-center gap-2.5">
                    <div class="w-6 h-6 rounded-lg bg-[#303030] border border-[#444444] flex items-center justify-center text-amber-400 shadow-sm flex-shrink-0">
                        <i data-lucide="sparkles" class="w-3.5 h-3.5"></i>
                    </div>
                    <span class="text-xs font-semibold text-neutral-200 tracking-tight">Excel AI</span>
                </div>
                <div class="flex items-center gap-1">
                    <button onclick="readAloud(this)" data-text="${escapeQuotes(cleanedText)}" title="Read Aloud" class="p-1.5 rounded-lg text-neutral-400 hover:text-white hover:bg-[#323232] transition">
                        <i data-lucide="volume-2" class="w-3.5 h-3.5"></i>
                    </button>
                    <button onclick="copyToClipboard(this)" data-content="${escapeQuotes(cleanedText)}" title="Copy Answer" class="px-2.5 py-1 rounded-lg text-neutral-400 hover:text-white hover:bg-[#323232] transition flex items-center gap-1.5 text-xs font-medium">
                        <i data-lucide="copy" class="w-3.5 h-3.5"></i>
                        <span>Copy</span>
                    </button>
                </div>
            </div>

            <!-- Content Area -->
            <div class="markdown-body">
                ${renderedHtml}
            </div>

            <!-- Box Bottom Actions -->
            <div class="flex items-center justify-between pt-3 border-t border-[#333333] text-xs text-neutral-400">
                <span class="text-[11px] text-neutral-400">Excel AI Response</span>
                <button onclick="copyToClipboard(this)" data-content="${escapeQuotes(cleanedText)}" class="hover:text-white transition flex items-center gap-1.5 text-[11px] font-medium text-neutral-400 hover:text-neutral-200">
                    <i data-lucide="copy" class="w-3 h-3"></i>
                    <span>Copy response</span>
                </button>
            </div>
        </div>
    `;
    container.appendChild(aiDiv);

    // Apply KaTeX auto-render if available
    if (window.renderMathInElement) {
        try {
            renderMathInElement(aiDiv, {
                delimiters: [
                    {left: '$$', right: '$$', display: true},
                    {left: '$', right: '$', display: false}
                ],
                throwOnError: false
            });
        } catch (e) {
            console.warn("KaTeX render notice:", e);
        }
    }

    lucide.createIcons();
    if (scroll) scrollChatToBottom();
}

function scrollChatToBottom() {
    const viewport = document.getElementById("chat-viewport");
    viewport.scrollTo({ top: viewport.scrollHeight, behavior: 'smooth' });
}

// Copy to clipboard
function copyToClipboard(btn) {
    const content = btn.getAttribute("data-content");
    if (!content) return;
    navigator.clipboard.writeText(content).then(() => {
        const span = btn.querySelector("span");
        const originalText = span.innerText;
        span.innerText = "Copied!";
        setTimeout(() => { span.innerText = originalText; }, 1500);
    });
}

// Text-to-Speech
function readAloud(btn) {
    const text = btn.getAttribute("data-text");
    if (!text || !('speechSynthesis' in window)) return;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text.substring(0, 700));
    utterance.rate = 1.0;
    utterance.lang = "en-IN";
    window.speechSynthesis.speak(utterance);
}

// Helpers
function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

function escapeQuotes(str) {
    if (!str) return "";
    return str.replace(/"/g, '&quot;').replace(/'/g, "\\'");
}

// ----------------- INTERACTIVE MCQ ENGINE -----------------

const MCQ_SYLLABUS_MAP = {
    "CA": {
        "Foundation": [
            "Accounting",
            "Business Laws",
            "Quantitative Aptitude",
            "Business Economics",
            "Business and Commercial Knowledge"
        ],
        "Inter": [
            "Advanced Accounting",
            "Corporate and Other Laws",
            "Taxation",
            "Cost and Management Accounting",
            "Auditing and Ethics",
            "Financial Management and Strategic Management"
        ],
        "Final": [
            "Financial Reporting",
            "Advanced Financial Management",
            "Advanced Auditing and Professional Ethics",
            "Direct Tax Laws and International Taxation",
            "Indirect Tax Laws",
            "Integrated Business Solutions"
        ]
    },
    "CS": {
        "Executive": [
            "Jurisprudence, Interpretation and General Laws",
            "Company Law and Practice",
            "Setting up of Business, Industrial and Labour Laws",
            "Corporate Accounting and Financial Management",
            "Capital Market and Securities Laws",
            "Economic, Commercial and Intellectual Property Laws",
            "Tax Laws and Practice"
        ],
        "Professional": [
            "Environmental, Social and Governance (ESG) - Principles & Practice",
            "Drafting, Pleadings and Appearances",
            "Compliance Management, Audit & Due Diligence",
            "Strategic Management & Corporate Finance",
            "Corporate Restructuring, Valuation and Insolvency"
        ]
    },
    "CMA": {
        "Foundation": [
            "Fundamentals of Business Laws and Business Communication",
            "Fundamentals of Financial and Cost Accounting",
            "Fundamentals of Business Mathematics and Statistics",
            "Fundamentals of Business Economics and Management"
        ],
        "Inter": [
            "Financial Accounting",
            "Corporate Laws and Practice",
            "Direct and Indirect Taxation",
            "Cost Accounting",
            "Operations Management and Strategic Management",
            "Corporate Accounting and Auditing",
            "Financial Management and Business Data Analytics",
            "Management Accounting"
        ],
        "Final": [
            "Corporate and Economic Laws",
            "Strategic Financial Management",
            "Strategic Cost Management",
            "Direct Tax Laws and International Taxation",
            "Corporate Financial Reporting",
            "Indirect Tax Laws and Practice",
            "Cost and Management Audit",
            "Strategic Performance Management and Business Valuation"
        ]
    }
};

let mcqActiveQuiz = null;
let mcqCurrentIndex = 0;
let mcqUserAnswers = {}; // { index: "A" | "B" | "C" | "D" }
let mcqSubmittedQuestions = {}; // { index: true }
let mcqSelectedMode = 'random'; // 'random' or 'topic'
let mcqSelectedCount = 10;
let quizTimerInterval = null;
let quizSecondsElapsed = 0;
let mcqResultsFilter = 'all'; // 'all' or 'mistakes'

function populateMcqSubjects() {
    const course = localStorage.getItem("excel_user_course") || "CA";
    const level = localStorage.getItem("excel_user_level") || "Inter";

    const badge = document.getElementById("mcq-student-track-badge");
    if (badge) badge.innerText = `${course} ${level}`;

    const dropdown = document.getElementById("mcq-subject-dropdown");
    if (!dropdown) return;

    dropdown.innerHTML = `<option value="All">All Subjects (Mixed Practice)</option>`;
    const subjects = (MCQ_SYLLABUS_MAP[course] && MCQ_SYLLABUS_MAP[course][level]) || [];
    subjects.forEach(subj => {
        const opt = document.createElement("option");
        opt.value = subj;
        opt.innerText = subj;
        dropdown.appendChild(opt);
    });
}

function openMcqModal(defaultTopic = null) {
    const modal = document.getElementById("mcq-modal");
    if (!modal) return;

    modal.classList.remove("hidden");
    modal.classList.remove("flex");
    modal.style.display = "block";
    document.body.classList.add("overflow-hidden");

    populateMcqSubjects();
    resetMcqToSetup();

    if (defaultTopic) {
        selectMcqMode('topic');
        const customInput = document.getElementById("mcq-custom-topic");
        if (customInput) customInput.value = defaultTopic;
    }

    lucide.createIcons();
}

function closeMcqModal() {
    const modal = document.getElementById("mcq-modal");
    if (modal) {
        modal.classList.add("hidden");
        modal.classList.remove("flex");
        modal.style.display = "none";
    }
    document.body.classList.remove("overflow-hidden");
    clearInterval(quizTimerInterval);
}

function handleModalBackdropClick(event) {
    if (event.target.id === "mcq-modal" || event.target.classList.contains("min-h-full")) {
        closeMcqModal();
    }
}

function selectMcqMode(mode) {
    mcqSelectedMode = mode;
    const btnRandom = document.getElementById("mcq-mode-random");
    const btnTopic = document.getElementById("mcq-mode-topic");
    const topicSelector = document.getElementById("mcq-topic-selector");

    if (mode === 'random') {
        if (btnRandom) btnRandom.className = "p-4 rounded-2xl border-2 border-amber-500 bg-amber-500/10 cursor-pointer transition flex items-start gap-3";
        if (btnTopic) btnTopic.className = "p-4 rounded-2xl border border-[#383838] bg-[#242424] hover:bg-[#282828] cursor-pointer transition flex items-start gap-3";
        if (topicSelector) topicSelector.classList.add("hidden");
    } else {
        if (btnTopic) btnTopic.className = "p-4 rounded-2xl border-2 border-amber-500 bg-amber-500/10 cursor-pointer transition flex items-start gap-3";
        if (btnRandom) btnRandom.className = "p-4 rounded-2xl border border-[#383838] bg-[#242424] hover:bg-[#282828] cursor-pointer transition flex items-start gap-3";
        if (topicSelector) topicSelector.classList.remove("hidden");
    }
}

function setMcqCount(count) {
    mcqSelectedCount = count;
    [5, 10, 15].forEach(c => {
        const btn = document.getElementById(`count-btn-${c}`);
        if (!btn) return;
        if (c === count) {
            btn.className = "py-2.5 rounded-xl text-xs font-bold border-2 border-amber-500 bg-amber-500/10 text-white transition text-center shadow-sm cursor-pointer";
        } else {
            btn.className = "py-2.5 rounded-xl text-xs font-bold border border-[#3a3a3a] bg-[#242424] text-neutral-400 hover:text-white transition text-center cursor-pointer";
        }
    });
}

function resetMcqToSetup() {
    document.getElementById("mcq-setup-view").classList.remove("hidden");
    document.getElementById("mcq-quiz-view").classList.add("hidden");
    document.getElementById("mcq-results-view").classList.add("hidden");
    document.getElementById("mcq-topic-badge").classList.add("hidden");

    clearInterval(quizTimerInterval);
    mcqActiveQuiz = null;
    mcqCurrentIndex = 0;
    mcqUserAnswers = {};
    mcqSubmittedQuestions = {};
    setMcqCount(10);
    selectMcqMode('random');

    const startBtn = document.getElementById("start-quiz-btn");
    if (startBtn) {
        startBtn.disabled = false;
        startBtn.innerHTML = `
            <i data-lucide="play" class="w-4 h-4 fill-slate-950"></i>
            <span>Start Interactive Practice Test</span>
        `;
    }
    lucide.createIcons();
}

async function startInteractiveQuiz() {
    let subject = null;
    let topic = "Random";

    if (mcqSelectedMode === 'topic') {
        const subjElem = document.getElementById("mcq-subject-dropdown");
        if (subjElem && subjElem.value !== "All") {
            subject = subjElem.value;
        }
        const customVal = (document.getElementById("mcq-custom-topic")?.value || "").trim();
        if (customVal) {
            topic = customVal;
        } else if (subject) {
            topic = subject;
        }
    }

    const startBtn = document.getElementById("start-quiz-btn");
    if (startBtn) {
        startBtn.disabled = true;
        startBtn.innerHTML = `
            <span class="w-4 h-4 border-2 border-slate-950 border-t-transparent rounded-full animate-spin"></span>
            <span>Generating Exam Questions...</span>
        `;
    }

    try {
        const studentCourse = localStorage.getItem("excel_user_course") || "CA";
        const studentLevel = localStorage.getItem("excel_user_level") || "Inter";

        const resp = await fetch("/api/mcq/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                course: studentCourse,
                level: studentLevel,
                subject: subject,
                topic: topic,
                count: mcqSelectedCount
            })
        });

        if (!resp.ok) {
            const errData = await resp.json().catch(() => ({}));
            throw new Error(errData.detail || "Failed to generate MCQs");
        }
        const data = await resp.json();

        if (!data.questions || data.questions.length === 0) {
            throw new Error("No questions returned from quiz generator");
        }

        mcqActiveQuiz = data;
        mcqCurrentIndex = 0;
        mcqUserAnswers = {};
        mcqSubmittedQuestions = {};

        // Stopwatch Timer
        clearInterval(quizTimerInterval);
        quizSecondsElapsed = 0;
        const timerElem = document.getElementById("quiz-timer-text");
        if (timerElem) timerElem.innerText = "00:00";
        quizTimerInterval = setInterval(() => {
            quizSecondsElapsed++;
            const mins = String(Math.floor(quizSecondsElapsed / 60)).padStart(2, '0');
            const secs = String(quizSecondsElapsed % 60).padStart(2, '0');
            const el = document.getElementById("quiz-timer-text");
            if (el) el.innerText = `${mins}:${secs}`;
        }, 1000);

        // Header topic badge
        const badge = document.getElementById("mcq-topic-badge");
        const displayLabel = topic === "Random" ? "Mixed Syllabus" : (topic.length > 25 ? topic.substring(0, 25) + "..." : topic);
        badge.innerText = displayLabel;
        badge.classList.remove("hidden");

        // Switch to Quiz View
        document.getElementById("mcq-setup-view").classList.add("hidden");
        document.getElementById("mcq-quiz-view").classList.remove("hidden");

        renderQuizQuestion(0);

    } catch (err) {
        console.error(err);
        alert(err.message || "Could not load interactive quiz. Please check server connection.");
        resetMcqToSetup();
    }
}

function jumpToMcqQuestion(index) {
    if (!mcqActiveQuiz || !mcqActiveQuiz.questions[index]) return;
    mcqCurrentIndex = index;
    renderQuizQuestion(index);
}

function renderQuizQuestion(index) {
    if (!mcqActiveQuiz || !mcqActiveQuiz.questions[index]) return;

    const q = mcqActiveQuiz.questions[index];
    const total = mcqActiveQuiz.questions.length;
    const correctKey = (q.correct_answer || q.correct_option || "").toUpperCase().trim();
    const isSubmitted = Boolean(mcqSubmittedQuestions[index]);
    const userChoice = mcqUserAnswers[index];

    // 1. Progress and Answered Counters
    document.getElementById("quiz-question-counter").innerText = `Question ${index + 1} of ${total}`;
    const answeredCount = Object.keys(mcqSubmittedQuestions).length;
    document.getElementById("quiz-answered-counter").innerText = `${answeredCount} of ${total} completed`;

    const progressPct = ((index + 1) / total) * 100;
    document.getElementById("quiz-progress-bar").style.width = `${progressPct}%`;

    // 2. Interactive Palette (1..total)
    const paletteContainer = document.getElementById("quiz-palette");
    if (paletteContainer) {
        paletteContainer.innerHTML = mcqActiveQuiz.questions.map((item, i) => {
            const isCurrent = i === index;
            const submitted = Boolean(mcqSubmittedQuestions[i]);
            const picked = mcqUserAnswers[i];
            const itemCorrect = (item.correct_answer || item.correct_option || "").toUpperCase().trim();

            let pillClass = "w-7 h-7 sm:w-8 sm:h-8 rounded-xl text-xs font-bold transition flex items-center justify-center cursor-pointer ";
            if (isCurrent) {
                pillClass += "ring-2 ring-amber-400 bg-amber-500 text-slate-950 font-black shadow-md";
            } else if (submitted) {
                if (picked === itemCorrect) {
                    pillClass += "bg-emerald-500/20 text-emerald-300 border border-emerald-500/60";
                } else {
                    pillClass += "bg-red-500/20 text-red-300 border border-red-500/60";
                }
            } else if (picked) {
                pillClass += "bg-amber-500/20 text-amber-300 border border-amber-500/40";
            } else {
                pillClass += "bg-[#292929] text-neutral-400 border border-[#3e3e3e] hover:bg-[#333] hover:text-white";
            }
            return `<button onclick="jumpToMcqQuestion(${i})" class="${pillClass}" title="Jump to Question ${i+1}">${i+1}</button>`;
        }).join("");
    }

    // 3. Question Text
    const cleanedQText = cleanExamMarkdown(q.question);
    const qElem = document.getElementById("quiz-question-text");
    qElem.innerHTML = marked.parse(cleanedQText);

    // 4. Render 4 Options
    const optionsContainer = document.getElementById("quiz-options-container");
    const optionKeys = ["A", "B", "C", "D"];

    optionsContainer.innerHTML = optionKeys.map(key => {
        const optionVal = cleanExamMarkdown(q.options[key] || "");
        const isSelected = userChoice === key;

        let borderClass = "";
        let badgeClass = "";
        let iconHtml = "";

        if (!isSubmitted) {
            // Unsubmitted: interactive selection, answers completely hidden!
            if (isSelected) {
                borderClass = "border-amber-400 bg-amber-500/15 shadow-md text-white";
                badgeClass = "bg-amber-400 text-slate-950 font-black";
                iconHtml = '<i data-lucide="check-circle" class="w-5 h-5 text-amber-400"></i>';
            } else {
                borderClass = "border-[#383838] bg-[#292929] hover:bg-[#303030] hover:border-[#484848] text-neutral-200";
                badgeClass = "bg-[#383838] text-neutral-300 font-bold";
                iconHtml = '<div class="w-4 h-4 rounded-full border border-neutral-600"></div>';
            }
        } else {
            // Submitted: Reveal correct/incorrect highlights
            if (key === correctKey) {
                borderClass = "border-emerald-500 bg-emerald-950/40 text-emerald-100 shadow-md font-semibold";
                badgeClass = "bg-emerald-500 text-slate-950 font-black";
                iconHtml = '<span class="text-xs font-bold text-emerald-400 flex items-center gap-1">✓ Correct</span>';
            } else if (isSelected && key !== correctKey) {
                borderClass = "border-red-500 bg-red-950/40 text-red-200 line-through opacity-85";
                badgeClass = "bg-red-500 text-white font-bold";
                iconHtml = '<span class="text-xs font-bold text-red-400 flex items-center gap-1">✗ Your Pick</span>';
            } else {
                borderClass = "border-[#303030] bg-[#222] opacity-60 text-neutral-400";
                badgeClass = "bg-[#303030] text-neutral-500 font-medium";
                iconHtml = "";
            }
        }

        const clickHandler = !isSubmitted ? `onclick="selectMcqOption('${key}')"` : "";
        const cursorStyle = !isSubmitted ? "cursor-pointer" : "cursor-default";

        return `
            <div ${clickHandler} class="p-3.5 sm:p-4 rounded-2xl border-2 ${borderClass} ${cursorStyle} transition flex items-center gap-3">
                <div class="w-7 h-7 rounded-xl ${badgeClass} text-xs flex items-center justify-center flex-shrink-0 shadow-sm">
                    ${key}
                </div>
                <div class="flex-1 min-w-0 text-xs sm:text-sm font-medium leading-relaxed break-words">
                    ${escapeHtml(optionVal)}
                </div>
                <div class="flex items-center justify-center flex-shrink-0">
                    ${iconHtml}
                </div>
            </div>
        `;
    }).join("");

    // 5. Instant Feedback & Reasoning Box
    const feedbackBox = document.getElementById("quiz-instant-feedback");
    const checkBtn = document.getElementById("quiz-check-btn");
    const nextBtn = document.getElementById("quiz-next-btn");

    if (isSubmitted) {
        feedbackBox.classList.remove("hidden");
        const statusBadgeContainer = document.getElementById("feedback-status-badge");
        const isCorrect = userChoice === correctKey;

        if (isCorrect) {
            statusBadgeContainer.innerHTML = `
                <div class="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-xs font-bold">
                    <i data-lucide="check-circle-2" class="w-4 h-4 text-emerald-400"></i>
                    <span>Correct Answer! (+1 Mark)</span>
                </div>
            `;
        } else {
            statusBadgeContainer.innerHTML = `
                <div class="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-red-500/20 border border-red-500/40 text-red-300 text-xs font-bold">
                    <i data-lucide="x-circle" class="w-4 h-4 text-red-400"></i>
                    <span>Incorrect • Your Pick: Option ${userChoice || 'None'} • Correct: Option ${correctKey}</span>
                </div>
            `;
        }

        const explanationElem = document.getElementById("feedback-explanation-text");
        explanationElem.innerText = cleanExamMarkdown(q.explanation || "Review the statutory section and calculation.");

        if (checkBtn) checkBtn.classList.add("hidden");
        if (nextBtn) {
            nextBtn.className = "px-6 py-2 rounded-xl text-xs font-bold bg-amber-500 hover:bg-amber-400 text-slate-950 shadow-md transition flex items-center gap-1.5 cursor-pointer";
            if (index === total - 1) {
                nextBtn.innerHTML = `<span>Finish & View Score</span><i data-lucide="award" class="w-4 h-4"></i>`;
            } else {
                nextBtn.innerHTML = `<span>Next Question</span><i data-lucide="chevron-right" class="w-4 h-4"></i>`;
            }
        }

    } else {
        feedbackBox.classList.add("hidden");
        if (checkBtn) {
            checkBtn.classList.remove("hidden");
            checkBtn.disabled = !userChoice;
        }
        if (nextBtn) {
            nextBtn.className = "px-4 py-2 rounded-xl text-xs font-semibold bg-[#2a2a2a] hover:bg-[#333] border border-[#383838] text-neutral-300 transition flex items-center gap-1.5 cursor-pointer";
            if (index === total - 1) {
                nextBtn.innerHTML = `<span>Skip to Finish</span><i data-lucide="check" class="w-4 h-4"></i>`;
            } else {
                nextBtn.innerHTML = `<span>Skip Next</span><i data-lucide="chevron-right" class="w-4 h-4"></i>`;
            }
        }
    }

    const prevBtn = document.getElementById("quiz-prev-btn");
    if (prevBtn) prevBtn.disabled = index === 0;

    if (window.renderMathInElement) {
        try {
            renderMathInElement(document.getElementById("mcq-quiz-view"), {
                delimiters: [
                    {left: '$$', right: '$$', display: true},
                    {left: '$', right: '$', display: false}
                ],
                throwOnError: false
            });
        } catch (e) {
            console.warn("KaTeX render notice:", e);
        }
    }

    lucide.createIcons();
}

function selectMcqOption(key) {
    if (!mcqActiveQuiz || mcqSubmittedQuestions[mcqCurrentIndex]) return;
    mcqUserAnswers[mcqCurrentIndex] = key;
    renderQuizQuestion(mcqCurrentIndex);
}

function submitCurrentQuestion() {
    if (!mcqActiveQuiz) return;
    if (!mcqUserAnswers[mcqCurrentIndex]) {
        alert("Please select an option before checking your answer.");
        return;
    }
    mcqSubmittedQuestions[mcqCurrentIndex] = true;
    renderQuizQuestion(mcqCurrentIndex);
}

function prevMcqQuestion() {
    if (mcqCurrentIndex > 0) {
        mcqCurrentIndex--;
        renderQuizQuestion(mcqCurrentIndex);
    }
}

function nextMcqQuestion() {
    if (!mcqActiveQuiz) return;
    const total = mcqActiveQuiz.questions.length;
    if (mcqCurrentIndex < total - 1) {
        mcqCurrentIndex++;
        renderQuizQuestion(mcqCurrentIndex);
    } else {
        submitQuiz();
    }
}

// Keyboard shortcuts for fun & fast quiz taking & Escape to close
document.addEventListener("keydown", (e) => {
    const modal = document.getElementById("mcq-modal");
    if (e.key === "Escape") {
        if (modal && modal.style.display !== "none" && !modal.classList.contains("hidden")) {
            closeMcqModal();
            return;
        }
    }

    const quizView = document.getElementById("mcq-quiz-view");
    if (!quizView || quizView.classList.contains("hidden")) return;
    if (document.activeElement && (document.activeElement.tagName === "INPUT" || document.activeElement.tagName === "TEXTAREA")) return;

    if (e.key === "1" || e.key.toUpperCase() === "A") selectMcqOption("A");
    else if (e.key === "2" || e.key.toUpperCase() === "B") selectMcqOption("B");
    else if (e.key === "3" || e.key.toUpperCase() === "C") selectMcqOption("C");
    else if (e.key === "4" || e.key.toUpperCase() === "D") selectMcqOption("D");
    else if (e.key === "Enter") {
        if (!mcqSubmittedQuestions[mcqCurrentIndex] && mcqUserAnswers[mcqCurrentIndex]) {
            submitCurrentQuestion();
        } else {
            nextMcqQuestion();
        }
    }
    else if (e.key === "ArrowRight") nextMcqQuestion();
    else if (e.key === "ArrowLeft") prevMcqQuestion();
});

function submitQuiz() {
    if (!mcqActiveQuiz) return;
    const total = mcqActiveQuiz.questions.length;
    const answeredCount = Object.keys(mcqSubmittedQuestions).length;

    if (answeredCount < total) {
        const confirmSubmit = confirm(`You have completed ${answeredCount} of ${total} questions. Do you want to finalize and view your score now?`);
        if (!confirmSubmit) return;
    }

    clearInterval(quizTimerInterval);
    const mins = Math.floor(quizSecondsElapsed / 60);
    const secs = quizSecondsElapsed % 60;
    const timeFormatted = `${mins > 0 ? mins + 'm ' : ''}${secs}s`;

    let correctCount = 0;
    let mistakesCount = 0;

    mcqActiveQuiz.questions.forEach((q, idx) => {
        const correctKey = (q.correct_answer || q.correct_option || "").toUpperCase().trim();
        if (mcqUserAnswers[idx] === correctKey) {
            correctCount++;
        } else {
            mistakesCount++;
        }
    });

    const scorePct = Math.round((correctCount / total) * 100);

    // Switch to Results View
    document.getElementById("mcq-quiz-view").classList.add("hidden");
    document.getElementById("mcq-results-view").classList.remove("hidden");

    // Score & timing
    document.getElementById("results-score-text").innerText = `${correctCount} / ${total} (${scorePct}%)`;

    let feedback = "";
    if (scorePct >= 80) {
        feedback = `🌟 Ranker Standard! Exceptional conceptual mastery and precision (Completed in ${timeFormatted}).`;
    } else if (scorePct >= 60) {
        feedback = `🎉 Official Exam Pass Standard! Strong command with minor revisions needed (Completed in ${timeFormatted}).`;
    } else if (scorePct >= 40) {
        feedback = `👍 Good Attempt! Review the step-by-step working notes below to boost your score (Completed in ${timeFormatted}).`;
    } else {
        feedback = `📚 Focus Needed! Thoroughly study the reasoning boxes below to master these concepts (Completed in ${timeFormatted}).`;
    }
    document.getElementById("results-feedback-text").innerText = feedback;

    // Filter counts
    const totalCountElem = document.getElementById("results-total-count");
    if (totalCountElem) totalCountElem.innerText = String(total);
    const mistakesCountElem = document.getElementById("results-mistakes-count");
    if (mistakesCountElem) mistakesCountElem.innerText = String(mistakesCount);

    mcqResultsFilter = 'all';
    renderResultsBreakdown();
}

function filterResults(filterType) {
    mcqResultsFilter = filterType;
    const allBtn = document.getElementById("filter-all-btn");
    const mistakesBtn = document.getElementById("filter-mistakes-btn");

    if (filterType === 'all') {
        if (allBtn) allBtn.className = "px-3 py-1.5 rounded-xl text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 transition cursor-pointer";
        if (mistakesBtn) mistakesBtn.className = "px-3 py-1.5 rounded-xl text-xs font-bold bg-[#303030] text-neutral-300 hover:text-white border border-[#404040] transition cursor-pointer";
    } else {
        if (mistakesBtn) mistakesBtn.className = "px-3 py-1.5 rounded-xl text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 transition cursor-pointer";
        if (allBtn) allBtn.className = "px-3 py-1.5 rounded-xl text-xs font-bold bg-[#303030] text-neutral-300 hover:text-white border border-[#404040] transition cursor-pointer";
    }
    renderResultsBreakdown();
}

function renderResultsBreakdown() {
    if (!mcqActiveQuiz) return;
    const container = document.getElementById("results-breakdown-list");
    if (!container) return;

    const filteredQuestions = mcqActiveQuiz.questions.map((q, idx) => ({ q, idx })).filter(({ q, idx }) => {
        if (mcqResultsFilter === 'all') return true;
        const correctKey = (q.correct_answer || q.correct_option || "").toUpperCase().trim();
        return mcqUserAnswers[idx] !== correctKey;
    });

    if (filteredQuestions.length === 0) {
        container.innerHTML = `
            <div class="p-8 text-center bg-[#242424] border border-[#383838] rounded-2xl space-y-2">
                <div class="text-3xl">🎉</div>
                <h4 class="text-sm font-bold text-white">No Mistakes Found!</h4>
                <p class="text-xs text-neutral-400">You answered all questions correctly in this practice session.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = filteredQuestions.map(({ q, idx }) => {
        const correctKey = (q.correct_answer || q.correct_option || "").toUpperCase().trim();
        const userChoice = mcqUserAnswers[idx];
        const isCorrect = userChoice === correctKey;
        const isAnswered = Boolean(userChoice);

        let statusBadge = "";
        let borderClass = "";

        if (!isAnswered) {
            statusBadge = `<span class="bg-amber-500/20 text-amber-300 border border-amber-500/30 px-2.5 py-0.5 rounded-full text-[10px] font-bold">⚠ Unattempted</span>`;
            borderClass = "border-[#383838]";
        } else if (isCorrect) {
            statusBadge = `<span class="bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-2.5 py-0.5 rounded-full text-[10px] font-bold">✓ Correct (+1 Mark)</span>`;
            borderClass = "border-emerald-500/40";
        } else {
            statusBadge = `<span class="bg-red-500/20 text-red-300 border border-red-500/30 px-2.5 py-0.5 rounded-full text-[10px] font-bold">✗ Incorrect (Selected ${userChoice})</span>`;
            borderClass = "border-red-500/40";
        }

        const optionKeys = ["A", "B", "C", "D"];
        const optionsHtml = optionKeys.map(k => {
            const optText = cleanExamMarkdown(q.options[k] || "");
            const isThisCorrect = k === correctKey;
            const isThisUserWrong = userChoice === k && !isCorrect;

            let optStyle = "bg-[#252525] border-[#353535] text-neutral-300";
            let tag = "";

            if (isThisCorrect) {
                optStyle = "bg-emerald-950/30 border-emerald-500/50 text-emerald-100 font-semibold";
                tag = `<span class="ml-auto text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded-full font-bold">✓ Correct Answer</span>`;
            } else if (isThisUserWrong) {
                optStyle = "bg-red-950/30 border-red-500/50 text-red-200 line-through opacity-80";
                tag = `<span class="ml-auto text-[10px] bg-red-500/20 text-red-300 px-2 py-0.5 rounded-full font-bold">Your Choice</span>`;
            }

            return `
                <div class="px-3.5 py-2.5 rounded-xl border text-xs sm:text-sm flex items-center gap-2.5 ${optStyle} mcq-review-item">
                    <span class="font-bold flex-shrink-0">${k})</span>
                    <span class="mcq-opt-text leading-relaxed">${escapeHtml(optText)}</span>
                    ${tag}
                </div>
            `;
        }).join("");

        const cleanedExplanation = cleanExamMarkdown(q.explanation || "");

        return `
            <div class="bg-[#212121] border ${borderClass} rounded-2xl p-4 sm:p-5 space-y-3.5 shadow-md mcq-review-item">
                <div class="flex items-center justify-between gap-2 border-b border-[#2e2e2e] pb-2.5">
                    <span class="text-xs font-bold text-white uppercase tracking-wider">Question ${idx + 1} of ${mcqActiveQuiz.questions.length}</span>
                    ${statusBadge}
                </div>

                <div class="text-sm sm:text-base font-bold text-neutral-100 leading-relaxed mcq-review-item">
                    ${escapeHtml(cleanExamMarkdown(q.question))}
                </div>

                <div class="space-y-2 pt-1">
                    ${optionsHtml}
                </div>

                <!-- Detailed Solution & Working Notes Box -->
                <div class="mt-3 p-3.5 sm:p-4 rounded-xl bg-[#142314] border border-emerald-500/40 text-emerald-100 text-xs sm:text-sm space-y-1.5 mcq-review-item shadow-inner">
                    <p class="font-bold flex items-center gap-1.5 text-emerald-300 text-xs uppercase tracking-wide">
                        <i data-lucide="lightbulb" class="w-4 h-4 text-emerald-400 flex-shrink-0"></i>
                        <span>Reasoning & Working Solution</span>
                    </p>
                    <p class="mcq-reasoning-box text-emerald-100/95 leading-relaxed">${escapeHtml(cleanedExplanation)}</p>
                </div>
            </div>
        `;
    }).join("");

    if (window.renderMathInElement) {
        try {
            renderMathInElement(container, {
                delimiters: [
                    {left: '$$', right: '$$', display: true},
                    {left: '$', right: '$', display: false}
                ],
                throwOnError: false
            });
        } catch (e) {
            console.warn("KaTeX render notice:", e);
        }
    }

    lucide.createIcons();
}
