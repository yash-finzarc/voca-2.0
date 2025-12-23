## Hindi Voice Agent Integration – Twilio + VOCA

This document explains the changes made to support a **Hindi-speaking voice agent** in this project. It is written for the original author of the codebase so you can quickly understand:

- What the system was doing before
- The problems we saw in real calls
- The exact changes we made (where, why, and what they fix)
- How the current architecture works

---

## 1. Previous Behaviour (Before Our Changes)

### 1.1 Call Flow and STT

- **Outbound calls**:
  - Frontend → `POST /api/twilio/make-call`.
  - `TwilioCallManager.make_outbound_call()` (`src/voca/twilio_voice.py`) created a Twilio call with TwiML URL:
  - `BASE_URL/outbound` (where `BASE_URL` came from `TwilioConfig.get_webhook_url()`).

- **Inbound/outbound webhooks** (modular API, `src/voca/api/routes/webhooks.py`):
  - `/outbound` and `/webhook/voice` returned TwiML like:

    ```xml
    <Response>
      <Say>Greeting...</Say>
      <Gather input="speech"
              language="hi-IN"
              action="/process_speech/{CallSid}"
              method="POST"
              timeout="10"
              speechTimeout="auto">
        <Say>I'm listening...</Say>
      </Gather>
      <Redirect>/process_speech/{CallSid}</Redirect>
    </Response>
    ```

  - This relied on **Twilio's built-in `<Gather>` speech recognition**. All understanding came from `SpeechResult` in the webhook.

- **`/process_speech/{call_sid}`**:
  - Read `SpeechResult` and `Confidence` from the form payload.
  - If `SpeechResult` was non-empty and `Confidence > 0.5`:
    - Logged `USER: <SpeechResult>`.
    - Passed the text to `VocaOrchestrator.generate_reply(...)`.
    - Returned TwiML with `<Say>` + another `<Gather>` loop.
  - Else (no speech or low confidence):

    ```xml
    <Say>I didn't catch that. Please speak clearly.</Say>
    <Redirect>/process_speech/{CallSid}</Redirect>
    ```

    **Note:** this error branch had **no `<Gather>`**, only `<Say>` + `<Redirect>`.

### 1.2 Orchestrator and LangGraph Agent

- `VocaOrchestrator.generate_reply()` (`src/voca/orchestrator.py`):
  - Received the raw `user_text` from Twilio STT.
  - Built a `LangGraphAgent` request using:
    - System prompt (from Supabase via `system_prompt.py`),
    - Conversation messages,
    - `collected_data`, `lead_status`, and `transcript`.

- `LangGraphAgent` (`src/voca/langgraph_agent.py`):
  - Used Gemini via `ChatGoogleGenerativeAI`.
  - Maintained **structured lead state** with:

    ```python
    class LeadData(BaseModel):
        name: Optional[str] = None
        ...
        custom_fields: Dict[str, Optional[str]] = Field(default_factory=dict)

    class LeadUpdate(BaseModel):
        lead: LeadData
        lead_status: Optional[str]
        summary_requested: bool
    ```

  - `_assistant_node`: produced `AIMessage` replies.
  - `_state_tracker_node`: used `self.state_parser = chat_llm.with_structured_output(LeadUpdate)` to ask the LLM for a `LeadUpdate`. On any exception (e.g. schema validation), it **discarded the update and returned the old state**.

### 1.3 Problems Observed in Real Calls

1. **Hindi intent was OK, names were not:**
   - Phrases like "मुझे चिकित्सक से बात करनी है।" were correctly recognized and handled.
   - Names (especially Indian names) were often mis-heard or low-confidence, for example:
     - "Keshav" → `"Station"`.

2. **"I didn't catch that" loop:**
   - On low confidence or empty `SpeechResult`, the `/process_speech` handler:
     - Played "I didn't catch that..." and then `<Redirect>`-ed back to `/process_speech`.
     - Because there was **no `<Gather>`** in that path, Twilio did **not listen again**.
     - Twilio immediately re-posted to `/process_speech` with no fresh `SpeechResult`, causing an endless "I didn't catch that" loop without giving the user a chance to speak.

