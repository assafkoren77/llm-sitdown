import { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import StageTimer from './StageTimer';
import { getShortModelName, getModelVisuals } from '../utils/modelHelpers';
import './BrainstormView.css';

const DIGEST_LIMIT = 180;

function StatusBadge({ status, progress }) {
    if (status === 'consensus') return <span className="brainstorm-badge consensus">✅ Consensus Reached</span>;
    if (status === 'max_cycles') return <span className="brainstorm-badge max-cycles">⏹ Max Cycles Reached</span>;
    if (progress?.currentModel) {
        return <span className="brainstorm-badge in-progress">💬 Cycle {progress.cycle || '?'}/{progress.maxCycles || '?'}</span>;
    }
    return <span className="brainstorm-badge in-progress">💬 Starting...</span>;
}

function TurnCard({ turn, forceCollapsed }) {
    const visuals = getModelVisuals(turn.model);
    const shortName = getShortModelName(turn.model);
    const [isOpen, setIsOpen] = useState(false);

    useEffect(() => {
        if (forceCollapsed) setIsOpen(false);
    }, [forceCollapsed]);

    const content = turn.error
        ? `⚠️ ${turn.error_message || 'Model failed to respond'}`
        : (typeof turn.content === 'string' ? turn.content : String(turn.content || ''));
    const snippet = content.length > 120 ? content.slice(0, 120).trimEnd() + '…' : content;

    return (
        <div className={`brainstorm-turn ${turn.error ? 'turn-error' : ''} ${isOpen ? 'turn-open' : 'turn-collapsed'}`}>
            <button className="turn-toggle" onClick={() => setIsOpen(v => !v)}>
                <span className="turn-toggle-icon">{isOpen ? '▼' : '▶'}</span>
                <span className="turn-icon">{visuals.icon}</span>
                <span className="turn-model" style={{ color: visuals.color }}>{shortName}</span>
                {!isOpen && <span className="turn-snippet">{snippet}</span>}
            </button>
            {isOpen && (
                <div className="turn-content markdown-content">
                    {turn.error ? (
                        <p className="error-text">⚠️ {turn.error_message || 'Model failed to respond'}</p>
                    ) : (
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{typeof turn.content === 'string' ? turn.content : String(turn.content || '')}</ReactMarkdown>
                    )}
                </div>
            )}
        </div>
    );
}

function SummaryCard({ summary, forceCollapsed }) {
    const displayText = summary.summary
        ? summary.summary.replace(/CONSENSUS:\s*(YES|NO)\s*$/im, '').trim()
        : '';
    const chairmanName = getShortModelName(summary.chairman_model || '');
    const [isOpen, setIsOpen] = useState(!forceCollapsed);

    useEffect(() => {
        if (forceCollapsed) setIsOpen(false);
    }, [forceCollapsed]);

    return (
        <div className={`brainstorm-summary ${summary.consensus_reached ? 'summary-consensus' : ''} ${isOpen ? 'summary-open' : 'summary-collapsed'}`}>
            <button className="summary-toggle" onClick={() => setIsOpen(v => !v)}>
                <span className="summary-toggle-icon">{isOpen ? '▼' : '▶'}</span>
                <span className="summary-label">⚖️ Chairman Summary — after cycle {summary.cycle}</span>
                <span className="summary-chairman">{chairmanName}</span>
                <span className={`consensus-signal ${summary.consensus_reached ? 'yes' : 'no'}`}>
                    CONSENSUS: {summary.consensus_reached ? 'YES' : 'NO'}
                </span>
            </button>
            {isOpen && (
                <div className="summary-content markdown-content">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{typeof displayText === 'string' ? displayText : String(displayText || '')}</ReactMarkdown>
                </div>
            )}
        </div>
    );
}

function SteeringPrompt({ cycle, onSubmit }) {
    const [text, setText] = useState('');

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            onSubmit(text.trim());
            setText('');
        }
    };

    return (
        <div className="steering-prompt">
            <div className="steering-prompt-header">🧭 Your turn — steer the discussion (cycle {cycle})</div>
            <textarea
                className="steering-input"
                placeholder="Type guidance for the next cycle, or press Enter to continue without steering..."
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={2}
                autoFocus
            />
            <div className="steering-hint">Press Enter to submit · Shift+Enter for new line · Enter with empty text to skip</div>
        </div>
    );
}

function UserInputCard({ entry }) {
    return (
        <div className="user-input-card">
            <div className="user-input-header">
                <span className="user-input-icon">👤</span>
                <span className="user-input-label">You (after cycle {entry.cycle})</span>
            </div>
            <div className="user-input-content markdown-content">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{typeof entry.input === 'string' ? entry.input : String(entry.input || '')}</ReactMarkdown>
            </div>
        </div>
    );
}

