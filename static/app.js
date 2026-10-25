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
});

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

    // 2. Render Loading State
    const loadingId = "loader-" + Date.now();
    const loadingDiv = document.createElement("div");
    loadingDiv.id = loadingId;
    loadingDiv.className = "flex gap-3 items-start max-w-2xl";
    loadingDiv.innerHTML = `
        <div class="w-8 h-8 rounded-xl bg-gradient-to-tr from-amber-500 to-amber-300 text-slate-900 font-black text-xs flex items-center justify-center flex-shrink-0 shadow-md">
            E
        </div>
        <div class="bg-[#2a2a2a] border border-[#383838] rounded-2xl rounded-tl-sm px-4 py-3 shadow-md flex items-center gap-2 text-xs font-medium text-neutral-400">
            <span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
            <span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse" style="animation-delay: 0.2s"></span>
            <span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse" style="animation-delay: 0.4s"></span>
            <span class="ml-1 text-neutral-300">Excel AI is thinking...</span>
        </div>
    `;
    container.appendChild(loadingDiv);
    scrollChatToBottom();

    // 3. Make API Call
    const formData = new FormData();
    if (text) formData.append("message", text);
    if (currentAttachment) formData.append("file", currentAttachment);

    try {
        const resp = await fetch("/api/chat", {
            method: "POST",
            body: formData
        });
        const data = await resp.json();

        // Remove loading state
        const loader = document.getElementById(loadingId);
        if (loader) loader.remove();

        const replyMarkdown = data.reply || "I could not generate an answer right now. Please try again.";

        // 4. Render Assistant Bubble
        appendAssistantBubble(replyMarkdown, true);

        // Save assistant message to session
        session.messages.push({
            role: "assistant",
            content: replyMarkdown
        });
        saveSessionsToStorage();

    } catch (err) {
        console.error(err);
        const loader = document.getElementById(loadingId);
        if (loader) loader.remove();
        alert("Failed to communicate with Excel AI server.");
    }
}

