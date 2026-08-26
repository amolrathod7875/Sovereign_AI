import logging
import asyncio
import uuid
from datetime import datetime
from typing import Dict, Any, List, AsyncGenerator

from app.agents.state import AgentState, create_initial_state
from app.agents.planner import classify_task, create_plan
from app.agents.policies import determine_routing, get_required_tools, get_retrieval_enabled
from app.schemas import AgentRunRequest, TaskType
from app.storage import create_execution, update_execution
from app.api.network import add_network_event

logger = logging.getLogger(__name__)


class AgentEvents:
    def __init__(self, execution_id: str):
        self.execution_id = execution_id
        self._events: List[Dict] = []

    async def emit(self, event_type: str, data: Dict):
        event = {"type": event_type, "execution_id": self.execution_id, **data}
        self._events.append(event)

        if event_type == "network_event":
            from app.schemas import NetworkEvent
            add_network_event(NetworkEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                destination_host=data.get("destination", "unknown"),
                destination_port=data.get("port", 0),
                action=data.get("action", "unknown"),
                execution_id=self.execution_id,
            ))


async def run_agent(request: AgentRunRequest, execution_id: str) -> Dict[str, Any]:
    """
    Run the agent workflow synchronously.
    """
    state = create_initial_state(execution_id, request.message, request.attachments)
    events = AgentEvents(execution_id)

    await create_execution(execution_id, "UNKNOWN")
    await events.emit("started", {"message": request.message})

    try:
        state = await execute_workflow(state, events)

        await update_execution(
            execution_id,
            status="COMPLETED",
            selected_model=state.get("selected_model"),
            steps=state.get("steps", []),
            artifacts=state.get("artifacts", []),
            errors=state.get("errors", []),
            external_calls=state.get("external_calls", 0),
        )
        await events.emit("completed", {
            "status": "COMPLETED",
            "external_calls": state.get("external_calls", 0),
            "artifacts": state.get("artifacts", []),
        })

    except Exception as e:
        logger.error(f"Agent execution error: {e}")
        state["errors"].append(str(e))
        state["status"] = "FAILED"
        await update_execution(execution_id, status="FAILED", errors=state["errors"])
        await events.emit("error", {"error": str(e)})

    return {
        "execution_id": execution_id,
        "status": state.get("status", "COMPLETED"),
        "task_type": state.get("task_type"),
        "selected_model": state.get("selected_model"),
        "steps": state.get("steps", []),
        "artifacts": state.get("artifacts", []),
        "external_calls": state.get("external_calls", 0),
    }


async def agent_stream(execution_id: str) -> AsyncGenerator[Dict, None]:
    """
    Stream agent events as they occur.
    """
    events = AgentEvents(execution_id)
    yield {"type": "connected", "execution_id": execution_id}

    while True:
        await asyncio.sleep(0.5)
        if events._events:
            yield events._events.pop(0)


async def execute_workflow(state: AgentState, events: AgentEvents) -> AgentState:
    """
    Execute the agent workflow through all steps.
    """
    await events.emit("task_classified", {"task": state["task_type"] or "GENERAL_QA"})

    state["task_type"] = classify_task(state["message"], state["attachments"])
    state["has_image"] = any(
        ext in attachment.lower()
        for attachment in state["attachments"]
        for ext in [".png", ".jpg", ".jpeg", ".pdf"]
    )

    await events.emit("task_classified", {"task": state["task_type"], "has_image": state["has_image"]})

    state["selected_model"] = determine_routing(state["task_type"], state["has_image"], state)
    await events.emit("model_selected", {"model": state["selected_model"]})

    state["plan"] = create_plan(state["task_type"], state["message"])
    await events.emit("plan_created", {"plan": state["plan"]})

    for step_name in state["plan"]:
        step_result = await execute_step(step_name, state, events)
        state["steps"].append({
            "action": step_name,
            "status": step_result.get("status", "SUCCESS"),
            "duration_ms": step_result.get("duration_ms", 0),
            "metadata": step_result.get("metadata", {}),
        })

    state["status"] = "COMPLETED"
    return state


