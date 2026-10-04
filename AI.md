# AI integration

## Providers and the abstraction boundary

Three interfaces (`backend/app/services/ai/base.py`) decouple business logic
from any specific vendor:

- `TextAIProvider.complete(...)`
- `ImageAIProvider.generate(...) / status()`
- `SearchProvider.search(...)`

No service outside `app/services/ai/` ever imports a concrete provider class.
Swapping Timeweb for another OpenAI-compatible vendor, or adding a second
image backend, means writing one new class and one line in
`app/services/ai/factory.py` — nothing else changes.

## Text: Timeweb Agent (GPT-6 Sol)

`TimewebAgentTextProvider` calls `TIMEWEB_AGENT_BASE_URL + "/chat/completions"`
with a Bearer token, matching Timeweb's documented OpenAI-compatible agent
API. Two deliberate constraints, both because Timeweb's docs do not guarantee
otherwise:

- The `model` field in the request body is sent for schema compliance only.
  The agent's actual model (GPT-6 Sol) is fixed by the agent's own
  configuration in the Timeweb console — the field is **not** relied on to
  select a model.
- No unsupported sampling parameters are sent. The request body is
  `{model, messages, max_tokens, temperature, stream: false}` — nothing
  copied blindly from GPT-4/GPT-5 integration patterns (e.g. no
  `response_format`, no `logprobs`, no reasoning-effort knobs) unless the
  Timeweb docs for this agent confirm support.

## Image: GPT Image 2.5 Sunburst — why it's `UNAVAILABLE` by default

At the time this was built, Timeweb's documentation describes the agent's
image generation (GPT Image 2.5 Sunburst) as reachable through the hosted
chat widget, **not** as a documented `/images/generations`-style programmatic
endpoint on the OpenAI-compatible agent API. Per the project's explicit
instruction to never fabricate an endpoint, `TimewebGatewayImageProvider`:

- targets the separate **AI Gateway** product via `TIMEWEB_AI_GATEWAY_BASE_URL`
  / `TIMEWEB_AI_GATEWAY_API_KEY` / `TIMEWEB_IMAGE_MODEL`, which is the most
  plausible documented path to a real image API if/when one is confirmed;
- reports `ImageProviderStatus.UNAVAILABLE` whenever those env vars are
  empty (the default), `ERROR` if they're set but the endpoint doesn't
  respond, and only ever `AVAILABLE` once a real, confirmed endpoint is
  wired into `generate()` (currently `raise NotImplementedError` with a
  message pointing at what to fill in);
- is read everywhere in the app through `ImageAIProvider.status()`, so the UI
  (`Settings → AI status`, Cost Dashboard) shows a honest
  "Image provider is not available through the configured Timeweb API"
  state instead of a broken button or a silent no-op.

The whole image pipeline (`MediaService`, `MediaGeneration` model, Cost
Dashboard breakdown by provider, Media Gallery) is fully built against the
interface — turning the feature on in production is changing three env vars
and implementing one method, not a redesign.

`FakeImageProvider` (used when `USE_FAKE_IMAGE_PROVIDER=true`, the dev
default) returns a real 1×1 PNG and a believable usage payload so the rest of
the pipeline (storage, gallery, cost ledger) can be exercised end-to-end
without a real provider.

## One AI call per ordinary post

`AIService.generate_post` issues exactly one `TextAIProvider.complete` call
and parses the response as a single JSON object matching `GenerationResult`
(`app/schemas/generation.py`). If the JSON can't be parsed or doesn't satisfy
the Pydantic schema, **one** automatic retry is made with an amended prompt
asking the model to return corrected JSON — never more than that, and never
silently accepting malformed output. Every attempt (including failed ones) is
recorded as an `AIRequest` row so the cost ledger and audit trail see every
call made, not just successful ones.

Rewrite / Shorten / Expand / Change Tone / Regenerate Title / Regenerate
Fragment / Regenerate Image are explicit, user-triggered calls through the
same `AIService`, billed and logged identically — there is no implicit
"improve this" loop anywhere in the codebase.

## Duplicate detection without a second AI call

`DuplicateDetectionService` never calls an AI provider. It combines trigram
(shingle) Jaccard similarity, SimHash over the same shingles, and
category/tag overlap into a single 0–1 score, compared against recent
`ContentItem`s already in Postgres. The AI-returned `duplicate_fingerprint`
is stored but the score itself is computed locally — see
`app/services/content/duplicate_detection.py`.

## Cost accounting

`CostService` computes `input_cost = prompt_tokens/1e6 * input_rate` and
`output_cost = completion_tokens/1e6 * output_rate` using the rates from
`Settings` at call time (not hardcoded into the formula), and persists both
the raw provider usage and the resulting `AIRequest`/`CostEvent` rows. Budget
checks (`assert_budget_available`) run **before** a billable call is issued —
see `BudgetExceededError` and its `kind` (`daily`/`monthly`/`per_post`).