function appendUserBubble(text, imageUrl, scroll) {
    const container = document.getElementById("messages-container");
    const userDiv = document.createElement("div");
    userDiv.className = "flex justify-end";

    let imgHtml = "";
    if (imageUrl) {
        imgHtml = `
            <div class="mb-2">
                <img src="${imageUrl}" class="max-h-56 rounded-xl border border-neutral-700 shadow-md" alt="upload">
            </div>
        `;
    }

    userDiv.innerHTML = `
        <div class="bg-[#2f2f2f] text-neutral-100 rounded-3xl rounded-tr-sm px-4 py-3 max-w-xl text-sm leading-relaxed shadow-md border border-[#3d3d3d]">
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
    cleaned = cleaned.replace(/\\leq\b/g, "≤");
    cleaned = cleaned.replace(/\\geq\b/g, "≥");
    cleaned = cleaned.replace(/\\neq\b/g, "≠");
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

    // 6. Strip $$ and $ wrappers around plain words and numbers
    cleaned = cleaned.replace(/\$\$([\s\S]*?)\$\$/g, (match, p1) => {
        return "\n\n" + p1.trim() + "\n\n";
    });
    cleaned = cleaned.replace(/\$([^\$\n]+)\$/g, (match, p1) => {
        return p1.trim();
    });

    // 7. Clean up double spaces
    cleaned = cleaned.replace(/[ \t]{2,}/g, " ");

    return cleaned.trim();
}

function appendAssistantBubble(markdownText, scroll) {
    const container = document.getElementById("messages-container");
    const aiDiv = document.createElement("div");
    aiDiv.className = "flex gap-3 items-start";

    // Clean broken LaTeX and format nicely
    const cleanedText = cleanExamMarkdown(markdownText);
    const renderedHtml = marked.parse(cleanedText);

    // Check if response mentions MCQs to offer interactive test card
    const isMcqRelated = /(mcq|multiple choice|quiz|practice question)/i.test(cleanedText);
    const mcqPillHtml = isMcqRelated ? `
        <div class="pt-2 pb-1">
            <div class="p-3.5 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div class="flex items-center gap-2.5">
                    <div class="w-8 h-8 rounded-xl bg-amber-500/20 text-amber-400 flex items-center justify-center font-bold flex-shrink-0">
                        <i data-lucide="award" class="w-4 h-4"></i>
                    </div>
                    <div>
                        <p class="text-xs font-bold text-white">Interactive 10-Question Exam Mode</p>
                        <p class="text-[11px] text-neutral-400">Test yourself with hidden answers, stopwatch timer, and live scoring</p>
                    </div>
                </div>
                <button onclick="openMcqModal()" class="px-3.5 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs shadow-md transition flex items-center justify-center gap-1.5 flex-shrink-0">
                    <i data-lucide="play" class="w-3.5 h-3.5 fill-slate-950"></i>
                    <span>Start 10-MCQ Test</span>
                </button>
            </div>
        </div>
    ` : "";

    aiDiv.innerHTML = `
        <div class="w-8 h-8 rounded-xl bg-gradient-to-tr from-amber-500 to-amber-300 text-slate-900 font-black text-xs flex items-center justify-center flex-shrink-0 shadow-md mt-1">
            E
        </div>
        <div class="flex-1 bg-[#282828] border border-[#383838] rounded-3xl rounded-tl-sm p-5 shadow-lg space-y-3">
            <div class="markdown-body">
                ${renderedHtml}
            </div>
            ${mcqPillHtml}
            <div class="pt-2 border-t border-[#333333] flex items-center justify-between text-xs text-neutral-400">
                <span class="text-[11px] font-semibold text-amber-400/80">ICAI / ICSI Standard</span>
                <div class="flex items-center gap-2">
                    <button onclick="copyToClipboard(this)" data-content="${escapeQuotes(cleanedText)}" title="Copy response" class="p-1 hover:text-white transition flex items-center gap-1 text-[11px] font-medium">
                        <i data-lucide="copy" class="w-3.5 h-3.5"></i>
                        <span>Copy</span>
                    </button>
                    <button onclick="readAloud(this)" data-text="${escapeQuotes(cleanedText.replace(/[#*`_]/g, ''))}" title="Listen to response" class="p-1 hover:text-amber-400 transition flex items-center gap-1 text-[11px] font-medium">
                        <i data-lucide="volume-2" class="w-3.5 h-3.5"></i>
                        <span>Listen</span>
                    </button>
                </div>
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

let mcqActiveQuiz = null;
let mcqCurrentIndex = 0;
let mcqUserAnswers = {};
let mcqSelectedMode = 'random';
let mcqSelectedCount = 10;
let quizTimerInterval = null;
let quizSecondsElapsed = 0;

function openMcqModal(defaultTopic = null) {
    const modal = document.getElementById("mcq-modal");
    if (!modal) return;

    modal.classList.remove("hidden");
    modal.classList.remove("flex");
    modal.style.display = "block";
    document.body.classList.add("overflow-hidden");

    resetMcqToSetup();

    if (defaultTopic) {
        selectMcqMode('topic');
        const dropdown = document.getElementById("mcq-topic-dropdown");
        const customInput = document.getElementById("mcq-custom-topic");
        let matched = false;

        for (let opt of dropdown.options) {
            if (opt.value.toLowerCase().includes(defaultTopic.toLowerCase()) || 
                opt.text.toLowerCase().includes(defaultTopic.toLowerCase())) {
                dropdown.value = opt.value;
                matched = true;
                break;
            }
        }
        if (!matched) {
            dropdown.value = "Custom";
            customInput.value = defaultTopic;
            customInput.classList.remove("hidden");
        }
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
        btnRandom.className = "p-4 rounded-2xl border-2 border-amber-500 bg-amber-500/10 cursor-pointer transition flex items-start gap-3";
        btnTopic.className = "p-4 rounded-2xl border border-[#383838] bg-[#242424] hover:bg-[#282828] cursor-pointer transition flex items-start gap-3";
        topicSelector.classList.add("hidden");
    } else {
        btnTopic.className = "p-4 rounded-2xl border-2 border-amber-500 bg-amber-500/10 cursor-pointer transition flex items-start gap-3";
        btnRandom.className = "p-4 rounded-2xl border border-[#383838] bg-[#242424] hover:bg-[#282828] cursor-pointer transition flex items-start gap-3";
        topicSelector.classList.remove("hidden");
    }
}

function handleMcqDropdownChange(selectElem) {
    const customInput = document.getElementById("mcq-custom-topic");
    if (selectElem.value === "Custom") {
        customInput.classList.remove("hidden");
        customInput.focus();
    } else {
        customInput.classList.add("hidden");
    }
}

function setMcqCount(count) {
    mcqSelectedCount = count;
    const btn5 = document.getElementById("count-btn-5");
    const btn10 = document.getElementById("count-btn-10");

    if (count === 10) {
        if (btn10) btn10.className = "flex-1 py-2.5 rounded-xl text-xs font-bold border-2 border-amber-500 bg-amber-500/10 text-white transition flex items-center justify-center gap-1.5 shadow-sm";
        if (btn5) btn5.className = "flex-1 py-2.5 rounded-xl text-xs font-bold border border-[#3a3a3a] bg-[#242424] text-neutral-400 hover:text-white transition";
    } else {
        if (btn5) btn5.className = "flex-1 py-2.5 rounded-xl text-xs font-bold border-2 border-amber-500 bg-amber-500/10 text-white transition flex items-center justify-center gap-1.5 shadow-sm";
        if (btn10) btn10.className = "flex-1 py-2.5 rounded-xl text-xs font-bold border border-[#3a3a3a] bg-[#242424] text-neutral-400 hover:text-white transition";
    }
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
    setMcqCount(10);

    const startBtn = document.getElementById("start-quiz-btn");
    startBtn.disabled = false;
    startBtn.innerHTML = `
        <i data-lucide="play" class="w-4 h-4 fill-slate-950"></i>
        <span>Start 10-Question Interactive Test</span>
    `;
    lucide.createIcons();
}

async function startInteractiveQuiz() {
    let topic = "Random";
    if (mcqSelectedMode === 'topic') {
        const dropdown = document.getElementById("mcq-topic-dropdown");
        if (dropdown.value === "Custom") {
            const customVal = document.getElementById("mcq-custom-topic").value.trim();
            if (!customVal) {
                alert("Please enter the custom topic you want to practice.");
                return;
            }
            topic = customVal;
        } else {
            topic = dropdown.value;
        }
    }

    const startBtn = document.getElementById("start-quiz-btn");
    startBtn.disabled = true;
    startBtn.innerHTML = `
        <span class="w-4 h-4 border-2 border-slate-950 border-t-transparent rounded-full animate-spin"></span>
        <span>Generating Exam Questions...</span>
    `;

    try {
        const resp = await fetch("/api/mcq/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                topic: topic,
                count: mcqSelectedCount,
                level: "CA_Inter"
            })
        });

        if (!resp.ok) throw new Error("Failed to generate MCQs");
        const data = await resp.json();

        if (!data.questions || data.questions.length === 0) {
            throw new Error("No questions returned from quiz generator");
        }

        mcqActiveQuiz = data;
        mcqCurrentIndex = 0;
        mcqUserAnswers = {};

        // Start Stopwatch Timer
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

        // Update topic badge in header
        const badge = document.getElementById("mcq-topic-badge");
        badge.innerText = topic === "Random" ? "Random Exam Test" : (topic.length > 25 ? topic.substring(0, 25) + "..." : topic);
        badge.classList.remove("hidden");

        // Switch to Quiz View
        document.getElementById("mcq-setup-view").classList.add("hidden");
        document.getElementById("mcq-quiz-view").classList.remove("hidden");

        renderQuizQuestion(0);

    } catch (err) {
        console.error(err);
        alert("Could not load interactive quiz. Please check server connection.");
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

    // 1. Progress and Answered Counters
    document.getElementById("quiz-question-counter").innerText = `Question ${index + 1} of ${total}`;
    const answeredCount = Object.keys(mcqUserAnswers).length;
    document.getElementById("quiz-answered-counter").innerText = `${answeredCount} of ${total} answered`;

    const progressPct = ((index + 1) / total) * 100;
    document.getElementById("quiz-progress-bar").style.width = `${progressPct}%`;

    // 2. Interactive Numbered Question Palette (1..total)
    const paletteContainer = document.getElementById("quiz-palette");
    if (paletteContainer) {
        paletteContainer.innerHTML = mcqActiveQuiz.questions.map((_, i) => {
            const isCurrent = i === index;
            const isAnswered = mcqUserAnswers[i] !== undefined;
            let pillClass = "w-7 h-7 sm:w-8 sm:h-8 rounded-xl text-xs font-bold transition flex items-center justify-center cursor-pointer ";
            if (isCurrent) {
                pillClass += "bg-amber-500 text-slate-950 ring-2 ring-amber-400 shadow-md";
            } else if (isAnswered) {
                pillClass += "bg-emerald-500/20 text-emerald-300 border border-emerald-500/50 hover:bg-emerald-500/30";
            } else {
                pillClass += "bg-[#292929] text-neutral-400 border border-[#3e3e3e] hover:bg-[#333] hover:text-white";
            }
            return `<button onclick="jumpToMcqQuestion(${i})" class="${pillClass}" title="Jump to Question ${i+1}">${i+1}</button>`;
        }).join("");
    }

    // 3. Question Text (Cleaned from any LaTeX syntax)
    const cleanedQText = cleanExamMarkdown(q.question);
    document.getElementById("quiz-question-text").innerHTML = marked.parse(cleanedQText);

    // 4. Render 4 Options (Answers 100% hidden while taking quiz!)
    const optionsContainer = document.getElementById("quiz-options-container");
    const selectedKey = mcqUserAnswers[index];

    const optionKeys = ["A", "B", "C", "D"];
    optionsContainer.innerHTML = optionKeys.map(key => {
        const optionVal = q.options[key] || "";
        const cleanedOpt = cleanExamMarkdown(optionVal);
        const isSelected = selectedKey === key;

        const borderClass = isSelected
            ? "border-amber-400 bg-amber-500/15 shadow-md text-white"
            : "border-[#383838] bg-[#292929] hover:bg-[#303030] hover:border-[#484848] text-neutral-200";

        const badgeClass = isSelected
            ? "bg-amber-400 text-slate-950 font-black"
            : "bg-[#383838] text-neutral-300 font-bold";

        return `
            <div onclick="selectMcqOption('${key}')" class="p-3.5 sm:p-4 rounded-2xl border-2 ${borderClass} cursor-pointer transition flex items-center gap-3">
                <div class="w-7 h-7 rounded-xl ${badgeClass} text-xs flex items-center justify-center flex-shrink-0 shadow-sm">
                    ${key}
                </div>
                <div class="flex-1 min-w-0 text-xs sm:text-sm font-medium leading-relaxed break-words">
                    ${escapeHtml(cleanedOpt)}
                </div>
                <div class="w-5 h-5 flex items-center justify-center">
                    ${isSelected ? '<i data-lucide="check-circle" class="w-5 h-5 text-amber-400"></i>' : '<div class="w-4 h-4 rounded-full border border-neutral-600"></div>'}
                </div>
            </div>
        `;
    }).join("");

    // 5. Navigation Buttons
    const prevBtn = document.getElementById("quiz-prev-btn");
    prevBtn.disabled = index === 0;

    const nextBtn = document.getElementById("quiz-next-btn");
    if (index === total - 1) {
        nextBtn.innerHTML = `<span>Submit Test</span><i data-lucide="check" class="w-4 h-4"></i>`;
    } else {
        nextBtn.innerHTML = `<span>Next</span><i data-lucide="chevron-right" class="w-4 h-4"></i>`;
    }

    lucide.createIcons();
}

