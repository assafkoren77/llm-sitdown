"""3-stage LLM Council orchestration."""

from typing import List, Dict, Any, Tuple
import asyncio
import logging
from . import openrouter
from . import ollama_client
from .config import get_council_models, get_chairman_model
from .search import perform_web_search, SearchProvider
from .settings import get_settings

logger = logging.getLogger(__name__)


from .providers.openai import OpenAIProvider
from .providers.anthropic import AnthropicProvider
from .providers.google import GoogleProvider
from .providers.mistral import MistralProvider
from .providers.deepseek import DeepSeekProvider
from .providers.openrouter import OpenRouterProvider
from .providers.ollama import OllamaProvider
from .providers.groq import GroqProvider
from .providers.custom_openai import CustomOpenAIProvider

# Initialize providers
PROVIDERS = {
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
    "google": GoogleProvider(),
    "mistral": MistralProvider(),
    "deepseek": DeepSeekProvider(),
    "groq": GroqProvider(),
    "openrouter": OpenRouterProvider(),
    "ollama": OllamaProvider(),
    "custom": CustomOpenAIProvider(),
}

def get_provider_for_model(model_id: str) -> Any:
    """Determine the provider for a given model ID."""
    if ":" in model_id:
        provider_name = model_id.split(":")[0]
        if provider_name in PROVIDERS:
            return PROVIDERS[provider_name]

    # Default to OpenRouter for unprefixed models (legacy support)
    return PROVIDERS["openrouter"]


async def query_model(model: str, messages: List[Dict[str, str]], timeout: float = 120.0, temperature: float = 0.7) -> Dict[str, Any]:
    """Dispatch query to appropriate provider."""
    provider = get_provider_for_model(model)
    return await provider.query(model, messages, timeout, temperature)


