import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const TrainModal = ({ agent, onClose }) => {
    const [url, setUrl] = useState('');
    const [prompt, setPrompt] = useState('');
    const [description, setDescription] = useState('');
    const [isTraining, setIsTraining] = useState(false);
    const [progress, setProgress] = useState(0);
    const [statusText, setStatusText] = useState('');
    const [done, setDone] = useState(false);
    const intervalRef = useRef(null);

    const messages = [
        'Connecting to website...',
        'Crawling pages...',
        'Extracting content...',
        'Processing sub-pages...',
        'Building dataset...',
        'Saving training data...',
        'Almost done...',
    ];

    const startProgress = () => {
        let current = 0;
        let msgIndex = 0;
        setStatusText(messages[0]);

        intervalRef.current = setInterval(() => {
            current += Math.random() * 4 + 1; // increase by 1–5% randomly
            if (current >= 90) current = 90;   // cap at 90% until real done
            setProgress(Math.floor(current));

            msgIndex = Math.min(Math.floor((current / 90) * messages.length), messages.length - 1);
            setStatusText(messages[msgIndex]);
        }, 800);
    };

    const stopProgress = (success) => {
        clearInterval(intervalRef.current);
        setProgress(100);
        setStatusText(success ? '✅ Training complete!' : '❌ Training failed.');
        setDone(true);
    };

    useEffect(() => {
        return () => clearInterval(intervalRef.current); // cleanup on unmount
    }, []);

    const handleSubmit = async () => {
        if (!url || !prompt) {
            alert('Please fill in the URL and Training Prompt.');
            return;
        }
        setIsTraining(true);
        setProgress(0);
        setDone(false);
        startProgress();

        try {
            await axios.post(`http://localhost:8000/agents/${agent.id}/train`, { url, prompt, description });
            stopProgress(true);
            setTimeout(() => onClose(), 1500);
        } catch (err) {
            stopProgress(false);
        }
    };

    return (
        <div className="modal">
            <div className="modal-content">
                <h2>Train {agent.name}</h2>

                <input
                    placeholder="Website URL (Required)"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    disabled={isTraining}
                    required
                />
                <textarea
                    placeholder="Training Prompt (Required)"
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    rows={4}
                    disabled={isTraining}
                    required
                />
                <textarea
                    placeholder="Dataset Description (Optional)"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={2}
                    disabled={isTraining}
                />

                {/* ── Progress Bar ── */}
                {isTraining && (
                    <div style={styles.progressWrapper}>
                        <div style={styles.statusRow}>
                            <span style={styles.statusText}>{statusText}</span>
                            <span style={styles.percentText}>{progress}%</span>
                        </div>
                        <div style={styles.progressTrack}>
                            <div
                                style={{
                                    ...styles.progressFill,
                                    width: `${progress}%`,
                                    background: done && progress === 100
                                        ? statusText.includes('✅') ? '#22c55e' : '#ef4444'
                                        : 'linear-gradient(90deg, #6e8efb, #a777e3)',
                                }}
                            />
                        </div>
                    </div>
                )}

                <div>
                    {!isTraining && (
                        <>
                            <button type="button" className="btn-submit" onClick={handleSubmit}>Train</button>
                            <button type="button" className="btn-cancel" onClick={onClose}>Cancel</button>
                        </>
                    )}
                    {isTraining && !done && (
                        <button type="button" className="btn-cancel" disabled style={{ opacity: 0.5 }}>
                            Training in progress...
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};

const styles = {
    progressWrapper: {
        margin: '16px 0',
        padding: '14px 16px',
        background: '#f8f9ff',
        borderRadius: '10px',
        border: '1px solid #e0e7ff',
    },
    statusRow: {
        display: 'flex',
        justifyContent: 'space-between',
        marginBottom: '8px',
    },
    statusText: {
        fontSize: '13px',
        color: '#555',
        fontWeight: 500,
    },
    percentText: {
        fontSize: '13px',
        color: '#6e8efb',
        fontWeight: 700,
    },
    progressTrack: {
        width: '100%',
        height: '10px',
        background: '#e2e8f0',
        borderRadius: '99px',
        overflow: 'hidden',
    },
    progressFill: {
        height: '100%',
        borderRadius: '99px',
        transition: 'width 0.6s ease, background 0.3s ease',
    },
};

export default TrainModal;