function selectMcqOption(key) {
    mcqUserAnswers[mcqCurrentIndex] = key;
    renderQuizQuestion(mcqCurrentIndex);
}

function prevMcqQuestion() {
    if (mcqCurrentIndex > 0) {
        mcqCurrentIndex--;
        renderQuizQuestion(mcqCurrentIndex);
    }
}

function nextMcqQuestion() {
    const total = mcqActiveQuiz ? mcqActiveQuiz.questions.length : 0;
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
    else if (e.key === "ArrowRight") nextMcqQuestion();
    else if (e.key === "ArrowLeft") prevMcqQuestion();
});

function submitQuiz() {
    if (!mcqActiveQuiz) return;
    const total = mcqActiveQuiz.questions.length;
    const answeredCount = Object.keys(mcqUserAnswers).length;

    if (answeredCount < total) {
        const confirmSubmit = confirm(`You have answered ${answeredCount} of ${total} questions. Do you want to submit and view your score now?`);
        if (!confirmSubmit) return;
    }

    // Stop timer
    clearInterval(quizTimerInterval);
    const mins = Math.floor(quizSecondsElapsed / 60);
    const secs = quizSecondsElapsed % 60;
    const timeFormatted = `${mins > 0 ? mins + 'm ' : ''}${secs}s`;

    // Calculate score
    let correctCount = 0;
    mcqActiveQuiz.questions.forEach((q, idx) => {
        if (mcqUserAnswers[idx] === q.correct_option) {
            correctCount++;
        }
    });

    const scorePct = Math.round((correctCount / total) * 100);

    // Switch to Results View
    document.getElementById("mcq-quiz-view").classList.add("hidden");
    document.getElementById("mcq-results-view").classList.remove("hidden");

    // Score & Timing display
    document.getElementById("results-score-text").innerText = `${correctCount} / ${total} (${scorePct}%)`;

    let feedback = "";
    if (scorePct >= 80) {
        feedback = `🌟 ICAI Ranker Standard! Flawless conceptual mastery and precision (Completed in ${timeFormatted}).`;
    } else if (scorePct >= 60) {
        feedback = `🎉 Official Exam Pass Standard! Strong command with minor revisions needed (Completed in ${timeFormatted}).`;
    } else if (scorePct >= 40) {
        feedback = `👍 Good Attempt! Review the detailed step-by-step working notes below to boost your score (Completed in ${timeFormatted}).`;
    } else {
        feedback = `📚 Focus Needed! Thoroughly study the ICAI reasoning boxes below to master these concepts (Completed in ${timeFormatted}).`;
    }
    document.getElementById("results-feedback-text").innerText = feedback;

    // Detailed Breakdown List
    const breakdownContainer = document.getElementById("results-breakdown-list");
    breakdownContainer.innerHTML = mcqActiveQuiz.questions.map((q, idx) => {
        const userChoice = mcqUserAnswers[idx];
        const isCorrect = userChoice === q.correct_option;
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
            const isThisCorrect = k === q.correct_option;
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

        // Explanation text cleaned of any LaTeX/math glitches
        const cleanedExplanation = cleanExamMarkdown(q.explanation || "");

        return `
            <div class="bg-[#212121] border ${borderClass} rounded-2xl p-4 sm:p-5 space-y-3.5 shadow-md mcq-review-item">
                <div class="flex items-center justify-between gap-2 border-b border-[#2e2e2e] pb-2.5">
                    <span class="text-xs font-bold text-white uppercase tracking-wider">Question ${idx + 1} of ${total}</span>
                    ${statusBadge}
                </div>

                <div class="text-sm sm:text-base font-bold text-neutral-100 leading-relaxed mcq-review-item">
                    ${escapeHtml(cleanExamMarkdown(q.question))}
                </div>

                <div class="space-y-2 pt-1">
                    ${optionsHtml}
                </div>

                <!-- Brief ICAI-Style Reasoning Box -->
                <div class="mt-3 p-3.5 sm:p-4 rounded-xl bg-[#142314] border border-emerald-500/40 text-emerald-100 text-xs sm:text-sm space-y-1.5 mcq-review-item shadow-inner">
                    <p class="font-bold flex items-center gap-1.5 text-emerald-300 text-xs uppercase tracking-wide">
                        <i data-lucide="lightbulb" class="w-4 h-4 text-emerald-400 flex-shrink-0"></i>
                        <span>ICAI-Style Reasoning & Solution</span>
                    </p>
                    <p class="mcq-reasoning-box text-emerald-100/95">${escapeHtml(cleanedExplanation)}</p>
                </div>
            </div>
        `;
    }).join("");

    lucide.createIcons();
}
