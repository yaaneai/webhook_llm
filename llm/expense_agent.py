import os
from agents import Agent, InputGuardrail, Runner, GuardrailFunctionOutput
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv(override=True)
ENV = os.environ.get("ENV", "")

# ---------------------------------------------------------------------------
# Application scope (shared – keep short for WhatsApp latency)
# ---------------------------------------------------------------------------

applicationInstruction = "Monthly expense app. User logs spends; you extract amount, date, purpose. Stay in scope."

# ---------------------------------------------------------------------------
# Welcome Agent
# ---------------------------------------------------------------------------

welcomeAgentsName = "Welcome Agent"
welcomeAgentsInst = (
    "You are a warm, natural person helping with a monthly expense app—not a generic bot.\n"
    "- When the user says hi/hello, reply as a real person would: friendly, varied, and slightly playful.\n"
    "- If a profile name is provided in the input (e.g. 'Profile name: John'), use it naturally in your reply (e.g. 'Hey John!', 'Hi there, John!')\n"
    "- Every reply must feel unique: vary your opening (Hey / Hi / Hello there / Hey there), wording, and tone. Never repeat the same phrase.\n"
    "- Add 1–2 reaction emojis in the mix (e.g. 👋 😊 🙌 ✨ 👍), different each time—never the same set.\n"
    "- Keep it short (1–2 sentences). Out-of-scope (weather, off-topic) → block. Scope: " + applicationInstruction
)


class welcomeAgentOutputFormat(BaseModel):
    is_application_entry: bool
    welcome_msg: str


welcomeAgentsInputGuardrailsInst = (
    "Decide: is this message an app-relevant entry (greeting/expense)? "
    "Output: is_application_entry (bool), welcome_msg (str). "
    "If off-topic (e.g. weather) → is_application_entry=false, welcome_msg=short polite reason."
)


welcomeInputGuardrailsAgent = Agent(
    name="Welcome guardrail: app-relevant entry?",
    instructions=welcomeAgentsInputGuardrailsInst,
    model="gpt-4o-mini",
)

async def welcomeInputGuardrails(ctx, agent, input_data):
    welcome_res = await Runner.run(welcomeInputGuardrailsAgent, input_data, context=ctx)
    response = welcome_res.final_output_as(welcomeAgentOutputFormat)
    block = not response.is_application_entry
    return GuardrailFunctionOutput(output_info=response, tripwire_triggered=block)


welcomeAgents = Agent(
    name=welcomeAgentsName,
    instructions=welcomeAgentsInst,
    model="gpt-4o-mini",
    input_guardrails=[InputGuardrail(guardrail_function=welcomeInputGuardrails)],
    handoff_description="Greeting/welcome (hi, hello).",
)

# ---------------------------------------------------------------------------
# Classify Expense Agent
# ---------------------------------------------------------------------------

classifyExpenseAgentsName = "Classify Expense Agent"
classifyExpenseAgentsInst = (
    f"Expense agent. Extract amount (number), date (YYYY-MM-DD), purpose (one word). Scope: {applicationInstruction}\n"
    "Date: use 'Current date: YYYY-MM-DD' in context for today; yesterday = previous day. Never invent date.\n\n"
    "Your reply to the user must be user-friendly and in two parts:\n"
    "1. First, write one or two short, natural sentences acknowledging their expense (e.g. 'Got it, I've noted that.', 'Recorded! Here’s what I saved.', 'Done! Here’s the summary.'). Vary the wording each time.\n"
    "2. Then show the spending as a clear list. Use exactly this format (WhatsApp bold is *text*):\n"
    "   • Amount: *<value>*\n"
    "   • Date: *<YYYY-MM-DD>*\n"
    "   • Purpose: *<value>*\n"
    "Output this full message as your reply—no raw key=value lines. Example for '300 for snacks today': "
    "'Got it, I've noted that. 👍 Here’s what I saved:\n• Amount: *300*\n• Date: *2026-02-15*\n• Purpose: *snacks*'"
)


class ClassifyExpenseAgentOutputFormat(BaseModel):
    amount: float
    date: str  # YYYY-MM-DD
    purpose: str


