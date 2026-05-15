import React from 'react';

const Bubbles = () => {
    const bubbles = Array.from({ length: 15 }).map((_, i) => (
        <div
            key={i}
            className="bubble"
            style={{
                width: `${Math.random() * 20 + 5}px`,
                height: `${Math.random() * 20 + 5}px`,
                left: `${Math.random() * 100}%`,
                top: `${Math.random() * 100}%`,
                animationDelay: `${Math.random() * 10}s`
            }}
        />
    ));
    return <>{bubbles}</>;
};

export default Bubbles;