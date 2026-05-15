<!-- Paste this in your HTML website to add the chatbot button -->
<script>
(function() {
    const agentId = "AGENT_ID_HERE"; // Replace with your agent ID from the dashboard
    const btn = document.createElement('button');
    btn.style = "position:fixed;bottom:20px;right:20px;width:60px;height:60px;border-radius:50%;background:linear-gradient(135deg,#6e8efb,#a777e3);border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 12px rgba(0,0,0,0.2);z-index:9999;transition:transform 0.2s;";
    
    // Unique chatbot SVG (not standard emoji)
    btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="white"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-2-8c0 1.1-.9 2-2 2s-2-.9-2-2 .9-2 2-2 2 .9 2 2zm6 0c0 1.1-.9 2-2 2s-2-.9-2-2 .9-2 2-2 2 .9 2 2z"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/></svg>`;
    
    btn.onmouseover = () => btn.style.transform = "scale(1.1)";
    btn.onmouseout = () => btn.style.transform = "scale(1)";
    
    btn.onclick = () => {
        const chatWindow = document.createElement('div');
        chatWindow.style = "position:fixed;bottom:90px;right:20px;width:300px;height:400px;background:white;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,0.15);z-index:9998;display:flex;flex-direction:column;";
        chatWindow.innerHTML = `
            <div style="background:linear-gradient(135deg,#6e8efb,#a777e3);color:white;padding:15px;border-radius:12px 12px 0 0;display:flex;justify-content:space-between;">
                <span>Chatbot</span>
                <button onclick="this.parentElement.parentElement.remove()" style="background:none;border:none;color:white;cursor:pointer;font-size:18px;">×</button>
            </div>
            <div style="flex:1;padding:15px;overflow-y:auto;">
                <p style="color:#666;font-size:14px;">Agent trained and ready (connect to backend chat API for full functionality)</p>
            </div>
        `;
        document.body.appendChild(chatWindow);
    };
    document.body.appendChild(btn);
})();
</script>