async def query_models_parallel(models: List[str], messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """Dispatch parallel query to appropriate providers."""
    tasks = []
    model_to_task_map = {}
    
    # Group models by provider to optimize batching if supported (mostly for OpenRouter/Ollama legacy)
    # But for simplicity and modularity, we'll just spawn individual tasks for now
    # OpenRouter and Ollama wrappers might handle their own internal concurrency if we called a batch method,
    # but the base interface is single query.
    # To maintain OpenRouter's batch efficiency if it exists, we could check type, but let's stick to simple asyncio.gather first.
    
    # Actually, the previous implementation used specific batch logic for Ollama and OpenRouter.
    # We should preserve that if possible, OR just rely on asyncio.gather which is fine for HTTP clients.
    # The previous `_query_ollama_batch` was just a helper to strip prefixes.
    # `openrouter.query_models_parallel` was doing the gather.
    
    # Let's just use asyncio.gather for all. It's clean and effective.
    
    async def _query_safe(m: str):
        try:
            return m, await query_model(m, messages)
        except Exception as e:
            return m, {"error": True, "error_message": str(e)}

    tasks = [_query_safe(m) for m in models]
    results = await asyncio.gather(*tasks)
    
    return dict(results)


async def stage1_collect_responses(user_query: str, search_context: str = "", request: Any = None) -> Any:
    """
    Stage 1: Collect individual responses from all council models.

    Args:
        user_query: The user's question
        search_context: Optional web search results to provide context
        request: FastAPI request object for checking disconnects

    Yields:
        - First yield: total_models (int)
        - Subsequent yields: Individual model results (dict)
    """
    settings = get_settings()

    # Build search context block if search results provided
    search_context_block = ""
    if search_context:
        from .prompts import STAGE1_SEARCH_CONTEXT_TEMPLATE
        search_context_block = STAGE1_SEARCH_CONTEXT_TEMPLATE.format(search_context=search_context)

    # Use customizable Stage 1 prompt
    try:
        prompt_template = settings.stage1_prompt
        if not prompt_template:
            from .prompts import STAGE1_PROMPT_DEFAULT
            prompt_template = STAGE1_PROMPT_DEFAULT

        prompt = prompt_template.format(
            user_query=user_query,
            search_context_block=search_context_block
        )
    except (KeyError, AttributeError, TypeError) as e:
        logger.warning(f"Error formatting Stage 1 prompt: {e}. Using fallback.")
        prompt = f"{search_context_block}Question: {user_query}" if search_context_block else user_query

    messages = [{"role": "user", "content": prompt}]

    # Prepare tasks for all models
    models = get_council_models()
    
    # Yield total count first
    yield len(models)

    council_temp = settings.council_temperature

    async def _query_safe(m: str):
        try:
            return m, await query_model(m, messages, temperature=council_temp)
        except Exception as e:
            return m, {"error": True, "error_message": str(e)}

    # Create tasks
    tasks = [asyncio.create_task(_query_safe(m)) for m in models]
    
    # Process as they complete
    pending = set(tasks)
    try:
        while pending:
            # Check for client disconnect
            if request and await request.is_disconnected():
                logger.info("Client disconnected during Stage 1. Cancelling tasks...")
                for t in pending:
                    t.cancel()
                raise asyncio.CancelledError("Client disconnected")

            # Wait for the next task to complete (with timeout to check for disconnects)
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED, timeout=1.0)

            for task in done:
                try:
                    model, response = await task
                    
                    result = None
                    if response is not None:
                        if response.get('error'):
                            # Include failed models with error info
                            result = {
                                "model": model,
                                "response": None,
                                "error": response.get('error'),
                                "error_message": response.get('error_message', 'Unknown error')
                            }
                        else:
                            # Successful response - ensure content is always a string
                            content = response.get('content', '')
                            if not isinstance(content, str):
                                # Handle case where API returns non-string content (array, object, etc.)
                                content = str(content) if content is not None else ''
                            result = {
                                "model": model,
                                "response": content,
                                "error": None
                            }
                    
                    if result:
                        yield result
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Error processing Stage 1 task result: {e}")

    except asyncio.CancelledError:
        # Ensure all tasks are cancelled if we get cancelled
        for t in tasks:
            if not t.done():
                t.cancel()
        raise


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    search_context: str = "",
    request: Any = None
) -> Any: # Returns an async generator
    """
    Stage 2: Collect peer rankings from all council models.
    
    Yields:
        - First yield: label_to_model mapping (dict)
        - Subsequent yields: Individual model results (dict)
    """
    settings = get_settings()

    # Filter to only successful responses for ranking
    successful_results = [r for r in stage1_results if not r.get('error')]

    # Create anonymized labels for responses (Response A, Response B, etc.)
    labels = [chr(65 + i) for i in range(len(successful_results))]  # A, B, C, ...

    # Create mapping from label to model name
    label_to_model = {
        f"Response {label}": result['model']
        for label, result in zip(labels, successful_results)
    }
    
    # Yield the mapping first so the caller has it
    yield label_to_model

    # Build the ranking prompt
    responses_text = "\n\n".join([
        f"Response {label}:\n{result['response']}"
        for label, result in zip(labels, successful_results)
    ])

    search_context_block = ""
    if search_context:
        search_context_block = f"Context from Web Search:\n{search_context}\n"

    try:
        # Ensure prompt is not None
        prompt_template = settings.stage2_prompt
        if not prompt_template:
            from .prompts import STAGE2_PROMPT_DEFAULT
            prompt_template = STAGE2_PROMPT_DEFAULT

        ranking_prompt = prompt_template.format(
            user_query=user_query,
            responses_text=responses_text,
            search_context_block=search_context_block
        )
    except (KeyError, AttributeError, TypeError) as e:
        logger.warning(f"Error formatting Stage 2 prompt: {e}. Using fallback.")
        ranking_prompt = f"Question: {user_query}\n\n{responses_text}\n\nRank these responses."

    messages = [{"role": "user", "content": ranking_prompt}]

    # Only use models that successfully responded in Stage 1
    # (no point asking failed models to rank - they'll just fail again)
    successful_models = [r['model'] for r in successful_results]

    # Use dedicated Stage 2 temperature (lower for consistent ranking output)
    stage2_temp = settings.stage2_temperature

    async def _query_safe(m: str):
        try:
            return m, await query_model(m, messages, temperature=stage2_temp)
        except Exception as e:
            return m, {"error": True, "error_message": str(e)}

    # Create tasks
    tasks = [asyncio.create_task(_query_safe(m)) for m in successful_models]

    # Process as they complete
    pending = set(tasks)
    try:
        while pending:
            # Check for client disconnect
            if request and await request.is_disconnected():
                logger.info("Client disconnected during Stage 2. Cancelling tasks...")
                for t in pending:
                    t.cancel()
                raise asyncio.CancelledError("Client disconnected")

            # Wait for the next task to complete (with timeout to check for disconnects)
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED, timeout=1.0)

            for task in done:
                try:
                    model, response = await task
                    
                    result = None
                    if response is not None:
                        if response.get('error'):
                            # Include failed models with error info
                            result = {
                                "model": model,
                                "ranking": None,
                                "parsed_ranking": [],
                                "error": response.get('error'),
                                "error_message": response.get('error_message', 'Unknown error')
                            }
                        else:
                            # Ensure content is always a string before parsing
                            full_text = response.get('content', '')
                            if not isinstance(full_text, str):
                                # Handle case where API returns non-string content (array, object, etc.)
                                full_text = str(full_text) if full_text is not None else ''
                            
                            # Parse with expected count to avoid duplicates
                            expected_count = len(successful_results)
                            parsed = parse_ranking_from_text(full_text, expected_count=expected_count)
                            
                            result = {
                                "model": model,
                                "ranking": full_text,
                                "parsed_ranking": parsed,
                                "error": None
                            }
                    
                    if result:
                        yield result
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Error processing task result: {e}")

    except asyncio.CancelledError:
        # Ensure all tasks are cancelled if we get cancelled
        for t in tasks:
            if not t.done():
                t.cancel()
        raise


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    search_context: str = ""
) -> Dict[str, Any]:
    """
    Stage 3: Chairman synthesizes final response.

    Args:
        user_query: The original user query
        stage1_results: Individual model responses from Stage 1
        stage2_results: Rankings from Stage 2

    Returns:
        Dict with 'model' and 'response' keys
    """
    settings = get_settings()

    # Build comprehensive context for chairman (only include successful responses)
    stage1_text = "\n\n".join([
        f"Model: {result['model']}\nResponse: {result.get('response', 'No response')}"
        for result in stage1_results
        if result.get('response') is not None
    ])

    stage2_text = "\n\n".join([
        f"Model: {result['model']}\nRanking: {result.get('ranking', 'No ranking')}"
        for result in stage2_results
        if result.get('ranking') is not None
    ])

    search_context_block = ""
    if search_context:
        search_context_block = f"Context from Web Search:\n{search_context}\n"

    try:
        # Ensure prompt is not None
        prompt_template = settings.stage3_prompt
        if not prompt_template:
            from .prompts import STAGE3_PROMPT_DEFAULT
            prompt_template = STAGE3_PROMPT_DEFAULT

        chairman_prompt = prompt_template.format(
            user_query=user_query,
            stage1_text=stage1_text,
            stage2_text=stage2_text,
            search_context_block=search_context_block
        )
    except (KeyError, AttributeError, TypeError) as e:
        logger.warning(f"Error formatting Stage 3 prompt: {e}. Using fallback.")
        chairman_prompt = f"Question: {user_query}\n\nSynthesis required."

    # Determine message structure based on whether the prompt is default or custom
    from .prompts import STAGE3_PROMPT_DEFAULT
    
    # Check if we are using the default prompt (or if it's empty/None, which falls back to default)
    is_default_prompt = (not settings.stage3_prompt) or (settings.stage3_prompt.strip() == STAGE3_PROMPT_DEFAULT.strip())

    if is_default_prompt:
        # If using default, split into System (Persona) and User (Data) for better adherence at low temp
        messages = [
            {"role": "system", "content": "You are the Chairman of an LLM Council. Your task is to synthesize the provided model responses into a single, comprehensive answer."},
            {"role": "user", "content": chairman_prompt}
        ]
    else:
        # If custom prompt, send as single User message to respect user's custom persona/structure
        messages = [{"role": "user", "content": chairman_prompt}]

    # Query the chairman model with error handling
    chairman_model = get_chairman_model()
    chairman_temp = settings.chairman_temperature

    try:
        response = await query_model(chairman_model, messages, temperature=chairman_temp)

        # Check for error in response
        if response is None or response.get('error'):
            error_msg = response.get('error_message', 'Unknown error') if response else 'No response received'
            return {
                "model": chairman_model,
                "response": f"Error synthesizing final answer: {error_msg}",
                "error": True,
                "error_message": error_msg
            }

        # Combine reasoning and content if available
        content = response.get('content') or ''
        reasoning = response.get('reasoning') or response.get('reasoning_details') or ''
        
        final_response = content
        if reasoning and not content:
            # If only reasoning is provided (some reasoning models do this)
            final_response = f"**Reasoning:**\n{reasoning}"
        elif reasoning and content:
            # If both are provided, prepend reasoning in a collapsible block or just prepend
            # For now, we'll just prepend it clearly
            final_response = f"<think>\n{reasoning}\n</think>\n\n{content}"

        if not final_response:
             final_response = "No response generated by the Chairman."

        return {
            "model": chairman_model,
            "response": final_response,
            "error": False
        }

    except Exception as e:
        logger.error(f"Unexpected error in Stage 3 synthesis: {e}")
        return {
            "model": chairman_model,
            "response": f"Error: Unable to generate final synthesis due to unexpected error.",
            "error": True,
            "error_message": str(e)
        }


