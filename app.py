from agents import Agent, Runner, InputGuardrail, GuardrailFunctionOutput, InputGuardrailTripwireTriggered
from dotenv import load_dotenv
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn


load_dotenv(override=True)

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Visitor Registration API",
    description="Accepts a message, validates visitor intent and required fields, returns structured visitor data or user-friendly errors.",
    version="1.0.0",
)


class VisitorRequest(BaseModel):
    """Payload from another dev: the raw message to process."""

    message: str = Field(..., description="User message to classify as visitor registration and extract fields from.")


class VisitorSuccessResponse(BaseModel):
    """200: Valid visitor input, all required fields present. Same shape as VisitorChatOutputFormat."""

    name: str
    mobile_no: str
    purpose: str
    whom_to_meet: str
    vehicle_number: str


class VisitorNotRelevantResponse(BaseModel):
    """400: Input is not a visitor registration request."""

    message: str = Field(..., description="User-friendly explanation that the input is not a visitor entry.")


class VisitorMissingFieldsResponse(BaseModel):
    """422: Visitor input but one or more required fields are missing."""

    message: str = Field(..., description="User-friendly explanation that some required fields are missing.")
    missing_required_fields: list[str] = Field(..., description="Exact field names that are missing (e.g. mobile_no, vehicle_number).")


class VisitorChatOutputFormat(BaseModel):
    name:str
    mobile_no:str
    purpose: str
    whom_to_meet:str
    vehicle_number:str


class VisitorGuardrailsOutputFormat(BaseModel):
    is_visitor_entry: bool
    missing_required_fields: list[str]  # e.g. ["mobile_no", "vehicle_number"]



async def VisitorInputGuardrails(ctx,agent,input_data):
    # print(ctx,"context")
    # print(input_data,"Input Data")
    # print(agent,"agent")
    runner = await Runner.run(input_guardrail_agent,input_data, context = ctx.context)
    final_output = runner.final_output_as(VisitorGuardrailsOutputFormat)
    print(final_output,"final_output")
    block = not final_output.is_visitor_entry or len(final_output.missing_required_fields) > 0
    return GuardrailFunctionOutput(
        output_info=final_output,
        tripwire_triggered=block,
    )




Instruction = """
You are a specialist agent that extracts visitor registration details from human messages and maps them into a structured output format.

## Your task
- Read the user's message.
- Extract only the following fields into VisitorChatOutputFormat: name, mobile_no, purpose, whom_to_meet, vehicle_number.
- If a value is not mentioned in the message, use an empty string "" for that field.
- Do not invent, guess, or add any value that is not clearly stated. Do not add commentary or your own answers.

## Output format (VisitorChatOutputFormat)
- name, mobile_no, purpose, whom_to_meet, vehicle_number — all strings; use "" when missing.

## Example
**Incoming message:** "Hey I am Sandhya.S, today I plan to meet our chairman sir regarding my scholarship. Here are my contact details: 7502696005, and my vehicle no: TN66Y4524."

**Your output:** name="Sandhya.S", mobile_no="7502696005", purpose="scholarship", whom_to_meet="chairman sir", vehicle_number="TN66Y4524".

## Rules (follow strictly)
1. Map only what is explicitly stated in the message; never fabricate or infer values.
2. Use empty string "" for any field that is not present in the message.
3. Output only the structured format; do not include any extra text or explanation.
"""

