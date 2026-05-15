import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate, useParams } from 'react-router-dom';
import Bubbles from './Bubbles';

const EditAgent = () => {
    const { agentId } = useParams();
    const navigate = useNavigate();

    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');

    // Load current agent data when component mounts
    useEffect(() => {
        axios.get(`http://localhost:8000/agents/${agentId}`)
            .then(res => {
                setName(res.data.name || '');
                setDescription(res.data.description || '');
                setLoading(false);
            })
            .catch(() => {
                setError('Agent not found.');
                setLoading(false);
            });
    }, [agentId]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!name.trim()) {
            setError('Agent name is required.');
            return;
        }
        setSaving(true);
        setError('');
        try {
            await axios.put(`http://localhost:8000/agents/${agentId}`, { name, description });
            navigate('/');
        } catch (err) {
            setError('Failed to save. Please try again.');
            setSaving(false);
        }
    };

    if (loading) {
        return (
            <div className="dashboard">
                <Bubbles />
                <div className="header"><h1>Edit Agent</h1></div>
                <div className="modal-content" style={{ textAlign: 'center', color: '#888' }}>
                    Loading agent data...
                </div>
            </div>
        );
    }

    return (
        <div className="dashboard">
            <Bubbles />
            <div className="header">
                <h1>Edit Agent</h1>
                <p>Update the name or description of this agent</p>
            </div>

            <form onSubmit={handleSubmit} className="modal-content">

                {error && (
                    <div style={{
                        background: '#fef2f2', border: '1px solid #fca5a5',
                        color: '#b91c1c', padding: '10px 14px',
                        borderRadius: '8px', marginBottom: '12px', fontSize: '14px'
                    }}>
                        {error}
                    </div>
                )}

                <label style={labelStyle}>Agent Name <span style={{ color: '#ef4444' }}>*</span></label>
                <input
                    placeholder="Agent Name (Required)"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    disabled={saving}
                    required
                />

                <label style={labelStyle}>Description <span style={{ color: '#aaa', fontWeight: 400 }}>(Optional)</span></label>
                <textarea
                    placeholder="What does this agent know about? e.g. KFUEIT university info"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={4}
                    disabled={saving}
                />

                <div style={{ marginTop: '8px' }}>
                    <button type="submit" className="btn-submit" disabled={saving}>
                        {saving ? 'Saving...' : 'Save Changes'}
                    </button>
                    <button
                        type="button"
                        className="btn-cancel"
                        onClick={() => navigate('/')}
                        disabled={saving}
                    >
                        Cancel
                    </button>
                </div>
            </form>
        </div>
    );
};

const labelStyle = {
    display: 'block',
    fontSize: '13px',
    fontWeight: 600,
    color: '#444',
    marginBottom: '6px',
    marginTop: '12px',
};

export default EditAgent;