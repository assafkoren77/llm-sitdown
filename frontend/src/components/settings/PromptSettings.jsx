import React from 'react';

export default function PromptSettings({
    prompts,
    handlePromptChange,
    handleResetPrompt,
    activePromptTab,
    setActivePromptTab,
}) {
    return (
        <section className="settings-section">
            <h3>System Prompts</h3>
            <p className="section-description">
                Customize the instructions given to the models at each stage.
            </p>

            <div className="prompts-tabs">
                <button
                    className={`prompt-tab ${activePromptTab === 'stage1' ? 'active' : ''}`}
                    onClick={() => setActivePromptTab('stage1')}
                >
                    Stage 1
                </button>
                <button
                    className={`prompt-tab ${activePromptTab === 'brainstorm_turn' ? 'active' : ''}`}
                    onClick={() => setActivePromptTab('brainstorm_turn')}
                >
                    Discussion Turn
                </button>
                <button
                    className={`prompt-tab ${activePromptTab === 'brainstorm_summary' ? 'active' : ''}`}
                    onClick={() => setActivePromptTab('brainstorm_summary')}
                >
                    Summary
                </button>
                <button
                    className={`prompt-tab ${activePromptTab === 'brainstorm_final' ? 'active' : ''}`}
                    onClick={() => setActivePromptTab('brainstorm_final')}
                >
                    Final Statement
                </button>
            </div>

            <div className="prompt-editor">
                {activePromptTab === 'stage1' && (
                    <div className="prompt-content">
                        <label>Stage 1: Initial Response</label>
                        <p className="section-description" style={{ marginBottom: '10px' }}>
                            Guides council members' initial independent responses to the user's question.
                        </p>
                        <p className="prompt-help">Variables: <code>{'{user_query}'}</code>, <code>{'{search_context_block}'}</code></p>
                        <textarea
                            value={prompts.stage1_prompt}
                            onChange={(e) => handlePromptChange('stage1_prompt', e.target.value)}
                            rows={15}
                        />
                        <button className="reset-prompt-btn" onClick={() => handleResetPrompt('stage1_prompt')}>Reset to Default</button>
                    </div>
                )}
                {activePromptTab === 'brainstorm_turn' && (
                    <div className="prompt-content">
                        <label>Discussion Turn</label>
                        <p className="section-description" style={{ marginBottom: '10px' }}>
                            Instructs each council member how to contribute during a brainstorm discussion cycle.
                        </p>
                        <p className="prompt-help">Variables: <code>{'{user_query}'}</code>, <code>{'{initial_answers}'}</code>, <code>{'{discussion_history}'}</code>, <code>{'{model_name}'}</code>, <code>{'{cycle}'}</code></p>
                        <textarea
                            value={prompts.brainstorm_turn_prompt}
                            onChange={(e) => handlePromptChange('brainstorm_turn_prompt', e.target.value)}
                            rows={15}
                        />
                        <button className="reset-prompt-btn" onClick={() => handleResetPrompt('brainstorm_turn_prompt')}>Reset to Default</button>
                    </div>
                )}
                {activePromptTab === 'brainstorm_summary' && (
                    <div className="prompt-content">
                        <label>Chairman Summary</label>
                        <p className="section-description" style={{ marginBottom: '10px' }}>
                            Directs the chairman to summarize progress and check for consensus after each pair of cycles. Must end with <code>CONSENSUS: YES</code> or <code>CONSENSUS: NO</code>.
                        </p>
                        <p className="prompt-help">Variables: <code>{'{user_query}'}</code>, <code>{'{initial_answers}'}</code>, <code>{'{previous_summaries}'}</code>, <code>{'{recent_discussion}'}</code>, <code>{'{cycle}'}</code></p>
                        <textarea
                            value={prompts.brainstorm_summary_prompt}
                            onChange={(e) => handlePromptChange('brainstorm_summary_prompt', e.target.value)}
                            rows={15}
                        />
                        <button className="reset-prompt-btn" onClick={() => handleResetPrompt('brainstorm_summary_prompt')}>Reset to Default</button>
                    </div>
                )}
                {activePromptTab === 'brainstorm_final' && (
                    <div className="prompt-content">
                        <label>Final Statement</label>
                        <p className="section-description" style={{ marginBottom: '10px' }}>
                            Instructs the chairman to draft the definitive final answer after the discussion concludes.
                        </p>
                        <p className="prompt-help">Variables: <code>{'{user_query}'}</code>, <code>{'{initial_answers}'}</code>, <code>{'{discussion_history}'}</code>, <code>{'{summaries_text}'}</code>, <code>{'{reason}'}</code></p>
                        <textarea
                            value={prompts.brainstorm_final_prompt}
                            onChange={(e) => handlePromptChange('brainstorm_final_prompt', e.target.value)}
                            rows={15}
                        />
                        <button className="reset-prompt-btn" onClick={() => handleResetPrompt('brainstorm_final_prompt')}>Reset to Default</button>
                    </div>
                )}
            </div>
        </section>
    );
}
