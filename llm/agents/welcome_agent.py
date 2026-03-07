"""Welcome agent: greetings and app-relevant entry guardrail."""

from agents import Agent, InputGuardrail, Runner, GuardrailFunctionOutput
from pydantic import BaseModel

from llm.agents.config import APPLICATION_INSTRUCTION, MODEL_NAME

# ---------------------------------------------------------------------------
# Welcome Agent
# ---------------------------------------------------------------------------

WELCOME_AGENT_NAME = "Welcome Agent"
WELCOME_AGENT_INSTRUCTIONS = (
    "You are a warm, natural person helping with a monthly expense app—not a generic bot.\n"
    "- When the user says hi/hello, reply as a real person would: friendly, varied, and slightly playful.\n"
    "- If a profile name is provided in the input (e.g. 'Profile name: John'), use it naturally in your reply (e.g. 'Hey John!', 'Hi there, John!')\n"
    "- Every reply must feel unique: vary your opening (Hey / Hi / Hello there / Hey there), wording, and tone. Never repeat the same phrase.\n"
    "- Add 1–2 reaction emojis in the mix (e.g. 👋 😊 🙌 ✨ 👍), different each time—never the same set.\n"
    "- Keep it short (1–2 sentences). Out-of-scope (weather, off-topic) → block. Scope: " + APPLICATION_INSTRUCTION
)


class WelcomeAgentOutputFormat(BaseModel):
    is_application_entry: bool
    welcome_msg: str


WELCOME_GUARDRAIL_INSTRUCTIONS = (
    "Decide: is this message an app-relevant entry (greeting/expense)? "
    "Output: is_application_entry (bool), welcome_msg (str). "
    "If off-topic (e.g. weather) → is_application_entry=false, welcome_msg=short polite reason."
)


welcomeInputGuardrailsAgent = Agent(
    name="Welcome guardrail: app-relevant entry?",
    instructions=WELCOME_GUARDRAIL_INSTRUCTIONS,
    model=MODEL_NAME,
)


async def welcomeInputGuardrails(ctx, agent, input_data):
    welcome_res = await Runner.run(welcomeInputGuardrailsAgent, input_data, context=ctx)
    response = welcome_res.final_output_as(WelcomeAgentOutputFormat)
    block = not response.is_application_entry
    return GuardrailFunctionOutput(output_info=response, tripwire_triggered=block)


welcomeAgents = Agent(
    name=WELCOME_AGENT_NAME,
    instructions=WELCOME_AGENT_INSTRUCTIONS,
    model=MODEL_NAME,
    input_guardrails=[InputGuardrail(guardrail_function=welcomeInputGuardrails)],
    handoff_description="Greeting/welcome (hi, hello).",
)
