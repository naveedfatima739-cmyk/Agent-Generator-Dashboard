import React, { useEffect, useState } from 'react';
import axios from 'axios';

const EmbedModal = ({ agent, onClose }) => {
    const [embedCode, setEmbedCode] = useState('');

    useEffect(() => {
        axios.get(`http://localhost:8000/agents/${agent.id}/embed-code`).then(res => setEmbedCode(res.data.embed_code));
    }, []);

    return (
        <div className="modal">
            <div className="modal-content">
                <h2>Embed Code for {agent.name}</h2>
                <textarea value={embedCode} rows={10} readOnly />
                <button className="btn-submit" onClick={() => { navigator.clipboard.writeText(embedCode); alert('Copied!'); }}>Copy Code</button>
                <button className="btn-cancel" onClick={onClose}>Close</button>
            </div>
        </div>
    );
};

export default EmbedModal;