class ClassifyExpenseGuardrailOutputFormat(BaseModel):
    is_expense_entry: bool
    reason: str = ""


classifyExpenseInputGuardrailsInst = (
    "Is this expense logging (user says they spent money + on what)? "
    "Output: is_expense_entry (bool), reason (str). Greeting/weather/other → false."
)


classifyExpenseInputGuardrailsAgent = Agent(
    name="Expense guardrail: expense entry?",
    instructions=classifyExpenseInputGuardrailsInst,
    model="gpt-4o-mini",
)


async def classifyExpenseInputGuardrails(ctx, agent, input_data):
    res = await Runner.run(classifyExpenseInputGuardrailsAgent, input_data, context=ctx)
    out = res.final_output_as(ClassifyExpenseGuardrailOutputFormat)
    block = not out.is_expense_entry
    return GuardrailFunctionOutput(output_info=out, tripwire_triggered=block)


classifyExpenseAgent = Agent(
    name=classifyExpenseAgentsName,
    instructions=classifyExpenseAgentsInst,
    model="gpt-4o-mini",
    input_guardrails=[InputGuardrail(guardrail_function=classifyExpenseInputGuardrails)],
    handoff_description="User logs expense: spent X on Y, bought Z.",
)

# ---------------------------------------------------------------------------
# Application Agent (router: handoffs to Welcome and ClassifyExpense)
# ---------------------------------------------------------------------------

applicationAgentInst = (
    f"Router. Use handoff tools only. Do not answer in place of agents. Scope: {applicationInstruction}\n"
    "Greeting (hi, hello) → Welcome Agent. Expense (spent X on Y) → Classify Expense Agent. "
    "Out-of-scope → one short line: this app is for expenses; I can greet or log expenses."
)

applicationAgent = Agent(
    name="Application Agent",
    instructions=applicationAgentInst,
    model="gpt-4o-mini",
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
    # RunResult.final_output is the last agent's output (str or custom type)
    out = getattr(runner, "final_output", None)
    if out is not None:
        return out if isinstance(out, str) else str(out)
    # Fallback: try final_output() as method (older API)
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
    _sample = os.environ.get("DEV_MESSAGE", "Today i really spend too much amount which 1800 for shopping itself and 700 for food and then finally 200 for bus far")
    _runner = asyncio.run(run_application_agent(_sample))
    _response = get_response_text(_runner)
    print("--- response ---")
    print(_response if _response else _runner)

# ---------------------------------------------------------------------------
# Usage note (for main.py / webhook flow)
# When calling Runner.run(applicationAgent, user_message), prepend the current date
# so ClassifyExpenseAgent can resolve "today" / "yesterday":
#   from datetime import datetime
#   today = datetime.utcnow().strftime("%Y-%m-%d")
#   input_with_date = f"Current date: {today}\n\nUser: {user_message}"
#   runner = await Runner.run(applicationAgent, input_with_date)
# Then use runner.final_output_as(...) depending on which agent responded.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Possible improvements (code & architecture)
# ---------------------------------------------------------------------------
# 1. Central config: move model name ("gpt-4o-mini"), app instruction, and any
#    magic strings to a small config module or env so you can change without
#    editing agents.py.
# 2. RECOMMENDED_PROMPT_PREFIX: use agents.extensions.handoff_prompt to add
#    recommended handoff instructions to Application Agent for more reliable routing.
# 3. Structured runner result: after Runner.run(applicationAgent, ...), the
#    final output shape depends on which agent handled the turn. You can check
#    runner context/events to see which agent replied and then parse as
#    welcomeAgentOutputFormat or ClassifyExpenseAgentOutputFormat accordingly.
# 4. Out-of-scope agent: add a third agent (e.g. "OutOfScopeAgent") that only
#    replies with a polite "this app is for expenses only" and hand off to it
#    from Application Agent instead of inlining that reply in the router.
# 5. Tests: add unit tests that run each agent with fixed inputs (e.g. expense
#    message, welcome message) and assert on output schema and key fields.
# 6. Date in handoff: use handoff(..., input_filter=...) to inject "Current date"
#    into the payload when handing off to ClassifyExpenseAgent so the router
#    caller does not need to prepend it to every message.


