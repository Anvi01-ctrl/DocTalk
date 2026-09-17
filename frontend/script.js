const documentUpload = document.getElementById("document-upload");
const uploadStatus = document.getElementById("upload-status");

const API_URL = "http://127.0.0.1:8000";

const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const messages = document.getElementById("messages");
const welcomeScreen = document.getElementById("welcomeScreen");
const newChatBtn = document.getElementById("newChatBtn");

let isLoading = false;


// Add a message to the chat
function addMessage(text, role) {

    welcomeScreen.style.display = "none";

    const message = document.createElement("div");
    message.className = `message ${role}`;

    if (role === "assistant") {

        const avatar = document.createElement("div");
        avatar.className = "avatar";
        avatar.textContent = "✦";

        const content = document.createElement("div");
        content.className = "message-content";

        // textContent keeps the response safe as plain text
        content.textContent = text;

        message.appendChild(avatar);
        message.appendChild(content);

    } else {

        const content = document.createElement("div");
        content.className = "message-content";
        content.textContent = text;

        message.appendChild(content);
    }

    messages.appendChild(message);

    message.scrollIntoView({
        behavior: "smooth",
        block: "end"
    });
}


// Show typing indicator
function showTyping() {

    const message = document.createElement("div");
    message.className = "message assistant";
    message.id = "typingMessage";

    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.textContent = "✦";

    const content = document.createElement("div");
    content.className = "message-content typing";
    content.textContent = "DocTalk is thinking";

    message.appendChild(avatar);
    message.appendChild(content);

    messages.appendChild(message);

    message.scrollIntoView({
        behavior: "smooth",
        block: "end"
    });
}


// Remove typing indicator
function hideTyping() {

    const typingMessage = document.getElementById("typingMessage");

    if (typingMessage) {
        typingMessage.remove();
    }
}


// Send message to backend
async function sendMessage() {

    const message = messageInput.value.trim();

    if (!message || isLoading) {
        return;
    }

    isLoading = true;
    sendBtn.disabled = true;

    addMessage(message, "user");

    messageInput.value = "";
    messageInput.style.height = "auto";

    showTyping();

    try {

        const url = `${API_URL}/chat?message=${encodeURIComponent(message)}`;

        const response = await fetch(url, {
            method: "POST"
        });

        if (!response.ok) {
            throw new Error(`Backend returned ${response.status}`);
        }

        const data = await response.json();

        hideTyping();

        addMessage(
            data.response || "The agent returned an empty response.",
            "assistant"
        );

    } catch (error) {

        hideTyping();

        addMessage(
            "I couldn't connect to the DocTalk backend. Make sure your FastAPI server is running.",
            "assistant"
        );

        console.error("DocTalk error:", error);

    } finally {

        isLoading = false;
        sendBtn.disabled = false;
        messageInput.focus();
    }
}


// Send with button
sendBtn.addEventListener("click", sendMessage);


// Send with Enter, Shift + Enter for new line
messageInput.addEventListener("keydown", function(event) {

    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
});


// Auto-grow textarea
messageInput.addEventListener("input", function() {

    this.style.height = "auto";
    this.style.height = Math.min(this.scrollHeight, 140) + "px";
});


// Quick suggestion cards
document.querySelectorAll(".suggestion-card").forEach(card => {

    card.addEventListener("click", function() {

        messageInput.value = this.dataset.prompt;
        sendMessage();

    });

});


// New conversation
newChatBtn.addEventListener("click", function() {

    messages.innerHTML = "";
    welcomeScreen.style.display = "block";
    messageInput.value = "";
    messageInput.focus();

});

if (documentUpload) {
    documentUpload.addEventListener("change", async function () {
        const file = documentUpload.files[0];

        if (!file) {
            return;
        }

        uploadStatus.textContent = "Uploading document...";
        uploadStatus.style.color = "#f5c76b";

        const formData = new FormData();
        formData.append("file", file);

        try {
            const response = await fetch(`${API_URL}/upload`, {
                method: "POST",
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "Upload failed.");
            }

            uploadStatus.textContent =
                `Uploaded: ${data.filename}`;

            uploadStatus.style.color = "#43d9ad";

        } catch (error) {
            uploadStatus.textContent =
                `Upload failed: ${error.message}`;

            uploadStatus.style.color = "#ff7b8a";
        }
    });
}