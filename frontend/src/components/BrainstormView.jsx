import { useState, useEffect, useRef, Fragment } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import StageTimer from './StageTimer';
import { getShortModelName, getModelVisuals } from '../utils/modelHelpers';
import './BrainstormView.css';

// ── Inline SVG icons (no lucide-react) ──────────────────────────────────────

const ChevronDown = ({ size = 12 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="6 9 12 15 18 9" />
    </svg>
);
const ChevronRight = ({ size = 12 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="9 6 15 12 9 18" />
    </svg>
);
const SendIcon = ({ size = 11 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="22" y1="2" x2="11" y2="13" />
        <polygon points="22 2 15 22 11 13 2 9 22 2" fill="currentColor" stroke="none" />
    </svg>
);
const XIcon = ({ size = 13 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
);
const UserIcon = ({ size = 10 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
        <circle cx="12" cy="7" r="4" />
    </svg>
);

// ── Turn card ────────────────────────────────────────────────────────────────

function Turn({ turn, open, onToggle, isLiveStreaming }) {
    const visuals = getModelVisuals(turn.model);
    const shortName = getShortModelName(turn.model);
    const initial = shortName.charAt(0).toUpperCase();
    const content = turn.error
        ? `⚠️ ${turn.error_message || 'Model failed to respond'}`
        : (typeof turn.content === 'string' ? turn.content : String(turn.content || ''));
    const preview = content.length > 120 ? content.slice(0, 120).trimEnd() + '…' : content;

    return (
        <div
            className={`bs-turn${turn.error ? ' bs-turn-error' : ''}${isLiveStreaming ? ' bs-turn-live' : ''}`}
            style={{ borderLeftColor: visuals.color }}
        >
            <div
                className="bs-turn-header"
                onClick={isLiveStreaming ? undefined : onToggle}
                style={{ cursor: isLiveStreaming ? 'default' : 'pointer' }}
            >
                <span className="bs-avatar" style={{ color: visuals.color, borderColor: `${visuals.color}55` }}>
                    {initial}
                </span>
                <span className="bs-turn-model" style={{ color: visuals.color }}>{shortName}</span>
                {isLiveStreaming ? (
                    <span className="bs-writing">
                        <span className="bs-cursor" />
                        writing…
                    </span>
                ) : (
                    <>
                        {!open && content && (
                            <span className="bs-turn-preview">{preview}</span>
                        )}
                        <span className="bs-chevron">
                            {open ? <ChevronDown /> : <ChevronRight />}
                        </span>
                    </>
                )}
            </div>
            {open && !isLiveStreaming && (
                <div className="bs-turn-content markdown-content">
                    {turn.error ? (
                        <p className="bs-error-text">⚠️ {turn.error_message || 'Model failed to respond'}</p>
                    ) : (
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {typeof content === 'string' ? content : String(content || '')}
                        </ReactMarkdown>
                    )}
                </div>
            )}
        </div>
    );
}

// ── Cycle pill ───────────────────────────────────────────────────────────────

function CyclePill({ label, open, onToggle, active, note, memberVisuals = [] }) {
    return (
        <button
            className={`bs-cycle-pill${active ? ' bs-cycle-pill-active' : ''}`}
            onClick={onToggle}
        >
            <span className="bs-pill-chevron">{open ? <ChevronDown size={10} /> : <ChevronRight size={10} />}</span>
            <span className="bs-pill-label">{label}</span>
            {active && <span className="bs-pill-live-dot" title="in progress" />}
            {note && <span className="bs-pill-note">{note}</span>}
            {memberVisuals.length > 0 && (
                <span className="bs-pill-avatars">
                    {memberVisuals.map((v, i) => (
                        <span
                            key={i}
                            className="bs-pill-avatar"
                            style={{ color: v.color, borderColor: `${v.color}55` }}
                            title={v.name}
                        >
                            {(v.short || v.name || '?').charAt(0).toUpperCase()}
                        </span>
                    ))}
                </span>
            )}
        </button>
    );
}

// ── Chairman divider ─────────────────────────────────────────────────────────

function ChairmanDivider({ summary, open, onToggle }) {
    const chairmanName = getShortModelName(summary.chairman_model || '');
    const displayText = summary.summary
        ? summary.summary.replace(/CONSENSUS:\s*(YES|NO)\s*$/im, '').trim()
        : '';

    return (
        <div className={`bs-chairman${summary.consensus_reached ? ' bs-chairman-consensus' : ''}`}>
            <div className="bs-chairman-header" onClick={onToggle}>
                <span className="bs-chairman-icon">⚖️</span>
                <span className="bs-chairman-label">chairman · after cycle {summary.cycle}</span>
                {chairmanName && <span className="bs-chairman-name">{chairmanName}</span>}
                <span className={`bs-consensus-badge${summary.consensus_reached ? ' yes' : ' no'}`}>
                    {summary.consensus_reached ? 'consensus ✓' : 'no consensus'}
                </span>
                <span className="bs-chevron">{open ? <ChevronDown /> : <ChevronRight />}</span>
            </div>
            {open && (
                <div className="bs-chairman-content markdown-content bs-serif-italic">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {typeof displayText === 'string' ? displayText : String(displayText || '')}
                    </ReactMarkdown>
                </div>
            )}
        </div>
    );
}

// ── Steering note (user input record) ────────────────────────────────────────

function SteeringNote({ entry, open, onToggle }) {
    const content = typeof entry.input === 'string' ? entry.input : String(entry.input || '');
    const preview = content.length > 120 ? content.slice(0, 120).trimEnd() + '…' : content;

    return (
        <div className="bs-steering-note">
            <div className="bs-turn-header" style={{ cursor: 'pointer' }} onClick={onToggle}>
                <span className="bs-avatar bs-avatar-user">
                    <UserIcon size={10} />
                </span>
                <span className="bs-turn-model bs-steering-note-label">you · steering note</span>
                {!open && content && <span className="bs-turn-preview">{preview}</span>}
                <span className="bs-chevron">{open ? <ChevronDown /> : <ChevronRight />}</span>
            </div>
            {open && (
                <div className="bs-turn-content markdown-content">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {content}
                    </ReactMarkdown>
                </div>
            )}
        </div>
    );
}

// ── Final Decision Toast ──────────────────────────────────────────────────────

function FinalDecisionToast({ finalCycle, onDecision }) {
    return (
        <div className="bs-toast bs-toast-decision">
            <div className="bs-toast-body">
                <div className="bs-toast-title">⏹ Cycle {finalCycle} — no consensus yet</div>
                <div className="bs-toast-hint">What would you like to do?</div>
                <div className="bs-toast-actions">
                    <button className="bs-toast-btn bs-toast-btn-primary" onClick={() => onDecision('extend')}>
                        ➕ 2 more cycles
                    </button>
                    <button className="bs-toast-btn" onClick={() => onDecision('finalize')}>
                        📋 Issue final statement
                    </button>
                </div>
            </div>
        </div>
    );
}

// ── Chairman Follow-up Chat ───────────────────────────────────────────────────

function ChairmanChat({ messages, isLoading, onSend, chairmanModel }) {
    const [input, setInput] = useState('');
    const bottomRef = useRef(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, isLoading]);

    const handleSend = () => {
        const trimmed = input.trim();
        if (trimmed) {
            onSend(trimmed);
            setInput('');
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    const shortName = chairmanModel ? getShortModelName(chairmanModel) : null;

    return (
        <div className="bs-chairman-chat">
            <div className="bs-chairman-chat-header">
                <span className="bs-chairman-icon">💬</span>
                <span className="bs-chairman-chat-title">continue with chairman</span>
                {shortName && <span className="bs-chairman-name">{shortName}</span>}
            </div>
            <div className="bs-cc-messages">
                {messages.map((m, i) => (
                    <div key={i} className={`bs-cc-message bs-cc-${m.role}`}>
                        <div className="bs-cc-label">{m.role === 'user' ? 'you' : 'chairman'}</div>
                        <div className="bs-cc-body markdown-content">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                {typeof m.content === 'string' ? m.content : String(m.content || '')}
                            </ReactMarkdown>
                        </div>
                    </div>
                ))}
                {isLoading && <ThinkingIndicator label="Chairman is thinking…" variant="chairman" />}
                <div ref={bottomRef} />
            </div>
            <div className="bs-cc-input-row">
                <textarea
                    className="bs-cc-textarea"
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask the chairman a follow-up…"
                    rows={2}
                    disabled={isLoading}
                />
                <button
                    className="bs-cc-send"
                    onClick={handleSend}
                    disabled={!input.trim() || isLoading}
                >
                    ➤
                </button>
            </div>
        </div>
    );
}

// ── Steering toast (floating overlay) ────────────────────────────────────────

const TOAST_DURATION = 270;

function SteeringToast({ cycle, onUserInput }) {
    const [expanded, setExpanded] = useState(false);
    const [text, setText] = useState('');
    const [remaining, setRemaining] = useState(TOAST_DURATION);
    const timerRef = useRef(null);

    useEffect(() => {
        if (expanded) {
            clearInterval(timerRef.current);
            return;
        }
        timerRef.current = setInterval(() => {
            setRemaining(r => {
                if (r <= 1) {
                    clearInterval(timerRef.current);
                    onUserInput('');
                    return 0;
                }
                return r - 1;
            });
        }, 1000);
        return () => clearInterval(timerRef.current);
    }, [expanded, onUserInput]);

    const handleSend = () => {
        onUserInput(text.trim());
        setText('');
    };

    const handleSkip = () => onUserInput('');

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (text.trim()) handleSend();
        }
    };

    const progress = (remaining / TOAST_DURATION) * 100;

    return (
        <div className="bs-toast">
            <div className="bs-toast-progress-bar">
                <div className="bs-toast-progress-fill" style={{ width: `${progress}%` }} />
            </div>
            {!expanded ? (
                <div className="bs-toast-body">
                    <div className="bs-toast-title">Cycle {cycle} complete</div>
                    <div className="bs-toast-hint">Want to guide the next cycle?</div>
                    <div className="bs-toast-actions">
                        <button className="bs-toast-btn bs-toast-btn-primary" onClick={() => setExpanded(true)}>
                            Add a note
                        </button>
                        <button className="bs-toast-btn" onClick={handleSkip}>
                            Skip <span className="bs-toast-timer">{remaining}s</span>
                        </button>
                    </div>
                </div>
            ) : (
                <div className="bs-toast-body">
                    <div className="bs-toast-title">🧭 Steer cycle {cycle + 1}</div>
                    <textarea
                        className="bs-toast-textarea"
                        placeholder="Guide the next cycle…"
                        value={text}
                        onChange={e => setText(e.target.value)}
                        onKeyDown={handleKeyDown}
                        rows={3}
                        autoFocus
                    />
                    <div className="bs-toast-actions">
                        <button
                            className="bs-toast-btn bs-toast-btn-primary"
                            onClick={handleSend}
                            disabled={!text.trim()}
                        >
                            <SendIcon size={11} /> Send
                        </button>
                        <button className="bs-toast-btn" onClick={() => setExpanded(false)}>
                            <XIcon size={11} /> Back
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}

// ── Final statement ───────────────────────────────────────────────────────────

function FinalStatement({ final, status }) {
    const isConsensus = status === 'consensus';
    return (
        <div className={`bs-final${isConsensus ? ' bs-final-consensus' : ''}`}>
            <div className="bs-final-header">
                <span className="bs-final-label">📋 final statement</span>
                {isConsensus && (
                    <span className="bs-consensus-badge yes">consensus reached ✓</span>
                )}
            </div>
            <div className="bs-final-content markdown-content">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {typeof final.response === 'string' ? final.response : String(final.response || '')}
                </ReactMarkdown>
            </div>
        </div>
    );
}

// ── Thinking indicator ────────────────────────────────────────────────────────

function ThinkingIndicator({ label, variant = 'default' }) {
    return (
        <div className={`bs-thinking${variant === 'chairman' ? ' bs-thinking-chairman' : ''}`}>
            <span className="bs-thinking-dot" />
            <span className="bs-thinking-dot" />
            <span className="bs-thinking-dot" />
            <span className="bs-thinking-label">{label}</span>
        </div>
    );
}

// ── Main export ───────────────────────────────────────────────────────────────

export default function BrainstormView({
    stage1 = [],
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
    awaitingFinalDecision = null,
    onFinalDecision,
    chairmanChat = [],
    chairmanChatLoading = false,
    onChairmanFollowup,
    chairmanModel = null,
}) {
    const isDone = !!status;

    // Cycle open/closed: true = collapsed, undefined/false = open
    const [collapsed, setCollapsed] = useState({});
    const [initialCollapsed, setInitialCollapsed] = useState(false);

    // Lifted turn open state. Key: `${cycle}-${model}`. undefined = open, false = closed.
    const [turnOpen, setTurnOpen] = useState({});

    // Chairman summary open state. Key: cycle. undefined = open, false = closed.
    const [summaryOpen, setSummaryOpen] = useState({});

    // Steering note open state. Key: global index in userInputs array.
    const [steeringNoteOpen, setSteeringNoteOpen] = useState({});

    // Derived cycle data
    const cycleMap = {};
    for (const turn of turns) {
        const c = turn.cycle || 1;
        if (!cycleMap[c]) cycleMap[c] = [];
        cycleMap[c].push(turn);
    }
    const summaryMap = {};
    for (const s of summaries) summaryMap[s.cycle] = s;

    const activeCycle = progress?.cycle || 0;
    const maxCycle = progress?.maxCycles || 0;

    // Include the active cycle even if it has no turns yet
    const allCycles = [...new Set([
        ...Object.keys(cycleMap).map(Number),
        ...(activeCycle > 0 && !isDone ? [activeCycle] : []),
    ])].sort((a, b) => a - b);

    // Auto-collapse completed cycles when a new one starts
    useEffect(() => {
        if (activeCycle > 0) {
            setCollapsed(prev => {
                const next = { ...prev };
                allCycles.forEach(c => { if (c < activeCycle) next[c] = true; });
                next[activeCycle] = false;
                return next;
            });
        }
    }, [activeCycle]); // eslint-disable-line react-hooks/exhaustive-deps

    // Collapse everything when discussion ends (but keep summaries open — they're the key content)
    useEffect(() => {
        if (isDone) {
            const nextCollapsed = {};
            allCycles.forEach(c => { nextCollapsed[c] = true; });
            setCollapsed(nextCollapsed);
            setInitialCollapsed(true);

            const nextTurnOpen = {};
            turns.forEach(t => { nextTurnOpen[`${t.cycle ?? 1}-${t.model}`] = false; });
            stage1.forEach(r => { nextTurnOpen[`0-${r.model}`] = false; });
            setTurnOpen(nextTurnOpen);
        }
    }, [isDone]); // eslint-disable-line react-hooks/exhaustive-deps

    // Auto-expand cycle when awaiting user steering input
    useEffect(() => {
        if (awaitingUserInput?.cycle) {
            setCollapsed(prev => ({ ...prev, [awaitingUserInput.cycle]: false }));
        }
    }, [awaitingUserInput?.cycle]);

    // Helpers
    const isCycleOpen = (cycle) => collapsed[cycle] !== true;
    const toggleCycle = (cycle) => setCollapsed(prev => ({ ...prev, [cycle]: !prev[cycle] }));

    const isTurnOpen = (key) => turnOpen[key] !== false;
    const toggleTurn = (key) => setTurnOpen(prev => ({
        ...prev,
        [key]: prev[key] === false ? undefined : false,
    }));

    const isSummaryOpen = (cycle) => summaryOpen[cycle] !== false;
    const toggleSummary = (cycle) => setSummaryOpen(prev => ({
        ...prev,
        [cycle]: prev[cycle] === false ? undefined : false,
    }));

    const isSteeringNoteOpen = (idx) => steeringNoteOpen[idx] !== false;
    const toggleSteeringNote = (idx) => setSteeringNoteOpen(prev => ({
        ...prev,
        [idx]: prev[idx] === false ? undefined : false,
    }));

    // Expand / collapse all
    const hasContent = stage1.length > 0 || allCycles.length > 0;
    const allAreCollapsed = (stage1.length === 0 || initialCollapsed) &&
        (allCycles.length === 0 || allCycles.every(c => collapsed[c] === true));

    const collapseAll = () => {
        const nextCollapsed = {};
        allCycles.forEach(c => { nextCollapsed[c] = true; });
        setCollapsed(nextCollapsed);
        setInitialCollapsed(true);

        const nextTurnOpen = {};
        turns.forEach(t => { nextTurnOpen[`${t.cycle ?? 1}-${t.model}`] = false; });
        stage1.forEach(r => { nextTurnOpen[`0-${r.model}`] = false; });
        setTurnOpen(nextTurnOpen);

        const nextSteeringNoteOpen = {};
        userInputs.forEach((_, i) => { nextSteeringNoteOpen[i] = false; });
        setSteeringNoteOpen(nextSteeringNoteOpen);
    };

    const expandAll = () => {
        setCollapsed({});
        setInitialCollapsed(false);
        setTurnOpen({});
        const nextSummaryOpen = {};
        summaries.forEach(s => { nextSummaryOpen[s.cycle] = true; });
        setSummaryOpen(nextSummaryOpen);
        const nextSteeringNoteOpen = {};
        userInputs.forEach((_, i) => { nextSteeringNoteOpen[i] = true; });
        setSteeringNoteOpen(nextSteeringNoteOpen);
    };

    // Status badge
    const statusBadge = status === 'consensus'
        ? <span className="bs-status-badge bs-status-consensus">✅ Consensus</span>
        : status === 'max_cycles'
            ? <span className="bs-status-badge bs-status-max">⏹ Max Cycles</span>
            : progress?.currentModel
                ? <span className="bs-status-badge bs-status-active">💬 Cycle {progress.cycle || '?'}{maxCycle > 0 ? `/${maxCycle}` : ''}</span>
                : <span className="bs-status-badge bs-status-active">💬 Starting…</span>;

    return (
        <div className="brainstorm-view">
            {/* Header */}
            <div className="bs-header">
                <div className="bs-header-left">
                    <span className="bs-header-title">🧠 brainstorm</span>
                    {startTime && <StageTimer startTime={startTime} endTime={endTime} />}
                    {statusBadge}
                </div>
                {hasContent && (
                    <button className="bs-expand-btn" onClick={allAreCollapsed ? expandAll : collapseAll}>
                        {allAreCollapsed ? '↕ Expand all' : '↕ Collapse all'}
                    </button>
                )}
            </div>

            {/* Body — flat scroll */}
            <div className="bs-body">
                {/* Initial Perspectives */}
                {stage1.length > 0 && (
                    <>
                        <CyclePill
                            label="initial perspectives"
                            open={!initialCollapsed}
                            onToggle={() => setInitialCollapsed(v => !v)}
                            note="parallel · independent"
                            memberVisuals={stage1.map(r => getModelVisuals(r.model))}
                        />
                        {!initialCollapsed && stage1.map((r, i) => {
                            const key = `0-${r.model}`;
                            return (
                                <Turn
                                    key={i}
                                    turn={{
                                        model: r.model,
                                        content: r.response ?? '',
                                        error: r.error ?? false,
                                        error_message: r.error_message ?? null,
                                        cycle: 0,
                                    }}
                                    open={isTurnOpen(key)}
                                    onToggle={() => toggleTurn(key)}
                                    isLiveStreaming={false}
                                />
                            );
                        })}
                    </>
                )}

                {/* Cycles */}
                {allCycles.map((cycle) => {
                    const isOpen = isCycleOpen(cycle);
                    const isActiveCycle = cycle === activeCycle && !isDone;
                    const cycleTurns = cycleMap[cycle] || [];
                    const memberVisuals = [...new Map(
                        cycleTurns.map(t => [t.model, getModelVisuals(t.model)])
                    ).values()];
                    const cycleUserInputs = userInputs
                        .map((u, globalIdx) => ({ u, globalIdx }))
                        .filter(({ u }) => u.cycle === cycle);
                    const isCurrentModelLive =
                        isActiveCycle &&
                        progress?.currentModel &&
                        !cycleTurns.some(t => t.model === progress.currentModel);

                    return (
                        <Fragment key={cycle}>
                            {/* Cycle pill + collapsible turns */}
                            <CyclePill
                                label={`cycle ${cycle}${maxCycle > 0 ? ` / ${maxCycle}` : ''}`}
                                open={isOpen}
                                onToggle={() => toggleCycle(cycle)}
                                active={isActiveCycle}
                                note={`${cycleTurns.length} turn${cycleTurns.length !== 1 ? 's' : ''}`}
                                memberVisuals={memberVisuals}
                            />
                            {isOpen && (
                                <>
                                    {cycleTurns.map((turn, i) => {
                                        const key = `${cycle}-${turn.model}`;
                                        return (
                                            <Turn
                                                key={i}
                                                turn={turn}
                                                open={isTurnOpen(key)}
                                                onToggle={() => toggleTurn(key)}
                                                isLiveStreaming={false}
                                            />
                                        );
                                    })}
                                    {/* Ghost card for currently streaming model */}
                                    {isCurrentModelLive && (
                                        <Turn
                                            turn={{
                                                model: progress.currentModel,
                                                content: '',
                                                error: false,
                                                cycle,
                                            }}
                                            open={true}
                                            onToggle={() => {}}
                                            isLiveStreaming={true}
                                        />
                                    )}
                                </>
                            )}

                            {/* Chairman summary — sits between cycles, always visible */}
                            {loadingSummary && isActiveCycle && !summaryMap[cycle] && (
                                <ThinkingIndicator label="Chairman is summarizing…" variant="chairman" />
                            )}
                            {summaryMap[cycle] && (
                                <ChairmanDivider
                                    summary={summaryMap[cycle]}
                                    open={isSummaryOpen(cycle)}
                                    onToggle={() => toggleSummary(cycle)}
                                />
                            )}

                            {/* Inline steering input — shown right after the chairman summary for this cycle */}
                            {awaitingUserInput?.cycle === cycle && onUserInput && (
                                <SteeringToast cycle={cycle} onUserInput={onUserInput} />
                            )}

                            {/* Steering notes — sit between cycles, always visible */}
                            {cycleUserInputs.map(({ u, globalIdx }) => (
                                <SteeringNote
                                    key={globalIdx}
                                    entry={u}
                                    open={isSteeringNoteOpen(globalIdx)}
                                    onToggle={() => toggleSteeringNote(globalIdx)}
                                />
                            ))}
                        </Fragment>
                    );
                })}

                {/* Thinking indicator before any cycles exist */}
                {progress?.currentModel && !status && allCycles.length === 0 && (
                    <ThinkingIndicator label={`${getShortModelName(progress.currentModel)} is thinking…`} />
                )}

                {/* Inline final decision — shown after all cycles, before the final statement */}
                {awaitingFinalDecision && onFinalDecision && (
                    <FinalDecisionToast
                        finalCycle={awaitingFinalDecision.finalCycle}
                        onDecision={onFinalDecision}
                    />
                )}

                {/* Final statement */}
                {loadingFinal && !final && (
                    <ThinkingIndicator label="Chairman is drafting the final statement…" variant="chairman" />
                )}
                {final && <FinalStatement final={final} status={status} />}

                {/* Chairman follow-up chat — shown after final statement */}
                {final && onChairmanFollowup && (
                    <ChairmanChat
                        messages={chairmanChat}
                        isLoading={chairmanChatLoading}
                        onSend={onChairmanFollowup}
                        chairmanModel={chairmanModel}
                    />
                )}
            </div>
        </div>
    );
}