3. **Lead extraction kept failing due to `custom_fields`:**
   - `LeadData.custom_fields` was typed as `Dict[str, Optional[str]]`.
   - The LLM sometimes emitted:

     ```json
     "custom_fields": "null"
     ```

     or `"None"` (string), which violated the schema.
   - This caused `LeadUpdate` validation to fail and `_state_tracker_node` logged:

     > `Lead state extraction failed: ... custom_fields Input should be a valid dictionary`

   - As a result, **valid `lead.name` updates were discarded**, and the agent repeatedly believed it still did not have the user's name, asking again and again.

4. **Deepgram Real-Time Transcription was configured but not actually used:**
   - There were `<Start><Transcription transcriptionEngine="deepgram" speechModel="nova-3" languageCode="hi-IN">` blocks in the old monolithic `api.py` and `twilio_voice.py`.
   - However, callback logs showed that Real-Time Transcription events had **empty `TranscriptionText`**, while all real understanding still came from `<Gather>` → `SpeechResult`.

---

## 2. Twilio / Real-Time Transcription Updates

### 2.1 Enable Real-Time Transcriptions with a Supported Hindi Combo

**File:** `src/voca/api/routes/webhooks.py`

We prepended a `<Start><Transcription>` block in both `/outbound` and `/webhook/voice` routes and switched to a documented, supported combo for Hindi:

- `transcriptionEngine="google"`
- `languageCode="hi-IN"`
- `speechModel="short"`
- Optional extras: `enableAutomaticPunctuation`, `profanityFilter`, `hints`.

```python
from twilio.twiml.voice_response import VoiceResponse, Start, Transcription

...

@router.post("/outbound")
async def handle_outbound_call(request: Request):
    ...
    response = VoiceResponse()

    # Enable Real-Time Transcriptions for Hindi using Google's short model (supported combo)
    if call_sid:
        config = get_twilio_config()
        webhook_url = config.get_webhook_url()
        base_url = webhook_url.replace("/webhook/voice", "")

        transcription_callback_url = f"{base_url}/transcription/{call_sid}"
        start = Start()
        transcription = Transcription(
            statusCallbackUrl=transcription_callback_url,
            transcriptionEngine="google",
            speechModel="short",
            languageCode="hi-IN",
            enableAutomaticPunctuation="true",
            profanityFilter="true",
            hints="संपर्क, सेवा, समर्थन, ग्राहक",
        )
        start.append(transcription)

        response.append(start)
        logger.info(
            f"[TRANSCRIPTION] Enabled Real-Time Transcription (google, hi-IN, short) "
            f"for outbound call {call_sid} (callback={transcription_callback_url})"
        )
```

We did the same for `handle_incoming_call_webhook`.

**Why:**

- Twilio’s own docs show Hindi Real-Time Transcriptions configured with **Google** and **short model** rather than Deepgram nova‑3, and your Deepgram configuration was returning empty transcripts.
- Switching to a supported combo guarantees we get actual `TranscriptionText` from the webhook to feed into the agent.

### 2.2 Keep the Call Alive with `<Gather>`, but Don’t Rely on `SpeechResult` for Meaning

We kept a `<Gather>` after the greeting in both `/outbound` and `/webhook/voice` to prevent early hangup and define turns:

```python
    # Log greeting as AI response
    if call_sid:
        logger.info(f"📞 Call {call_sid[:8]}... | AI: {greeting}")
    response.say(greeting)

    # IMPORTANT: Twilio RT Transcriptions don't use /transcription TwiML to control calls.
    # To keep the call open, we also include a legacy <Gather> loop. RT Transcription
    # streams in parallel for semantics; <Gather> provides call control + turn boundaries.
    if call_sid:
        gather = response.gather(
            input="speech",
            timeout=60,
            speech_timeout="auto",
            language="hi-IN",
            action=f"/process_speech/{call_sid}",
            method="POST",
        )
        gather.say("I'm listening...")
        response.redirect(f"/process_speech/{call_sid}")

    return Response(content=str(response), media_type="text/xml")
```

**Why:**

