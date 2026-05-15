# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LLM Council Plus is a brainstorm deliberation system where multiple LLMs collaboratively answer user questions through:
1. **Stage 1**: Parallel independent responses from all council members (with optional web search context)
2. **Brainstorm Discussion**: Multi-cycle round-robin debate — each model builds on the conversation; the chairman summarizes every 2 cycles and checks for consensus
3. **Final Statement**: Chairman drafts a definitive answer once consensus is reached or max cycles hit

**Key Innovation**: Hybrid architecture supporting OpenRouter (cloud), Ollama (local), Groq (fast inference), direct provider connections, and custom OpenAI-compatible endpoints.

## Running the Application

**Quick Start:**
```bash
./start.sh
```

**Manual Start:**
```bash
# Backend (from project root)
uv run python -m backend.main

# Frontend (in new terminal)
cd frontend
npm run dev
```

**Ports:**
- Backend: `http://localhost:8001` (NOT 8000 - avoid conflicts)
- Frontend: `http://localhost:5173`

**Network Access:**
```bash
# Backend already listens on 0.0.0.0:8001
# Frontend with network access:
cd frontend && npm run dev -- --host
```

**Installing Dependencies:**
```bash
# Backend
uv sync

# Frontend
cd frontend
npm install
```

**Important**: If switching between Intel/Apple Silicon Macs with iCloud sync:
```bash
rm -rf frontend/node_modules && cd frontend && npm install
```
This fixes binary incompatibilities (e.g., `@rollup/rollup-darwin-*` variants).

## Architecture Overview

### Backend (`backend/`)

**Provider System** (`backend/providers/`)
- **Base**: `base.py` - Abstract interface for all LLM providers
- **Implementations**: `openrouter.py`, `ollama.py`, `groq.py`, `openai.py`, `anthropic.py`, `google.py`, `mistral.py`, `deepseek.py`, `custom_openai.py`
- **Auto-routing**: Model IDs with prefix (e.g., `openai:gpt-4.1`, `ollama:llama3`, `custom:model-name`) route to correct provider
- **Routing logic**: `council.py:get_provider_for_model()` handles prefix parsing

**Core Modules**

| Module | Purpose |
|--------|---------|
| `council.py` | Orchestration: stage1 collection, brainstorm discussion, final synthesis, title generation |
| `search.py` | Web search: DuckDuckGo, Tavily, Brave with Jina Reader content fetch |
| `settings.py` | Config management, persisted to `data/settings.json` |
| `prompts.py` | Default system prompts for all stages (stage1, brainstorm turn/summary/final, title) |
| `main.py` | FastAPI app with streaming SSE endpoint |
| `storage.py` | Conversation persistence in `data/conversations/{id}.json` |

### Frontend (`frontend/src/`)

| Component | Purpose |
|-----------|---------|
| `App.jsx` | Main orchestration, SSE streaming, conversation state |
| `ChatInterface.jsx` | User input, web search toggle, renders per-message views |
| `BrainstormView.jsx` | Full brainstorm UI: initial perspectives, cycle cards, chairman summaries, steering, final statement, chairman follow-up chat |
| `Stage1.jsx` | Tab view of individual model responses (initial perspectives within BrainstormView) |
| `CouncilGrid.jsx` | Visual grid of council members with provider icons |
| `Settings.jsx` | 5-section settings: LLM API Keys, Council Config, System Prompts, Search Providers, Backup & Reset |
| `Sidebar.jsx` | Conversation list with inline delete confirmation |
| `SearchableModelSelect.jsx` | Searchable dropdown for model selection |
| `settings/PromptSettings.jsx` | Prompt editor tabs: Stage 1, Discussion Turn, Summary, Final Statement |
| `settings/CouncilConfig.jsx` | Model selection, temperature sliders, brainstorm cycle count |