GuardrailInstruction = """
You are a specialist guardrail agent that decides whether incoming input is a valid visitor registration request and whether all required fields are present.

## Your task
Evaluate the user's message in two steps:
1. Decide if the message is about visiting someone (visitor entry) or something else.
2. If it is a visitor entry, check which required fields are missing from the message.

## Output format (VisitorGuardrailsOutputFormat)
- is_visitor_entry: true if the message is about visiting someone; false otherwise.
- missing_required_fields: array of field names that are required but not present. Use exact names only: name, mobile_no, purpose, whom_to_meet, vehicle_number. Use [] when nothing is missing or when is_visitor_entry is false.

## Scenarios
**Scenario 1 — Not a visitor entry:** Message is about something else (e.g. food, weather, general chat). Set is_visitor_entry to false and missing_required_fields to [].

**Scenario 2 — Visitor entry with missing fields:** Message is about visiting someone but does not mention all required fields. Set is_visitor_entry to true and list only the missing field names in missing_required_fields (e.g. ["mobile_no", "vehicle_number"]).

**Scenario 3 — Visitor entry with all fields:** Message is about visiting someone and includes all required details. Set is_visitor_entry to true and missing_required_fields to [].

## Example
**Incoming message:** "I am Diwa, I plan to visit the manager to discuss my project work."

**Your output:** is_visitor_entry=true, missing_required_fields=["mobile_no", "vehicle_number"] (name, whom_to_meet, purpose are present; mobile_no and vehicle_number are missing).

## Rules (follow strictly)
1. Use only the exact field names in missing_required_fields: name, mobile_no, purpose, whom_to_meet, vehicle_number.
2. When is_visitor_entry is false, always set missing_required_fields to [].
3. Output only the structured format; do not add commentary.
"""

input_guardrail_agent = Agent(
    name="Visitor input guardrail — validates visitor intent and required fields",
    instructions=GuardrailInstruction,
    output_type=VisitorGuardrailsOutputFormat,
)

visitor_agent = Agent(
    name="Visitor registration extractor — maps messages to VisitorChatOutputFormat",
    instructions=Instruction,
    output_type=VisitorChatOutputFormat,
    model="gpt-4o-mini",
    input_guardrails=[
        InputGuardrail(guardrail_function=VisitorInputGuardrails)
    ]
)


def health_check() -> dict:
    """Check API is up. Returns status and code for load balancers / monitors."""
    return {"status": "ok", "status_code": 200}


@app.get("/health", status_code=status.HTTP_200_OK)
async def get_health():
    """Health check endpoint. Returns 200 when the API is running."""
    return health_check()


@app.post(
    "/visit",
    response_model=None,
    responses={
        status.HTTP_200_OK: {
            "description": "Valid visitor input; all required fields present.",
            "model": VisitorSuccessResponse,
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Input is not a visitor registration request.",
            "model": VisitorNotRelevantResponse,
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "Visitor input but one or more required fields are missing.",
            "model": VisitorMissingFieldsResponse,
        },
    },
)
async def process_visitor(payload: VisitorRequest):
    """
    Process a visitor message.

    - **200**: Input is a valid visitor registration with all required fields → returns VisitorChatOutputFormat.
    - **400**: Input is not about visiting someone → user-friendly message.
    - **422**: Input is about visiting but missing required fields → user-friendly message + list of missing fields.
    """
    try:
        runner = await Runner.run(visitor_agent, payload.message)
        result = runner.final_output_as(VisitorChatOutputFormat)
        return VisitorSuccessResponse(
            name=result.name,
            mobile_no=result.mobile_no,
            purpose=result.purpose,
            whom_to_meet=result.whom_to_meet,
            vehicle_number=result.vehicle_number,
        )
    except InputGuardrailTripwireTriggered as e:
        gr_output: VisitorGuardrailsOutputFormat = e.guardrail_result.output.output_info
        if not gr_output.is_visitor_entry:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=VisitorNotRelevantResponse(
                    message="Your message doesn't seem to be a visitor registration. Please send details about who you are, whom you want to meet, purpose, contact number, and vehicle number (if any) so we can register your visit.",
                ).model_dump(),
            )
        # Valid visitor intent but missing required fields
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=VisitorMissingFieldsResponse(
                message="We need a few more details to complete your visitor registration.",
                missing_required_fields=gr_output.missing_required_fields,
            ).model_dump(),
        )


# ---------------------------------------------------------------------------
# Run API server (for local / production)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)


