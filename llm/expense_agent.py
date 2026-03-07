import os
from agents import Agent, Runner

from dotenv import load_dotenv
from llm.agents import welcomeAgents, classifyExpenseAgent
from llm.agents.config import APPLICATION_INSTRUCTION, MODEL_NAME

load_dotenv(override=True)
ENV = os.environ.get("ENV", "")

# ---------------------------------------------------------------------------
# Application Agent (router: handoffs to Welcome and ClassifyExpense)
# ---------------------------------------------------------------------------

applicationAgentInst = (
    f"Router. Use handoff tools only. Do not answer in place of agents. Scope: {APPLICATION_INSTRUCTION}\n"
    "Greeting (hi, hello) → Welcome Agent. Expense (spent X on Y) → Classify Expense Agent. "
    "Out-of-scope → one short line: this app is for expenses; I can greet or log expenses."
)

applicationAgent = Agent(
    name="Application Agent",
    instructions=applicationAgentInst,
    model=MODEL_NAME,
    handoffs=[welcomeAgents, classifyExpenseAgent],
)


async def run_application_agent(user_message: str, profile_name: str = ""):
    """Run applicationAgent; returns Runner result. Prepends profile name and current date for LLM context."""
    from datetime import datetime
    today = datetime.utcnow().strftime("%Y-%m-%d")
    parts = [f"Current date: {today}"]
    if profile_name and profile_name.strip():
        parts.append(f"Profile name: {profile_name.strip()}")
    parts.append(f"User: {user_message}")
    input_with_context = "\n\n".join(parts)
    return await Runner.run(applicationAgent, input_with_context)


def get_response_text(runner) -> str:
    """Return only the final output string from RunResult for WhatsApp (no RunResult repr)."""
    if runner is None:
        return ""
    out = getattr(runner, "final_output", None)
    if out is not None:
        return out if isinstance(out, str) else str(out)
    if hasattr(runner, "final_output") and callable(runner.final_output):
        out = runner.final_output()
        if out is not None:
            return out if isinstance(out, str) else str(out)
    return ""


# ---------------------------------------------------------------------------
# Development: run agents directly (ENV=development)
# ---------------------------------------------------------------------------
if __name__ == "__main__" and ENV == "development":
    import asyncio
    _sample = os.environ.get(
        "DEV_MESSAGE",
        "Today i really spend too much amount which 1800 for shopping itself and 700 for food and then finally 200 for bus far",
    )
    _runner = asyncio.run(run_application_agent(_sample))
    _response = get_response_text(_runner)
    print("--- response ---")
    print(_response if _response else _runner)
