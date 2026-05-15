import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import AgentList from './components/AgentList';
import CreateAgent from './components/CreateAgent';
import EditAgent from './components/EditAgent';
import './styles/app.css';

const App = () => (
    <Router>
        <Routes>
            <Route path="/" element={<AgentList />} />
            <Route path="/create" element={<CreateAgent />} />
            <Route path="/edit/:agentId" element={<EditAgent />} />
        </Routes>
    </Router>
);

export default App;