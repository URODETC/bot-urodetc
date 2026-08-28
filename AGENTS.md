# AGENTS.md

## Project Overview

This project is a personal service platform with Telegram as its primary interface.

Do **not** treat the project as a collection of Telegram commands. The core system is a modular platform of services/tools that can later be accessed through multiple interfaces:

- Telegram commands
- Telegram inline mode
- Telegram callbacks
- REST API
- Web dashboard
- CLI
- AI agent

Telegram is an adapter/interface layer, not the center of the business architecture.

---

# Core Architecture Principles

## 1. Keep Telegram handlers thin

Telegram handlers must not contain business logic.

Handlers should only:

1. Parse incoming Telegram data.
2. Validate basic input.
3. Call the appropriate service/tool.
4. Return or format a response.

Avoid:

```python
@router.message(Command("download"))
async def download(message: Message):
    url = message.text.split()[1]

    # Download video
    # Convert video
    # Save file
    # Upload file
    # Handle retries
    # Update database
```

Prefer:

```python
@router.message(Command("download"))
async def download(message: Message):
    url = extract_url(message.text)

    job = await video_service.create_job(
        user_id=message.from_user.id,
        url=url,
    )

    await message.answer(
        f"Task {job.id} was added to the queue."
    )
```

The service and worker layers must handle the actual business logic.

---

# 2. Use a modular Tool / Service architecture

Every independent capability should exist as an isolated module.

Examples:

- Video download and processing
- Football match notifications
- WHOIS lookup
- Server monitoring
- Search
- File processing
- Future custom services

Suggested structure:

```text
app/
├── main.py
│
├── telegram/
│   ├── bot.py
│   ├── commands/
│   ├── inline/
│   └── callbacks/
│
├── tools/
│   ├── video/
│   │   ├── service.py
│   │   ├── downloader.py
│   │   ├── models.py
│   │   └── manifest.py
│   │
│   ├── football/
│   │   ├── service.py
│   │   ├── provider.py
│   │   ├── scheduler.py
│   │   └── models.py
│   │
│   ├── whois/
│   │   ├── service.py
│   │   ├── parser.py
│   │   └── models.py
│   │
│   └── server_monitor/
│       ├── service.py
│       └── models.py
│
├── jobs/
│   ├── models.py
│   ├── queue.py
│   └── workers/
│
├── events/
│   ├── bus.py
│   └── models.py
│
├── notifications/
│   └── service.py
│
├── infrastructure/
│   ├── database.py
│   ├── redis.py
│   ├── logging.py
│   └── config.py
│
├── registry/
│   └── tools.py
│
└── tests/
```

Each tool should own its business logic and domain-specific code.

Avoid creating one giant `services.py` file or one giant Telegram router containing unrelated functionality.

---

# 3. Define a common Tool interface

Tools should have a consistent abstraction.

Example:

```python
class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def execute(self, **kwargs):
        ...
```

Example implementation:

```python
class WhoisTool(BaseTool):
    name = "whois"

    async def execute(self, domain: str):
        return await whois_service.lookup(domain)
```

Another example:

```python
class VideoTool(BaseTool):
    name = "video"

    async def execute(self, url: str):
        return await video_service.create_job(url=url)
```

The exact abstraction can evolve, but the architecture should preserve the idea that tools are independent capabilities with a clear interface.

---

# 4. Use a Tool Registry

Tools should be discoverable through a central registry.

Conceptually:

```python
TOOLS = {
    "whois": WhoisTool(),
    "video": VideoTool(),
    "football": FootballTool(),
}
```

Prefer a proper registry implementation over scattered imports and hardcoded conditionals as the project grows.

The registry should eventually support:

- Tool discovery
- Metadata
- Enabled/disabled state
- Command mapping
- Inline capability
- Async job capability
- Permissions

Avoid:

```python
if command == "whois":
    ...
elif command == "video":
    ...
elif command == "football":
    ...
```

for the main application architecture.

---

# 5. Commands and inline mode must share business logic

Telegram commands and inline queries are different interfaces for the same underlying capabilities.

Example:

```text
/whois example.com
```

and:

```text
@bot example.com
```

should both use:

```python
await whois_service.lookup(domain)
```

Do not duplicate business logic between:

```text
telegram/commands/whois.py
telegram/inline/whois.py
```

Preferred flow:

```text
Telegram Command ───┐
                    │
                    ▼
              WhoisService
                    ▲
                    │
Telegram Inline ────┘
```

Telegram-specific code may differ, but domain/business logic must remain shared.

---

# 6. Long-running work must use a Job Queue

Potentially slow operations must not run directly inside Telegram request handlers.

Examples:

- Video downloads
- Audio extraction
- Video conversion
- Large file processing
- AI generation
- Heavy external API operations
- Server scans

Use a job-based architecture:

```text
User
 │
 │ Request
 ▼
Telegram Bot
 │
 ▼
Create Job
 │
 ▼
Queue
 │
 ▼
Worker
 │
 ├── Execute work
 ├── Retry if needed
 ├── Update progress
 │
 ▼
Store result
 │
 ▼
Notify user
```

Suggested job model:

```text
Job
├── id
├── type
├── status
├── payload
├── result
├── progress
├── error
├── created_at
├── started_at
└── finished_at
```

Suggested statuses:

```text
PENDING
RUNNING
SUCCESS
FAILED
CANCELLED
```

All tools that need asynchronous execution should use the same generic job infrastructure instead of implementing independent task systems.

---

# 7. Separate synchronous and asynchronous execution

Fast operations can return immediately:

```text
WHOIS lookup
Small API request
Cached search
Simple status query
```

Slow operations should create jobs:

```text
Video download
Media conversion
Large processing
Long-running scans
```

A tool should clearly communicate whether its result is:

- Immediate
- Cached
- Queued
- Failed

Do not make users or callers wait synchronously for potentially long operations.

---

# 8. Use a Provider abstraction for external APIs

Business services should not depend directly on a specific external API.

Bad:

```python
class FootballService:
    async def get_matches(self):
        return await specific_api.get(...)
```

Prefer:

```text
FootballService
       │
       ▼
FootballProvider
       │
       ├── Provider A
       ├── Provider B
       └── Cached Provider
```

Example:

```python
class FootballProvider(Protocol):
    async def get_matches(
        self,
        date: datetime,
    ) -> list[Match]:
        ...
```

Then implementations can be swapped:

```python
class ProviderA:
    ...

class ProviderB:
    ...
```

This pattern should be used for any unstable or replaceable external dependency.

The domain service should depend on an abstraction, not a concrete API provider.

---

# 9. Football notifications should use centralized scheduling

Do not create one long-running timer per user subscription.

Avoid:

```python
asyncio.create_task(wait_until_match())
```

for every notification.

Instead:

```text
Scheduler
    │
    ▼
Fetch upcoming matches
    │
    ▼
Find matching subscriptions
    │
    ▼
Create notifications
    │
    ▼
Notification Queue
    │
    ▼
Telegram
```

Suggested persistent data:

```text
UserSubscription
├── user_id
├── team_id
├── event_type
├── notify_before_minutes
└── enabled
```

The scheduler should be centralized and idempotent.

Prevent duplicate notifications using database state or distributed locks where appropriate.

---

# 10. Separate persistent storage and ephemeral infrastructure

Use persistent storage for durable state.

Examples:

```text
Users
Subscriptions
Jobs
Job history
Settings
Saved items
Notification history
```

Use cache/ephemeral infrastructure for:

```text
Cached API responses
Rate limits
Temporary state
Distributed locks
Queue state
Short-lived sessions
```

Do not treat cache as the source of truth for critical durable user data.

---

# 11. Introduce an Event Bus when service interactions grow

As the number of tools grows, services should communicate through domain events where appropriate.

Examples:

```text
video.downloaded
video.failed

match.starts_soon
match.started

server.down
server.recovered
```

Architecture:

```text
Service
   │
   ▼
Event
   │
   ▼
Event Bus
   │
   ├── Notification Service
   ├── Logging
   ├── Analytics
   └── Other consumers
```

Example:

```python
await event_bus.publish(
    MatchStartingEvent(
        match_id=123,
    )
)
```

Do not introduce an overly complex distributed event system too early. A simple in-process abstraction may be enough initially.

The goal is to reduce tight coupling between services.

---

# 12. Use Tool Manifests

Every tool should expose metadata.

Example:

```python
@dataclass
class ToolManifest:
    name: str
    description: str
    commands: list[str]
    inline: bool
    async_mode: bool
```

Example:

```python
VIDEO_MANIFEST = ToolManifest(
    name="video",
    description="Download and process video",
    commands=["download", "audio"],
    inline=False,
    async_mode=True,
)
```

```python
WHOIS_MANIFEST = ToolManifest(
    name="whois",
    description="Domain lookup",
    commands=["whois"],
    inline=True,
    async_mode=False,
)
```

The registry should use manifests for discovery and routing.

This can later support automatic generation of:

- `/help`
- Tool menus
- Web dashboard
- REST API documentation
- AI tool schemas

Avoid duplicating tool metadata across multiple files.

---

# 13. Prepare tools for future AI integration

The architecture should make it possible for an AI agent to invoke tools without depending on Telegram-specific code.