function DigestView({ turns, summaries, userInputs = [] }) {
    // Group turns by cycle
    const cycleMap = {};
    for (const turn of turns) {
        const c = turn.cycle || 1;
        if (!cycleMap[c]) cycleMap[c] = [];
        cycleMap[c].push(turn);
    }
    const summaryMap = {};
    for (const s of summaries) summaryMap[s.cycle] = s;

    const allCycles = Object.keys(cycleMap).map(Number).sort((a, b) => a - b);

    return (
        <div className="digest-view">
            {allCycles.map(cycle => (
                <div key={cycle} className="digest-cycle">
                    <div className="digest-cycle-label">Cycle {cycle}</div>
                    <div className="digest-turns">
                        {(cycleMap[cycle] || []).map((turn, i) => {
                            const visuals = getModelVisuals(turn.model);
                            const shortName = getShortModelName(turn.model);
                            const text = turn.error
                                ? `⚠️ ${turn.error_message || 'Error'}`
                                : (turn.content || '');
                            const snippet = text.length > DIGEST_LIMIT
                                ? text.slice(0, DIGEST_LIMIT).trimEnd() + '…'
                                : text;
                            return (
                                <div key={i} className="digest-turn">
                                    <span className="digest-icon">{visuals.icon}</span>
                                    <span className="digest-model" style={{ color: visuals.color }}>{shortName}</span>
                                    <span className="digest-snippet">{snippet}</span>
                                </div>
                            );
                        })}
                    </div>
                    {summaryMap[cycle] && (
                        <div className="digest-summary">
                            ⚖️ Chairman: {
                                (() => {
                                    const t = summaryMap[cycle].summary || '';
                                    const clean = t.replace(/CONSENSUS:\s*(YES|NO)\s*$/im, '').trim();
                                    return clean.length > DIGEST_LIMIT
                                        ? clean.slice(0, DIGEST_LIMIT).trimEnd() + '…'
                                        : clean;
                                })()
                            }
                            <span className={`digest-consensus ${summaryMap[cycle].consensus_reached ? 'yes' : 'no'}`}>
                                {summaryMap[cycle].consensus_reached ? ' ✅' : ' ❌'}
                            </span>
                        </div>
                    )}
                    {userInputs.filter(u => u.cycle === cycle).map((u, i) => (
                        <div key={i} className="digest-user-input">
                            👤 You: {u.input.length > DIGEST_LIMIT ? u.input.slice(0, DIGEST_LIMIT).trimEnd() + '…' : u.input}
                        </div>
                    ))}
                </div>
            ))}
        </div>
    );
}