- Twilio’s Real-Time Transcription callback (/transcription) is **data-only** – Twilio does not use the TwiML returned there for call control.
- The call *must* have a long-lived verb (e.g. `<Gather>`) in the initial TwiML. Otherwise Twilio executes the greeting `<Say>` and immediately ends the call.
- We use `<Gather>` primarily to keep the call up and mark turns, but no longer treat `SpeechResult` as the only semantic source.

### 2.3 Make `/process_speech` Prefer RT Transcript Text Over `SpeechResult`

**File:** `src/voca/api/routes/webhooks.py`

In `handle_speech_webhook`, we changed the core logic for deciding what text to feed into the agent:

- **Before:** only `SpeechResult` was used, gated by `confidence > 0.5`.
- **Now:** we first try the latest Real-Time Transcription text; if none, we fall back to `SpeechResult`.

```python
@router.post("/process_speech/{call_sid}")
async def handle_speech_webhook(call_sid: str, request: Request):
    ...
    form_data = await request.form()
    speech_result = form_data.get("SpeechResult", "") or ""
    confidence = form_data.get("Confidence", "0")

    # Primary source of truth: latest completed Real-Time Transcription text
    call_data = voice_handler.active_calls.get(call_sid, {})
    transcripts = call_data.get("transcriptions", [])
    user_text = ""

    if transcripts:
        latest = transcripts[-1]
        t_text = (latest.get("text") or "").strip()
        if t_text:
            user_text = t_text

    # Fallback: if we have no transcript text yet, fall back to SpeechResult
    if not user_text and speech_result.strip():
        user_text = speech_result.strip()

    # If we still have nothing, go to the "no speech" branch
    if user_text:
        logger.info(f"📞 Call {call_sid[:8]}... | USER: {user_text}")
        app_state._log_callback(
            f"Speech received for call {call_sid}: {user_text} "
            f"(confidence={confidence}, source={'rt_transcription' if transcripts else 'gather'})"
        )
        try:
            ai_response = voice_handler.orchestrator.generate_reply(
                user_text,
                conversation_id=call_sid,
                call_sid=call_sid,
            )
            ...
```

**Why:**

- To **truly use Real-Time Transcription text** (Google hi‑IN) as the semantic source.
- If transcripts are present, they’re assumed more reliable than `SpeechResult`, especially for Indian names.
- `SpeechResult` is now only a fallback when RT transcription hasn’t produced text yet.

### 2.4 Fix the “I Didn’t Catch That” Loop

Still in `handle_speech_webhook`, we fixed both the error and “no speech” branches to always start a new `<Gather>`:

- **Before:**

  ```python
  else:
      response = VoiceResponse()
      response.say("I didn't catch that. Please speak clearly.")
      if call_sid:
          response.redirect(f'/process_speech/{call_sid}')
      return Response(...)
  ```

  This caused Twilio to hammer `/process_speech` without listening again.

- **Now:**

  ```python
  else:
      # No speech or empty result – gently prompt again, but ALWAYS start a new <Gather>
      response = VoiceResponse()
      response.say("I didn't catch that. Please speak clearly.")
      if call_sid:
          gather = response.gather(
              input="speech",
              timeout=60,
              speech_timeout="auto",
              language="hi-IN",
              action=f"/process_speech/{call_sid}",
              method="POST",
          )
          gather.say("I'm listening...")
          response.redirect(f"/process_speech/{call_sid}")
      return Response(content=str(response), media_type="text/xml")
  ```

**Why:**

- Ensures Twilio always gives the user another chance to speak instead of looping with no audio.

---

## 3. LangGraph / Lead Extraction and Name Handling

### 3.1 Make `custom_fields` Robust

**File:** `src/voca/langgraph_agent.py`

**Problem:** The LLM sometimes emitted `"custom_fields": "null"` or `"None"`, which violates the `Dict[str, Optional[str]]` type and caused Pydantic validation errors, discarding the entire `LeadUpdate` (including `lead.name`).

**Change:**

