import React, { useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import Bubbles from './Bubbles';

const CreateAgent = () => {
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        await axios.post('http://localhost:8000/agents', { name, description });
        navigate('/');
    };

    return (
        <div className="dashboard">
            <Bubbles />
            <div className="header">
                <h1>Create New Agent</h1>
            </div>
            <form onSubmit={handleSubmit} className="modal-content">
                <input
                    placeholder="Agent Name (Required)"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                />
                <textarea
                    placeholder="Description (Optional)"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={4}
                />
                <div>
                    <button type="submit" className="btn-submit">Create</button>
                    <button type="button" className="btn-cancel" onClick={() => navigate('/')}>Cancel</button>
                </div>
            </form>
        </div>
    );
};

export default CreateAgent;