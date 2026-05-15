import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';

const ChatModal = ({ agent, onClose }) => {
    const [messages, setMessages] = useState([
        { sender: 'bot', text: `Hello! I'm ${agent.name}. Ask me anything about the content I was trained on.` }
    ]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const messagesEndRef = useRef(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(scrollToBottom, [messages]);

    const sendMessage = async () => {
        if (!input.trim()) return;
        const userMessage = { sender: 'user', text: input };
        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setLoading(true);

        try {
            const res = await axios.post(`http://localhost:8000/agents/${agent.id}/chat`, {
                message: input
            });
            const botMessage = { sender: 'bot', text: res.data.reply };
            setMessages(prev => [...prev, botMessage]);
        } catch (e) {
    let errorMsg = '❌ Error: Could not connect to agent.';
    if (e.response) {
        // Backend is running but returned an error
        errorMsg = `❌ Server error ${e.response.status}: ${e.response.data?.detail || 'Unknown error'}`;
    } else if (e.request) {
        // Backend is not running at all
        errorMsg = '⚠️ Backend server is not running. Please start it:\n\ncd backend\nuvicorn main:app --reload --port 8000';
    }
    setMessages(prev => [...prev, { sender: 'bot', text: errorMsg }]);
    }
    };

    return (
        <div className="modal">
            <div className="modal-content" style={{ width: '400px', maxWidth: '90%', height: '500px', display: 'flex', flexDirection: 'column', padding: 0, overflow: 'hidden' }}>
                {/* Header */}
                <div style={{ background: 'linear-gradient(135deg,#6e8efb,#a777e3)', color: 'white', padding: '15px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontWeight: 600 }}>{agent.name} - Chat Test</span>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'white', cursor: 'pointer', fontSize: '20px', lineHeight: 1 }}>×</button>
                </div>

                {/* Messages */}
                <div style={{ flex: 1, padding: '15px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '10px', background: '#f8f9fa' }}>
                    {messages.map((msg, idx) => (
                        <div
                            key={idx}
                            style={{
                                alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                                background: msg.sender === 'user' ? 'linear-gradient(135deg,#6e8efb,#a777e3)' : 'white',
                                color: msg.sender === 'user' ? 'white' : '#333',
                                padding: '8px 14px',
                                borderRadius: msg.sender === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                                maxWidth: '80%',
                                fontSize: '14px',
                                boxShadow: msg.sender === 'bot' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none'
                            }}
                        >
                            {msg.text}
                        </div>
                    ))}
                    {loading && <div style={{ alignSelf: 'flex-start', color: '#999', fontSize: '13px' }}>Thinking...</div>}
                    <div ref={messagesEndRef} />
                </div>

                {/* Input */}
                <div style={{ padding: '12px', borderTop: '1px solid #eee', display: 'flex', gap: '8px', background: 'white' }}>
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
                        placeholder="Type a message..."
                        style={{ flex: 1, padding: '8px 12px', border: '1px solid #ddd', borderRadius: '20px', outline: 'none', fontSize: '14px' }}
                    />
                    <button onClick={sendMessage} disabled={loading} style={{ background: 'linear-gradient(135deg,#6e8efb,#a777e3)', color: 'white', border: 'none', borderRadius: '50%', width: '36px', height: '36px', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '16px' }}>➤</button>
                </div>
            </div>
        </div>
    );
};

export default ChatModal;