```python
from pydantic import BaseModel, Field, field_validator

class LeadData(BaseModel):
    ...
    custom_fields: Dict[str, Optional[str]] = Field(default_factory=dict)

    @field_validator("custom_fields", mode="before")
    @classmethod
    def _coerce_custom_fields(cls, v: Any) -> Dict[str, Optional[str]]:
        """
        Ensure custom_fields is always a dictionary.

        The LLM sometimes emits values like "null" or "None" for this field.
        Those should be treated as an empty object rather than causing
        schema validation failures.
        """
        if v is None or v == "" or v in ("null", "None"):
            return {}
        if isinstance(v, dict):
            return v
        # Any other unexpected type (e.g. list/str) -> ignore and use empty dict
        return {}
```

**Why / Effect:**

- This prevents `LeadUpdate` parsing from failing due to a weird `custom_fields` value.
- Valid name data (and other lead fields) can still be merged into `collected_data` even if `custom_fields` is junk.

### 3.2 Explicitly Support Names + Indian Context in Tracker Instructions

Still in `langgraph_agent.py`, we refined the state tracker’s system prompt:

**Before:**

```python
tracker_instructions = (
    "You are a CRM state tracker. "
    "Given the full conversation, extract any newly provided values for the lead fields "
    "(name, phone, email, service_type, preferred_date, preferred_time, number_of_people, "
    "room_type, notes) and store them in JSON. "
    "Only include fields that are explicitly mentioned. "
    "Classify the lead as hot, warm, or cold depending on intent and readiness. "
    "Set summary_requested to true only if the user explicitly requests a summary."
)
```

**After:**

```python
tracker_instructions = (
    "You are a CRM state tracker. "
    "Given the full conversation, extract any newly provided values for the lead fields "
    "(name, first_name, last_name, phone, email, service_type, preferred_date, "
    "preferred_time, number_of_people, room_type, notes) and store them in JSON. "
    "Only include fields that are explicitly mentioned. "
    "Classify the lead as hot, warm, or cold depending on intent and readiness. "
    "Set summary_requested to true only if the user explicitly requests a summary. "
    "\n\n"
    "The conversation may be in Hindi or English. Users may say their names in Hindi "
    "script (e.g. 'आदित्य शर्मा') or romanized English (e.g. 'Aditya Sharma'). When the "
    "assistant asks for the user's name and the next user message is a short phrase "
    "(1–3 words) that looks like a name, set lead.name to that value, and, when it is "
    "naturally separable, set lead.first_name and lead.last_name as well. "
    "\n\n"
    "IMPORTANT: The custom_fields field MUST ALWAYS be a JSON object (dictionary). "
    "If you have no custom fields, set custom_fields to {}. Do not set it to the "
    "string 'null', 'None', or any other non-object value."
)
```

**Why / Effect:**

- Makes the LLM:
  - Treat short replies after "What is your first name?" as a name, even in Hindi script or romanized English.
  - Keep `custom_fields` as `{}` when unused, instead of `"null"`/`"None"`.
- Combined with the validator, this significantly reduces name-related extraction failures.

---

## 4. Current State and How to Extend

As of these changes:

- Twilio **Real-Time Transcriptions** are used with a **supported Hindi configuration** (Google hi‑IN short).
- Your semantic pipeline now prefers the **Real-Time `TranscriptionText`** over `SpeechResult`.
- `<Gather>` is retained for call control and turn boundaries, but no longer the sole semantic source.
- The agent’s **lead state tracker** is more robust:
  - It no longer discards valid updates due to `custom_fields`.
  - It is explicitly told how to treat Hindi/romanized names.

If you later want to:

- Move to a different engine (e.g., Deepgram nova‑3 for Hindi), you can:
  - Swap `transcriptionEngine`/`languageCode`/`speechModel` in one place in `routes/webhooks.py`.
  - Keep the same `/transcription` → `/process_speech` → `VocaOrchestrator` logic.

- Add stronger name handling (e.g., spelling, confirmation):
  - Continue refining the state tracker prompt.
  - Add heuristics in `_state_tracker_node` to detect when the last user message is likely a name and force-set `lead.name` even if structured output is uncertain.

This document should give you a precise map of what changed and why, so you can confidently iterate from here. 