**Styling**: "Council Chamber" dark theme (refined Midnight Glass). CSS variables in `index.css` (`--font-display`: Syne, `--font-ui`: Plus Jakarta Sans, `--font-content`: Source Serif 4, `--font-code`: JetBrains Mono). Primary accent blue (#3b82f6), chairman gold (#fbbf24). Staggered hero/card animations; glass panels with backdrop-filter.

## Critical Implementation Details

### Python Module Imports
**ALWAYS** use relative imports in backend modules:
```python
from .config import ...
from .council import ...
```
**NEVER** use absolute imports like `from backend.config import ...`

**Run backend as module** from project root:
```bash
uv run python -m backend.main  # Correct
cd backend && python main.py  # WRONG - breaks imports
```

### Model ID Prefix Format
```
openrouter:anthropic/claude-sonnet-4  → Cloud via OpenRouter
ollama:llama3.1:latest                → Local via Ollama
groq:llama3-70b-8192                  → Fast inference via Groq
openai:gpt-4.1                        → Direct OpenAI connection
anthropic:claude-sonnet-4             → Direct Anthropic connection
custom:model-name                     → Custom OpenAI-compatible endpoint
```

### Model Name Display Helper
Use this pattern in Stage components to handle both `/` and `:` delimiters:
```jsx
const getShortModelName = (modelId) => {
  if (!modelId) return 'Unknown';
  if (modelId.includes('/')) return modelId.split('/').pop();
  if (modelId.includes(':')) return modelId.split(':').pop();
  return modelId;
};
```

### Provider Icon Detection (CouncilGrid.jsx)
Check prefixes FIRST before name-based detection to avoid mismatches:
```jsx
const getProviderInfo = (modelId) => {
    const id = modelId.toLowerCase();
    // Check prefixes FIRST (order matters!)
    if (id.startsWith('custom:')) return PROVIDER_CONFIG.custom;
    if (id.startsWith('ollama:')) return PROVIDER_CONFIG.ollama;
    if (id.startsWith('groq:')) return PROVIDER_CONFIG.groq;
    // Then check name-based patterns...
};
```

### Brainstorm Consensus Detection
The chairman's summary prompt requires exactly `CONSENSUS: YES` or `CONSENSUS: NO` (uppercase) as the final line. Detection in `council.py`:
```python
consensus = "CONSENSUS: YES" in summary_text.upper()
```
If the prompt is customized, this sentinel must be preserved.

### Streaming & Abort Logic
- Backend checks `request.is_disconnected()` inside loops
- Frontend aborts via AbortController signal
- **Critical**: Always inject raw `Request` object into streaming endpoints (Pydantic models lack `is_disconnected()`)

### ReactMarkdown Safety
```jsx
<div className="markdown-content">
  <ReactMarkdown>
    {typeof content === 'string' ? content : String(content || '')}
  </ReactMarkdown>
</div>
```
Always wrap in `.markdown-content` div and ensure string type (some providers return arrays/objects).

### Tab Bounds Safety
In Stage1, auto-adjust activeTab when out of bounds during streaming:
```jsx
useEffect(() => {
  if (activeTab >= responses.length && responses.length > 0) {
    setActiveTab(responses.length - 1);
  }
}, [responses.length]);
```

### Brainstorm User Steering
- Backend always pauses between cycles for user input (`await_user_input` SSE event, 300s timeout)
- Frontend auto-skips the pause when the steering checkbox is unchecked (`userSteeringRef`)
- Steering is submitted via `POST /api/conversations/{id}/brainstorm/steer`
- At max cycles without consensus, `await_final_decision` event prompts extend (+2 cycles) or finalize

## Common Gotchas

1. **Port Conflicts**: Backend uses 8001 (not 8000). Update `backend/main.py` and `frontend/src/api.js` together.

2. **CORS Errors**: Frontend origins must match `main.py` CORS middleware (localhost:5173 and :3000).

3. **Duplicate Tabs**: Use immutable state updates (spread operator), not mutations. StrictMode runs effects twice.

4. **Search Rate Limits**: DuckDuckGo can rate-limit. Retry logic in `search.py` handles this.

5. **Jina Reader 451 Errors**: Many news sites block AI scrapers. Use Tavily/Brave or set `full_content_results` to 0.

6. **Model Deduplication**: When multiple sources provide same model, use Map-based deduplication preferring direct connections.

7. **Binary Dependencies**: `node_modules` in iCloud can break between Mac architectures. Delete and reinstall.

8. **Custom Endpoint Icons**: Models from custom endpoints may match name patterns (e.g., "claude"). Check `custom:` prefix first.

9. **Brainstorm Prompt Formatting**: Brainstorm prompts use `.format()` — curly braces in prompt text must be escaped as `{{` / `}}`.

## Data Flow

```
User Query (+ optional web search)
    ↓
[Web Search: DuckDuckGo/Tavily/Brave + Jina Reader]
    ↓
Stage 1: Parallel queries → Stream individual responses
    ↓
Brainstorm Discussion:
  for each cycle (up to brainstorm_max_cycles):
    → Each model responds in turn (uses previous cycle's turns + all initial answers)
    → Every 2 cycles: chairman summarizes + checks CONSENSUS: YES/NO
    → Between cycles: optional user steering pause
    → At max cycles: user decides extend (+2) or finalize
    ↓
Final Synthesis: Chairman drafts definitive answer
    ↓
Save conversation (stage1 + brainstorm turns/summaries/final)
```

## Brainstorm Mode

The only execution mode. Key parameters:

- **`brainstorm_max_cycles`** (2–10, default 4): Max discussion cycles before asking user to extend or finalize. Chairman summarizes every 2 cycles.
- **`council_temperature`** (default 0.5): Controls creativity of council member turns
- **`chairman_temperature`** (default 0.4): Controls chairman summaries and final synthesis

**SSE event sequence**: `brainstorm_start` → `brainstorm_init` → `brainstorm_cycle_start` → `brainstorm_turn_start/complete` (×N models) → `brainstorm_summary_start/complete` (every 2 cycles) → optionally `brainstorm_await_input` / `brainstorm_await_final_decision` → `brainstorm_complete` → `brainstorm_final_start` → `brainstorm_final_complete`

**Brainstorm-specific endpoints**:
```
POST /api/conversations/{id}/brainstorm/steer         — submit steering input
POST /api/conversations/{id}/brainstorm/final_decision — 'extend' or 'finalize'
POST /api/conversations/{id}/chairman_followup         — follow-up chat after discussion
```

## Testing & Debugging

```bash
# Check Ollama models
curl http://localhost:11434/api/tags

# Test custom endpoint
curl https://your-endpoint.com/v1/models -H "Authorization: Bearer $API_KEY"

# View logs
# Watch terminal running backend/main.py
```

## Web Search

**Providers**: DuckDuckGo (free), Tavily (API), Brave (API)

**Full Content Fetching**: Jina Reader (`https://r.jina.ai/{url}`) extracts article text for top N results (configurable 0-10, default 3). Falls back to summary if fetch fails or yields <500 chars. 25-second timeout per article, 60-second total search budget.

**Search Query Processing**:
- **Direct** (default): Send exact query to search engine
- **YAKE**: Extract keywords first (useful for long prompts)

## Settings

**UI Sections** (sidebar navigation):
1. **LLM API Keys**: OpenRouter, Groq, Ollama, Direct providers, Custom endpoint
2. **Council Config**: Model selection with Remote/Local toggles, temperature controls, brainstorm cycle count, "I'm Feeling Lucky" randomizer
3. **System Prompts**: 4 tabs — Stage 1, Discussion Turn, Summary, Final Statement — each with reset-to-default
4. **Search Providers**: DuckDuckGo, Tavily, Brave + Jina full content settings
5. **Backup & Reset**: Import/Export config, reset to defaults

**Auto-Save Behavior**:
- **Credentials auto-save**: API keys and URLs save immediately on successful test
- **Configs require manual save**: Model selections, prompts, temperatures
- UX flow: Test → Success → Auto-save → Clear input → "Settings saved!"

**Temperature Controls**:
- Council Heat: Stage 1 + discussion turn creativity (default: 0.5)
- Chairman Heat: Summaries + final synthesis (default: 0.4)

**System Prompt Variables**:

| Prompt | Variables |
|--------|-----------|
| Stage 1 | `{user_query}`, `{search_context_block}` |
| Discussion Turn | `{user_query}`, `{initial_answers}`, `{discussion_history}`, `{model_name}`, `{cycle}` |
| Summary | `{user_query}`, `{initial_answers}`, `{previous_summaries}`, `{recent_discussion}`, `{cycle}` |
| Final Statement | `{user_query}`, `{initial_answers}`, `{discussion_history}`, `{summaries_text}`, `{reason}` |

**Rate Limit Estimates** (per brainstorm run with N council members, C cycles):
- Stage 1: N calls
- Discussion turns: N × C calls
- Summaries: floor(C/2) calls (chairman, every 2 cycles)
- Final synthesis: 1 call
- Total ≈ `N × (C + 1) + floor(C/2) + 1`

**Storage**: `data/settings.json`

## Design Principles

- **Graceful Degradation**: Single model failure doesn't block entire council
- **Transparency**: All raw outputs inspectable (initial perspectives collapsible, cycle cards expandable)
- **Progress Indicators**: Cycle/model progress during streaming
- **Provider Flexibility**: Mix cloud, local, and custom endpoints freely
- **User Steering**: Optional mid-discussion guidance injected into turn and summary prompts

## Code Safety Guidelines

**Communication:**
- NEVER make assumptions when requirements are vague - ask for clarification
- Provide options with pros/cons for different approaches
- Confirm understanding before significant changes

**Code Safety:**
- NEVER use placeholders like `// ...` in edits - this deletes code
- Always provide full content when writing/editing files
- FastAPI: Inject raw `Request` object to access `is_disconnected()`
- React: Use spread operators for immutable state updates (StrictMode runs effects twice)

## Future Enhancements

- Model performance analytics over time
- Export conversations to markdown/PDF
- Backend caching for repeated queries
- Multiple custom endpoints support