def parse_ranking_from_text(ranking_text: str, expected_count: int = None) -> List[str]:
    """
    Parse the FINAL RANKING section from the model's response.

    Args:
        ranking_text: The full text response from the model
        expected_count: Optional number of expected ranked items (to truncate duplicates)

    Returns:
        List of response labels in ranked order
    """
    import re

    # Defensive: ensure ranking_text is a string
    if not isinstance(ranking_text, str):
        ranking_text = str(ranking_text) if ranking_text is not None else ''

    matches = []

    # Look for "FINAL RANKING:" section
    if "FINAL RANKING:" in ranking_text:
        # Extract everything after "FINAL RANKING:"
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            # Try to extract numbered list format (e.g., "1. Response A")
            # This pattern looks for: number, period, optional space, "Response X"
            numbered_matches = re.findall(r'\d+\.\s*Response [A-Z]', ranking_section)
            if numbered_matches:
                # Extract just the "Response X" part
                matches = [re.search(r'Response [A-Z]', m).group() for m in numbered_matches]
            else:
                # Fallback: Extract all "Response X" patterns in order from the section
                matches = re.findall(r'Response [A-Z]', ranking_section)
    
    # If no matches found in section (or section missing), fallback to full text search
    if not matches:
        matches = re.findall(r'Response [A-Z]', ranking_text)

    # Truncate if expected_count is provided
    if expected_count and len(matches) > expected_count:
        matches = matches[:expected_count]
        
    return matches


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Calculate aggregate rankings across all models.

    Args:
        stage2_results: Rankings from each model
        label_to_model: Mapping from anonymous labels to model names

    Returns:
        List of dicts with model name and average rank, sorted best to worst
    """
    from collections import defaultdict

    # Track positions for each model
    model_positions = defaultdict(list)

    for ranking in stage2_results:
        ranking_text = ranking['ranking']

        # Parse the ranking from the structured format
        expected_count = len(label_to_model)
        parsed_ranking = parse_ranking_from_text(ranking_text, expected_count=expected_count)

        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_model:
                model_name = label_to_model[label]
                model_positions[model_name].append(position)

    # Calculate average position for each model
    aggregate = []
    for model, positions in model_positions.items():
        if positions:
            avg_rank = sum(positions) / len(positions)
            aggregate.append({
                "model": model,
                "average_rank": round(avg_rank, 2),
                "rankings_count": len(positions)
            })

    # Sort by average rank (lower is better)
    aggregate.sort(key=lambda x: x['average_rank'])

    return aggregate


def _short_model_name(model_id: str) -> str:
    """Extract a short display name from a prefixed model ID."""
    if "/" in model_id:
        return model_id.split("/")[-1]
    if ":" in model_id:
        return model_id.split(":")[-1]
    return model_id


def _build_brainstorm_initial_text(stage1_results: List[Dict[str, Any]]) -> str:
    """Format Stage 1 results as named initial answers."""
    lines = []
    for r in stage1_results:
        if not r.get("error"):
            lines.append(f"[{_short_model_name(r['model'])}]: {r.get('response', '')}")
    return "\n\n".join(lines) if lines else "(No initial answers available)"


def _build_brainstorm_discussion_text(turns: List[Dict[str, Any]], recent_cycles: int = None) -> str:
    """Format discussion turns with cycle labels.

    If recent_cycles is set, only turns from the most recent N cycles are included.
    """
    if not turns:
        return "(No discussion yet — you are the first to respond)"
    if recent_cycles is not None:
        max_cycle = max(t["cycle"] for t in turns)
        cutoff = max_cycle - recent_cycles + 1
        turns = [t for t in turns if t["cycle"] >= cutoff]
    if not turns:
        return "(No discussion yet — you are the first to respond)"
    lines = []
    for t in turns:
        name = _short_model_name(t["model"])
        if t.get("error"):
            lines.append(f"[Cycle {t['cycle']}, {name}]: [Error: {t.get('error_message', 'Unknown error')}]")
        else:
            lines.append(f"[Cycle {t['cycle']}, {name}]: {t.get('content', '')}")
    return "\n\n".join(lines)


async def brainstorm_discussion(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    request: Any = None,
    get_user_input=None,
    get_final_decision=None,
) -> Any:
    """
    Brainstorm mode: round-robin discussion between council models until consensus.

    Yields dicts with a 'type' key:
      {'type': 'total',            'max_cycles': N, 'model_count': M}
      {'type': 'cycle_start',      'cycle': N}
      {'type': 'turn_start',       'model': str, 'cycle': N}
      {'type': 'turn_complete',    'model': str, 'content': str, 'cycle': N,
                                   'error': bool, 'error_message': str|None}
      {'type': 'summary_start',    'cycle': N}
      {'type': 'summary_complete', 'summary': str, 'consensus_reached': bool,
                                   'cycle': N, 'chairman_model': str}
      {'type': 'done',             'consensus_reached': bool, 'final_cycle': N,
                                   'reason': 'consensus'|'max_cycles'|'no_models'}
    """
    settings = get_settings()
    successful = [r for r in stage1_results if not r.get("error")]
    models = [r["model"] for r in successful]
    max_cycles = settings.brainstorm_max_cycles

    if not models:
        yield {"type": "done", "consensus_reached": False, "final_cycle": 0, "reason": "no_models"}
        return

    yield {"type": "total", "max_cycles": max_cycles, "model_count": len(models)}

    turns: List[Dict[str, Any]] = []
    local_summaries: List[Dict[str, Any]] = []
    initial_text = _build_brainstorm_initial_text(successful)
    pending_user_input: str = ""

    cycle = 0
    consensus = False
    while cycle < max_cycles:
        cycle += 1
        yield {"type": "cycle_start", "cycle": cycle}

        # Consume any pending user steering input at the start of each cycle
        cycle_user_input = pending_user_input
        pending_user_input = ""

        for model in models:
            if request:
                try:
                    if await request.is_disconnected():
                        return
                except Exception:
                    pass

            yield {"type": "turn_start", "model": model, "cycle": cycle}

            # Only pass the previous cycle's turns to keep prompts compact
            discussion_text = _build_brainstorm_discussion_text(turns, recent_cycles=1)
            try:
                prompt = settings.brainstorm_turn_prompt.format(
                    user_query=user_query,
                    initial_answers=initial_text,
                    discussion_history=discussion_text,
                    model_name=_short_model_name(model),
                    cycle=cycle,
                )
            except (KeyError, ValueError) as e:
                logger.warning(f"Error formatting brainstorm turn prompt: {e}")
                prompt = f"Topic: {user_query}\n\nDiscussion so far:\n{discussion_text}\n\nYou are {_short_model_name(model)}. Contribute your perspective."

            if cycle_user_input:
                prompt += f"\n\n---\n**USER STEERING (address this in your response):**\n{cycle_user_input}"

            result = await query_model(
                model,
                [{"role": "user", "content": prompt}],
                temperature=settings.council_temperature,
            )

            content = result.get("content", "")
            if not isinstance(content, str):
                content = str(content) if content else ""

            turn = {
                "model": model,
                "content": content,
                "cycle": cycle,
                "error": result.get("error", False),
                "error_message": result.get("error_message") if result.get("error") else None,
            }
            turns.append(turn)
            yield {"type": "turn_complete", **turn}

        # Chairman summarizes every 2 cycles and at the final cycle
        if cycle % 2 == 0 or cycle == max_cycles:
            if request:
                try:
                    if await request.is_disconnected():
                        return
                except Exception:
                    pass

            yield {"type": "summary_start", "cycle": cycle}

            # Previous summaries replace the full history; only current cycle's turns are sent in full
            previous_summaries_text = "\n\n".join(
                f"[After cycle {s['cycle']}]: {s['summary']}"
                for s in local_summaries
            ) or "(No previous summaries)"
            recent_discussion = _build_brainstorm_discussion_text(turns, recent_cycles=1)

            try:
                summary_prompt = settings.brainstorm_summary_prompt.format(
                    user_query=user_query,
                    initial_answers=initial_text,
                    previous_summaries=previous_summaries_text,
                    recent_discussion=recent_discussion,
                    cycle=cycle,
                )
            except (KeyError, ValueError) as e:
                logger.warning(f"Error formatting brainstorm summary prompt: {e}")
                summary_prompt = f"Topic: {user_query}\n\nSummarize the discussion. End with CONSENSUS: YES or CONSENSUS: NO."

            if cycle_user_input:
                summary_prompt += f"\n\n---\n**USER STEERING INPUT (given before this cycle):**\n{cycle_user_input}"

            chairman = get_chairman_model()
            result = await query_model(
                chairman,
                [{"role": "user", "content": summary_prompt}],
                temperature=settings.chairman_temperature,
            )

            summary_text = result.get("content", "")
            if not isinstance(summary_text, str):
                summary_text = str(summary_text) if summary_text else ""

            consensus = "CONSENSUS: YES" in summary_text.upper()

            summary_entry = {"cycle": cycle, "summary": summary_text}
            local_summaries.append(summary_entry)

            yield {
                "type": "summary_complete",
                "summary": summary_text,
                "consensus_reached": consensus,
                "cycle": cycle,
                "chairman_model": chairman,
            }

            if consensus:
                yield {"type": "done", "consensus_reached": True, "final_cycle": cycle, "reason": "consensus"}
                return

            if cycle == max_cycles and not consensus:
                # Ask user whether to extend or finalize
                if get_final_decision:
                    yield {"type": "await_final_decision", "final_cycle": cycle}
                    decision = await get_final_decision()
                    if decision == "extend":
                        max_cycles += 2
                        yield {"type": "cycles_extended", "new_max_cycles": max_cycles}
                        # Give user a chance to steer before the extended cycles start
                        if get_user_input:
                            yield {"type": "await_user_input", "cycle": cycle}
                            user_input = await get_user_input(cycle)
                            if user_input:
                                pending_user_input = user_input
                                yield {"type": "user_input_received", "input": user_input, "cycle": cycle}
                        continue  # loop continues for 2 more cycles
                    else:
                        break  # finalize immediately
                # else fall through to end of loop

            # Pause for user steering after each non-final, non-consensus chairman summary.
            # The backend always pauses; frontend auto-skips if steering checkbox is unchecked.
            elif get_user_input and cycle < max_cycles:
                yield {"type": "await_user_input", "cycle": cycle}
                user_input = await get_user_input(cycle)
                if user_input:
                    pending_user_input = user_input
                    yield {"type": "user_input_received", "input": user_input, "cycle": cycle}

    yield {"type": "done", "consensus_reached": False, "final_cycle": cycle, "reason": "max_cycles"}


async def brainstorm_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    turns: List[Dict[str, Any]],
    summaries: List[Dict[str, Any]],
    reason: str = "max_cycles",
    user_inputs: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Chairman drafts the definitive final statement after a brainstorm discussion."""
    settings = get_settings()
    initial_text = _build_brainstorm_initial_text(stage1_results)
    discussion_text = _build_brainstorm_discussion_text(turns)

    summaries_text = "\n\n".join(
        f"[After cycle {s['cycle']}]: {s.get('summary', '')}"
        for s in summaries
    ) or "(No summaries)"

    reason_label = "consensus reached" if reason == "consensus" else "maximum discussion cycles reached"

    try:
        prompt = settings.brainstorm_final_prompt.format(
            user_query=user_query,
            initial_answers=initial_text,
            discussion_history=discussion_text,
            summaries_text=summaries_text,
            reason=reason_label,
        )
    except (KeyError, ValueError) as e:
        logger.warning(f"Error formatting brainstorm final prompt: {e}")
        prompt = f"Topic: {user_query}\n\n{discussion_text}\n\nDraft a final recommendation."

    if user_inputs:
        steering_lines = "\n".join(
            f"[After cycle {entry['cycle']}]: {entry['input']}"
            for entry in user_inputs
        )
        prompt += f"\n\nUSER STEERING INPUTS DURING DISCUSSION:\n{steering_lines}"

    chairman = get_chairman_model()
    try:
        result = await query_model(
            chairman,
            [{"role": "user", "content": prompt}],
            temperature=settings.chairman_temperature,
        )
        if result.get("error"):
            return {"model": chairman, "response": f"Error: {result.get('error_message', 'Unknown error')}", "error": True}

        content = result.get("content", "") or ""
        if not isinstance(content, str):
            content = str(content)
        return {"model": chairman, "response": content, "error": False}
    except Exception as e:
        logger.error(f"Error in brainstorm final synthesis: {e}")
        return {"model": chairman, "response": f"Error generating final statement: {e}", "error": True}


