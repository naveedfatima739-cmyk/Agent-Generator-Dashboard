import React, { useEffect, useState } from 'react';
import axios from 'axios';
import Bubbles from './Bubbles';
import TrainModal from './TrainModal';
import EmbedModal from './EmbedModal';
import ChatModal from './ChatModal';

const AgentList = () => {
    const [agents, setAgents] = useState([]);
    const [selectedAgent, setSelectedAgent] = useState(null);
    const [showTrain, setShowTrain] = useState(false);
    const [showEmbed, setShowEmbed] = useState(false);
    const [showChat, setShowChat] = useState(false);

    useEffect(() => {
        axios.get('http://localhost:8000/agents').then(res => setAgents(res.data));
    }, []);

    const deleteAgent = async (id) => {
        await axios.delete(`http://localhost:8000/agents/${id}`);
        setAgents(agents.filter(a => a.id !== id));
    };

    return (
        <div className="dashboard">
            <Bubbles />
            <div className="header">
                <h1>Agent Dashboard</h1>
                <p>Manage your chatbot agents</p>
            </div>
            <button className="btn-create" onClick={() => window.location.href = '/create'}>
                + Create New Agent
            </button>
            {agents.map(agent => (
                <div key={agent.id} className="agent-card">
                    <div>
                        <h3>{agent.name}</h3>
                        <p>{agent.description || 'No description'}</p>
                    </div>
                    <div className="agent-actions">
                        <button className="btn-edit" onClick={() => window.location.href = `/edit/${agent.id}`}>Edit</button>
                        <button className="btn-train" onClick={() => { setSelectedAgent(agent); setShowTrain(true); }}>Train</button>
                        <button className="btn-delete" onClick={() => deleteAgent(agent.id)}>Delete</button>
                        <button className="btn-train" onClick={() => { setSelectedAgent(agent); setShowEmbed(true); }}>Get Embed</button>
                        {agent.dataset_path && (
                            <button className="btn-submit" style={{background: '#6e8efb'}} onClick={() => { setSelectedAgent(agent); setShowChat(true); }}>Chat</button>
                        )}
                    </div>
                </div>
            ))}
            {showTrain && <TrainModal agent={selectedAgent} onClose={() => setShowTrain(false)} />}
            {showEmbed && <EmbedModal agent={selectedAgent} onClose={() => setShowEmbed(false)} />}
            {showChat && <ChatModal agent={selectedAgent} onClose={() => setShowChat(false)} />}
        </div>
    );
};

export default AgentList;