Conceptually:

```text
Telegram ──┐
           │
Web API ───┤
           │
CLI ───────┤
           ▼
      Tool Registry
           │
           ├── WhoisTool
           ├── VideoTool
           ├── FootballTool
           └── ServerTool
```

An AI agent should call the same domain tools used by Telegram.

Do not create a separate duplicate implementation specifically for AI integration.

---

# 14. Recommended dependency direction

Dependencies should generally flow inward:

```text
Interfaces
    ↓
Application / Tool Layer
    ↓
Domain Services
    ↓
Infrastructure
```

Telegram code may depend on services.

Services should not depend on Telegram.

External API implementations may depend on HTTP/database libraries.

Core domain models should not depend on Telegram-specific types.

Avoid this:

```text
VideoService
    └── imports Telegram Message
```

Prefer passing domain-level data:

```python
await video_service.create_job(
    user_id=user_id,
    url=url,
)
```

instead of:

```python
await video_service.create_job(
    message=telegram_message,
)
```

---

# 15. Error handling

Errors should be classified.

Suggested categories:

```text
ValidationError
NotFoundError
ExternalServiceError
TemporaryError
PermanentError
RateLimitError
PermissionError
```

Telegram adapters should translate domain errors into user-friendly messages.

Workers should decide whether an error is retryable.

Do not retry permanently invalid requests.

Do not expose raw internal exceptions to users.

Always log enough structured context to debug failures.

---

# 16. Observability

Every important operation should be observable.

At minimum, implement:

- Structured logging
- Job IDs
- Request/correlation IDs where useful
- Error logging
- Execution duration
- Retry count

Example useful fields:

```text
user_id
tool
job_id
event
duration_ms
status
error_type
```

Do not log secrets, tokens, or sensitive private data.

---

# 17. Security and permissions

Since this is a personal bot, still design permissions explicitly.

Possible model:

```text
Public
Authenticated
Owner-only
Admin
```

Tools should be able to declare required permissions.

Example:

```python
class ServerTool:
    required_permission = "owner"
```

Do not rely only on hiding Telegram commands.

Authorization should be checked before sensitive operations.

---

# 18. Recommended implementation order

Build the architecture incrementally.

## Phase 1

Implement:

- Telegram adapter
- Tool/service layer
- Tool registry
- One synchronous tool
- One asynchronous tool
- Basic database

Suggested first tools:

```text
WHOIS
Video download
```

## Phase 2

Add:

- Generic job model
- Queue
- Workers
- Progress tracking
- Retry handling

## Phase 3

Add:

- Football provider abstraction
- Subscription storage
- Central scheduler
- Notification service

## Phase 4

Add:

- Event bus
- Tool manifests
- Better observability
- Permissions

## Phase 5

Add additional interfaces:

- REST API
- Web dashboard
- CLI
- AI agent integration

Do not build unnecessary microservices initially.

Prefer a modular monolith with clear boundaries.

Split components into separate processes or services only when there is a concrete operational reason.

---

# 19. Architectural rule of thumb

When adding a new feature, ask:

1. Is this a new interface or a new capability?
2. Can an existing tool/service handle it?
3. Does it need synchronous or asynchronous execution?
4. Does it require persistent state?
5. Is an external provider involved?
6. Could another interface use the same capability?
7. Does this feature produce domain events?
8. Does it require special permissions?

The preferred architecture is:

```text
                 Interfaces
        ┌──────────┼──────────┐
        ▼          ▼          ▼
    Telegram      API        CLI
        │          │          │
        └──────────┼──────────┘
                   ▼
              Tool Router
                   ▼
              Tool Registry
                   ▼
        ┌──────────┼──────────┐
        ▼          ▼          ▼
      Video     Football     WHOIS
       Tool       Tool       Tool
        │          │          │
        └──────────┼──────────┘
                   ▼
            Domain Services
                   ▼
             Infrastructure
        ┌──────────┼──────────┐
        ▼          ▼          ▼
     Database     Queue     Providers
                   │
                   ▼
                 Workers
                   │
                   ▼
                Events
                   │
                   ▼
             Notifications
```

---

# Final Principle

Build this project as a **personal extensible service platform**, not as a monolithic Telegram bot.

The desired architecture is:

> Interfaces invoke tools. Tools invoke domain services. Services use infrastructure through abstractions. Long-running work goes through jobs/workers. Cross-service communication can happen through events. Telegram remains replaceable.

When making implementation decisions, prefer:

- Clear module boundaries
- Shared business logic
- Reusable tools
- Thin interface adapters
- Explicit async workflows
- Replaceable providers
- Incremental complexity
- Modular monolith first
