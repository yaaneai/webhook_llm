"""Classify expense agent: extract amount, date, purpose and reply in user-friendly format."""

from agents import Agent, InputGuardrail, Runner, GuardrailFunctionOutput
from pydantic import BaseModel

from llm.agents.config import APPLICATION_INSTRUCTION, MODEL_NAME

# ---------------------------------------------------------------------------
# Classify Expense Agent
# ---------------------------------------------------------------------------

CLASSIFY_EXPENSE_AGENT_NAME = "Classify Expense Agent"
CLASSIFY_EXPENSE_AGENT_INSTRUCTIONS = (
    f"Expense agent. Extract amount (number), date (YYYY-MM-DD), purpose (one word). Scope: {APPLICATION_INSTRUCTION}\n"
    "Date: use 'Current date: YYYY-MM-DD' in context for today; yesterday = previous day. Never invent date.\n\n"
    "Your reply to the user must be user-friendly and in two parts:\n"
    "1. First, write one or two short, natural sentences acknowledging their expense (e.g. 'Got it, I've noted that.', 'Recorded! Here's what I saved.', 'Done! Here's the summary.'). Vary the wording each time.\n"
    "2. Then show the spending as a clear list. Use exactly this format (WhatsApp bold is *text*):\n"
    "   • Amount: *<value>*\n"
    "   • Date: *<YYYY-MM-DD>*\n"
    "   • Purpose: *<value>*\n"
    "Output this full message as your reply—no raw key=value lines. Example for '300 for snacks today': "
    "'Got it, I've noted that. 👍 Here's what I saved:\n• Amount: *300*\n• Date: *2026-02-15*\n• Purpose: *snacks*'"
)


class ClassifyExpenseAgentOutputFormat(BaseModel):
    amount: float
    date: str  # YYYY-MM-DD
    purpose: str


class ClassifyExpenseGuardrailOutputFormat(BaseModel):
    is_expense_entry: bool
    reason: str = ""


CLASSIFY_EXPENSE_GUARDRAIL_INSTRUCTIONS = (
    "Is this expense logging (user says they spent money + on what)? "
    "Output: is_expense_entry (bool), reason (str). Greeting/weather/other → false."
)


classifyExpenseInputGuardrailsAgent = Agent(
    name="Expense guardrail: expense entry?",
    instructions=CLASSIFY_EXPENSE_GUARDRAIL_INSTRUCTIONS,
    model=MODEL_NAME,
)


async def classifyExpenseInputGuardrails(ctx, agent, input_data):
    res = await Runner.run(classifyExpenseInputGuardrailsAgent, input_data, context=ctx)
    out = res.final_output_as(ClassifyExpenseGuardrailOutputFormat)
    block = not out.is_expense_entry
    return GuardrailFunctionOutput(output_info=out, tripwire_triggered=block)


classifyExpenseAgent = Agent(
    name=CLASSIFY_EXPENSE_AGENT_NAME,
    instructions=CLASSIFY_EXPENSE_AGENT_INSTRUCTIONS,
    model=MODEL_NAME,
    input_guardrails=[InputGuardrail(guardrail_function=classifyExpenseInputGuardrails)],
    handoff_description="User logs expense: spent X on Y, bought Z.",
)