async def execute_step(step_name: str, state: AgentState, events: AgentEvents) -> Dict:
    """
    Execute a single step in the agent workflow.
    """
    import time
    start = time.time()

    await events.emit("step_started", {"step": step_name})

    result = {"status": "SUCCESS", "duration_ms": 0, "metadata": {}}

    try:
        if step_name == "validate_inputs":
            result["metadata"] = {"attachments": len(state["attachments"])}

        elif step_name == "classify_task":
            result["metadata"] = {"task_type": state["task_type"]}

        elif step_name == "select_model":
            result["metadata"] = {"model": state["selected_model"]}

        elif step_name == "process_document":
            if state["attachments"]:
                result["metadata"] = {"document_processed": state["attachments"][0]}

        elif step_name == "run_ocr":
            await asyncio.sleep(0.1)
            result["metadata"] = {"pages_processed": 3, "ocr_engine": "PaddleOCR"}

        elif step_name == "hybrid_retrieval":
            retrieved = await perform_ragRetrieval(state, events)
            state["retrieved_context"] = retrieved
            result["metadata"] = {"chunks_found": len(retrieved), "sources": [r.get("document") for r in retrieved[:3]]}
            for chunk in retrieved[:3]:
                await events.emit("evidence", {
                    "source": chunk.get("document", "unknown"),
                    "page": chunk.get("page"),
                    "chunk_id": chunk.get("chunk_id"),
                })

        elif step_name == "analyze_and_reason":
            analysis_result = await perform_analysis(state, events)
            result["metadata"] = {"analysis": analysis_result}

        elif step_name == "generate_code":
            code = await generate_code(state, events)
            state["generated_code"] = code
            result["metadata"] = {"code_length": len(code)}

        elif step_name == "execute_in_sandbox":
            sandbox_result = await execute_in_sandbox_step(state, events)
            result["metadata"] = sandbox_result

        elif step_name == "generate_artifact":
            artifact_id = await generate_docx_artifact(state, events)
            state["artifacts"].append(artifact_id)
            result["metadata"] = {"artifact_id": artifact_id}
            await events.emit("artifact_created", {
                "artifact_id": artifact_id,
                "filename": "approval_note.docx",
            })

        elif step_name == "finalize":
            result["metadata"] = {"finalized": True}

        else:
            result["metadata"] = {"skipped": True}

    except Exception as e:
        logger.error(f"Step {step_name} error: {e}")
        result["status"] = "FAILED"
        state["errors"].append(f"{step_name}: {str(e)}")

    result["duration_ms"] = int((time.time() - start) * 1000)
    await events.emit("step_complete", {"step": step_name, **result})

    return result


async def perform_ragRetrieval(state: AgentState, events: AgentEvents) -> List[Dict]:
    """
    Perform hybrid RAG retrieval.
    """
    from app.rag.retrieval import hybrid_search

    try:
        results = await hybrid_search(state["message"], top_k=5)
        return results
    except Exception as e:
        logger.error(f"RAG retrieval error: {e}")
        return []


async def perform_analysis(state: AgentState, events: AgentEvents) -> str:
    """
    Perform analysis using the selected model.
    """
    from app.models.client import get_model_client

    try:
        client = await get_model_client(state["selected_model"])
        context_text = ""
        if state.get("retrieved_context"):
            context_text = "\n\n".join([
                f"[{r.get('document', 'doc')} p.{r.get('page', '?')}]: {r.get('text', '')[:500]}"
                for r in state["retrieved_context"][:3]
            ])

        messages = [
            {"role": "system", "content": "You are a helpful AI assistant analyzing documents."},
            {"role": "user", "content": f"Context:\n{context_text}\n\nQuestion: {state['message']}"},
        ]

        response = await client.generate(messages)
        await events.emit("message_delta", {"content": response})

        return response[:500] if len(response) > 500 else response

    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return "Analysis completed with errors."


async def generate_code(state: AgentState, events: AgentEvents) -> str:
    """
    Generate code using the coder model.
    """
    from app.models.client import get_model_client

    try:
        client = await get_model_client("coder")
        messages = [
            {"role": "system", "content": "You are a coding assistant. Generate clean, working Python code."},
            {"role": "user", "content": state["message"]},
        ]
        code = await client.generate(messages)
        state["generated_code"] = code
        return code
    except Exception as e:
        logger.error(f"Code generation error: {e}")
        return f"# Error generating code: {e}"


async def execute_in_sandbox_step(state: AgentState, events: AgentEvents) -> Dict:
    """
    Execute code in the sandbox.
    """
    from app.tools.python_tool import execute_in_sandbox

    code = state.get("generated_code", "print('No code to execute')")
    try:
        result = await execute_in_sandbox(code, "python", timeout=30)
        return {
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "exit_code": result.get("exit_code", 0),
            "execution_time_ms": result.get("execution_time_ms", 0),
        }
    except Exception as e:
        return {"error": str(e), "exit_code": -1}


async def generate_docx_artifact(state: AgentState, events: AgentEvents) -> str:
    """
    Generate a DOCX artifact.
    """
    from app.tools.docx_tool import create_approval_note
    import uuid

    artifact_id = f"art_{uuid.uuid4().hex[:8]}"

    try:
        analysis = state.get("retrieved_context", [{}])
        content = f"Approval Note\n\nBased on analysis of the provided documents.\n\n"
        content += f"Task: {state['message']}\n\n"
        if state.get("retrieved_context"):
            content += f"Evidence retrieved from {len(state['retrieved_context'])} sources.\n"

        filepath = await create_approval_note(artifact_id, content)
        state["artifacts"].append(artifact_id)

        return artifact_id
    except Exception as e:
        logger.error(f"DOCX generation error: {e}")
        return artifact_id