export default function BrainstormView({
    turns = [],
    summaries = [],
    status = null,
    final = null,
    loadingFinal = false,
    progress = null,
    loadingSummary = false,
    startTime = null,
    endTime = null,
    awaitingUserInput = null,
    onUserInput,
    userInputs = [],
}) {
    const isDone = !!status;
    const [activeTab, setActiveTab] = useState('final');

    // Switch to 'final' tab automatically when it arrives
    useEffect(() => {
        if (final) setActiveTab('final');
    }, [!!final]);

    // Group turns by cycle
    const cycleMap = {};
    for (const turn of turns) {
        const c = turn.cycle || 1;
        if (!cycleMap[c]) cycleMap[c] = [];
        cycleMap[c].push(turn);
    }
    const summaryMap = {};
    for (const s of summaries) summaryMap[s.cycle] = s;
    const allCycles = Object.keys(cycleMap).map(Number).sort((a, b) => a - b);
    const maxCycle = progress?.maxCycles || 0;
    const activeCycle = progress?.cycle || 0;

    // Collapsed state: each cycle key → bool. Default: only the active cycle is expanded.
    const [collapsed, setCollapsed] = useState({});
    useEffect(() => {
        if (activeCycle > 0) {
            setCollapsed(prev => {
                const next = { ...prev };
                // Collapse all previously open cycles when a new one starts
                allCycles.forEach(c => { if (c < activeCycle) next[c] = true; });
                next[activeCycle] = false;
                return next;
            });
        }
    }, [activeCycle]);

    // When discussion ends, collapse all cycles by default
    useEffect(() => {
        if (isDone) {
            setCollapsed(prev => {
                const next = { ...prev };
                allCycles.forEach(c => { next[c] = true; });
                return next;
            });
        }
    }, [isDone]);

    // When awaiting user input, make sure the steering cycle is expanded
    useEffect(() => {
        if (awaitingUserInput?.cycle) {
            setCollapsed(prev => ({ ...prev, [awaitingUserInput.cycle]: false }));
        }
    }, [awaitingUserInput?.cycle]);

    const toggleCycle = (cycle) => {
        setCollapsed(prev => ({ ...prev, [cycle]: !prev[cycle] }));
    };

    const isCycleCollapsed = (cycle) => collapsed[cycle] !== false && collapsed[cycle] !== undefined
        ? collapsed[cycle]
        : false;

    return (
        <div className="brainstorm-view">
            <div className="stage-header">
                <h3>🧠 Brainstorm Discussion</h3>
                <div className="stage-header-right">
                    {startTime && <StageTimer startTime={startTime} endTime={endTime} />}
                    <StatusBadge status={status} progress={progress} />
                </div>
            </div>

            {/* Tabs — only show once discussion is done or final is loading */}
            {(isDone || loadingFinal || final) && (
                <div className="brainstorm-tabs">
                    <button
                        className={`brainstorm-tab ${activeTab === 'final' ? 'active' : ''}`}
                        onClick={() => setActiveTab('final')}
                    >
                        📋 Final Statement
                    </button>
                    <button
                        className={`brainstorm-tab ${activeTab === 'discussion' ? 'active' : ''}`}
                        onClick={() => setActiveTab('discussion')}
                    >
                        💬 Discussion
                    </button>
                    <button
                        className={`brainstorm-tab ${activeTab === 'digest' ? 'active' : ''}`}
                        onClick={() => setActiveTab('digest')}
                    >
                        📝 Digest
                    </button>
                </div>
            )}

            {/* Final Statement tab */}
            {(isDone || loadingFinal || final) && activeTab === 'final' && (
                <div className="brainstorm-final">
                    {loadingFinal && !final && (
                        <div className="brainstorm-thinking">
                            <span className="thinking-dot" />
                            <span className="thinking-dot" />
                            <span className="thinking-dot" />
                            <span className="thinking-model">Chairman is drafting the final statement...</span>
                        </div>
                    )}
                    {final && (
                        <div className="brainstorm-final-content markdown-content">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                {typeof final.response === 'string' ? final.response : String(final.response || '')}
                            </ReactMarkdown>
                        </div>
                    )}
                </div>
            )}

            {/* Digest tab */}
            {(isDone || loadingFinal || final) && activeTab === 'digest' && (
                <DigestView turns={turns} summaries={summaries} userInputs={userInputs} />
            )}

            {/* Discussion tab (collapsible cycles) — always visible when not done, or when tab selected */}
            {(!isDone && !loadingFinal && !final) || activeTab === 'discussion' ? (
                <div className="brainstorm-cycles">
                    {allCycles.map((cycle) => {
                        const isCollapsed = isCycleCollapsed(cycle);
                        const turnCount = (cycleMap[cycle] || []).length;
                        const hasSummary = !!summaryMap[cycle];
                        return (
                            <div key={cycle} className="brainstorm-cycle">
                                <button
                                    className="cycle-label cycle-toggle"
                                    onClick={() => toggleCycle(cycle)}
                                    aria-expanded={!isCollapsed}
                                >
                                    <span className="cycle-toggle-icon">{isCollapsed ? '▶' : '▼'}</span>
                                    <span>Cycle {cycle}{maxCycle > 0 ? ` / ${maxCycle}` : ''}</span>
                                    {isCollapsed && (
                                        <span className="cycle-summary-pill">
                                            {turnCount} turn{turnCount !== 1 ? 's' : ''}
                                            {hasSummary && ' · summary'}
                                        </span>
                                    )}
                                </button>

                                {!isCollapsed && (
                                    <>
                                        {(cycleMap[cycle] || []).map((turn, i) => (
                                            <TurnCard key={i} turn={turn} forceCollapsed={isDone} />
                                        ))}
                                        {summaryMap[cycle] && <SummaryCard summary={summaryMap[cycle]} forceCollapsed={isDone} />}
                                        {userInputs.filter(u => u.cycle === cycle).map((u, i) => (
                                            <UserInputCard key={i} entry={u} />
                                        ))}
                                        {awaitingUserInput?.cycle === cycle && onUserInput && (
                                            <SteeringPrompt cycle={cycle} onSubmit={onUserInput} />
                                        )}
                                    </>
                                )}
                            </div>
                        );
                    })}

                    {/* Live thinking indicator */}
                    {progress?.currentModel && !status && (
                        <div className="brainstorm-thinking">
                            <span className="thinking-dot" />
                            <span className="thinking-dot" />
                            <span className="thinking-dot" />
                            <span className="thinking-model">{getShortModelName(progress.currentModel)} is thinking...</span>
                        </div>
                    )}

                    {/* Chairman summary loading */}
                    {loadingSummary && !status && (
                        <div className="brainstorm-thinking summary-thinking">
                            <span className="thinking-dot" />
                            <span className="thinking-dot" />
                            <span className="thinking-dot" />
                            <span className="thinking-model">Chairman is summarizing...</span>
                        </div>
                    )}
                </div>
            ) : null}
        </div>
    );
}
