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
function toggleSidebar(open) {
    const sidebar = document.getElementById("chat-sidebar");
    const backdrop = document.getElementById("sidebar-backdrop");

    if (open) {
        sidebar.classList.remove("-translate-x-full");
        backdrop.classList.remove("hidden");
    } else {
        sidebar.classList.add("-translate-x-full");
        backdrop.classList.add("hidden");
    }
}

// Quick Prompt Click
function usePrompt(text) {
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

function appendAssistantBubble(markdownText, scroll) {
    const container = document.getElementById("messages-container");
    const aiDiv = document.createElement("div");
    aiDiv.className = "flex gap-3 items-start";

    const renderedHtml = marked.parse(markdownText);

    aiDiv.innerHTML = `
        <div class="w-8 h-8 rounded-xl bg-gradient-to-tr from-amber-500 to-amber-300 text-slate-900 font-black text-xs flex items-center justify-center flex-shrink-0 shadow-md mt-1">
            E
        </div>
        <div class="flex-1 bg-[#282828] border border-[#383838] rounded-3xl rounded-tl-sm p-5 shadow-lg space-y-3">
            <div class="markdown-body">
                ${renderedHtml}
            </div>
            <div class="pt-2 border-t border-[#333333] flex items-center justify-between text-xs text-neutral-400">
                <span class="text-[11px] font-semibold text-amber-400/80">ICAI / ICSI Standard</span>
                <div class="flex items-center gap-2">
                    <button onclick="copyToClipboard(this)" data-content="${escapeQuotes(markdownText)}" title="Copy response" class="p-1 hover:text-white transition flex items-center gap-1 text-[11px] font-medium">
                        <i data-lucide="copy" class="w-3.5 h-3.5"></i>
                        <span>Copy</span>
                    </button>
                    <button onclick="readAloud(this)" data-text="${escapeQuotes(markdownText.replace(/[#*`_]/g, ''))}" title="Listen to response" class="p-1 hover:text-amber-400 transition flex items-center gap-1 text-[11px] font-medium">
                        <i data-lucide="volume-2" class="w-3.5 h-3.5"></i>
                        <span>Listen</span>
                    </button>
                </div>
            </div>
        </div>
    `;
    container.appendChild(aiDiv);
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