async def chairman_followup(
    user_message: str,
    brainstorm_context: Dict[str, Any],
    chat_history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Chairman responds to a follow-up question with full brainstorm context."""
    settings = get_settings()
    chairman = get_chairman_model()

    final_response = brainstorm_context.get("final_response", "")
    user_query = brainstorm_context.get("user_query", "")
    summaries = brainstorm_context.get("summaries", [])

    summaries_text = "\n\n".join(
        f"[After cycle {s['cycle']}]: {s.get('summary', '')}"
        for s in summaries
    ) or "(No summaries available)"

    system_prompt = (
        f"You are the Chairman of an LLM Council. You previously led a multi-model brainstorm discussion "
        f"on the following topic and issued a final statement. A user is now asking you a follow-up question.\n\n"
        f"ORIGINAL TOPIC: {user_query}\n\n"
        f"DISCUSSION SUMMARIES:\n{summaries_text}\n\n"
        f"YOUR FINAL STATEMENT:\n{final_response}\n\n"
        f"Answer the follow-up question thoughtfully, drawing on the full context of the discussion above."
    )

    messages = [{"role": "system", "content": system_prompt}]
    for entry in chat_history:
        role = "assistant" if entry.get("role") == "chairman" else "user"
        messages.append({"role": role, "content": entry.get("content", "")})
    messages.append({"role": "user", "content": user_message})

    try:
        result = await query_model(chairman, messages, temperature=settings.chairman_temperature)
        if result.get("error"):
            return {"model": chairman, "response": f"Error: {result.get('error_message', 'Unknown error')}", "error": True}
        content = result.get("content", "") or ""
        if not isinstance(content, str):
            content = str(content)
        return {"model": chairman, "response": content, "error": False}
    except Exception as e:
        logger.error(f"Error in chairman followup: {e}")
        return {"model": chairman, "response": f"Error generating response: {e}", "error": True}


async def generate_conversation_title(user_query: str) -> str:
    """
    Generate a short title for a conversation based on the first user message.

    Uses a simple heuristic (first few words) to avoid unnecessary API calls.

    Args:
        user_query: The first user message

    Returns:
        A short title (max 50 chars)
    """
    # Validate input
    if not user_query or not isinstance(user_query, str):
        return "Untitled Conversation"

    # Simple heuristic: take first 50 chars
    title = user_query.strip()

    # If empty after stripping, return default
    if not title:
        return "Untitled Conversation"

    # Remove quotes if present
    title = title.strip('"\'')

    # Truncate if too long
    if len(title) > 50:
        title = title[:47] + "..."

    return title


def generate_search_query(user_query: str) -> str:
    """Return user query directly for web search (passthrough).
    
    Modern search engines (DuckDuckGo, Brave, Tavily) handle 
    natural language queries well without optimization.
    
    Args:
        user_query: The user's full question
    
    Returns:
        User query truncated to 100 characters for safety
    """
    return user_query[:100]  # Truncate for safety
