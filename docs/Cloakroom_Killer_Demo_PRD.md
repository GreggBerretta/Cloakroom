# Cloakroom Killer Demo PRD

Document status: Draft for IT and engineering review

Date: 2026-04-29

Owner: GB

Demo purpose: Show business IT and security buyers that Cloakroom lets employees use AI chatbots without leaking PII, GDPR-sensitive data, or confidential company information.

## 1. Executive Summary

Cloakroom is a local-first protection layer for employees who want to use AI tools with sensitive business content. The killer demo should show an employee taking a realistic document, shielding sensitive information before it leaves the machine, pasting the safe version into an AI chatbot, and restoring the AI response back to the original values locally.

The demo must make three things obvious:

1. Employees can keep using AI without learning a complicated security tool.
2. Sensitive information is replaced before anything is pasted into an AI chatbot.
3. Original values stay in a local encrypted vault and can be restored only after integrity checks pass.

The core message for IT:

> Cloakroom does not block AI adoption. It creates a local trust boundary between company data and external AI tools.

## 2. Target Audience

### Primary buyer audience

- IT directors
- Security leaders
- Compliance teams
- Data protection officers
- CIO/CTO stakeholders evaluating employee AI risk

### Primary end-user audience

- Consultants
- Analysts
- Operators
- Account managers
- Finance and legal-adjacent knowledge workers
- Employees who paste customer, employee, or internal business data into AI chatbots

## 3. Business Problem

Business customers are worried that employees will accidentally leak sensitive information into external AI chatbots. The risk is not theoretical. Employees already paste real work into AI tools because the productivity gain is obvious.

Sensitive data at risk includes:

- PII such as names, emails, phone numbers, addresses, SSNs, customer IDs, and account numbers
- GDPR-sensitive personal data related to EU citizens or customers
- Confidential customer names and contract terms
- Strategic projects, acquisition plans, pricing strategies, layoffs, incidents, and board-level information
- Regulated content that cannot safely leave managed local infrastructure

Traditional options are painful:

- Block AI tools entirely, which users route around.
- Train employees not to paste sensitive data, which is unreliable.
- Use generic DLP, which is often too broad, opaque, or workflow-breaking.
- Manually redact content, which destroys context and is hard to undo.

Cloakroom should demonstrate a better path:

> Preserve the usefulness of the work while preventing raw sensitive data from leaving local control.

## 4. Demo Goal

The demo should create a clear buyer reaction:

> "I understand exactly what this does, I can see why employees would use it, and I can see how IT can trust it."

The demo must prove:

- Cloakroom identifies sensitive content.
- Cloakroom replaces sensitive content with human-readable tokens.
- The tokenized output remains useful for AI reasoning.
- Original values remain local.
- The AI never sees the original sensitive values.
- Cloakroom can restore the AI response back to original values.
- Cloakroom refuses to restore if the AI mutates, invents, or drops important tokens.
- IT can get audit evidence without creating a new PII exposure.

## 5. Demo Narrative

The demo follows a normal employee workflow:

1. An employee is preparing a customer escalation summary.
2. The summary contains customer names, employee names, emails, phone numbers, EU personal data, contract terms, pricing details, and an internal strategic project codename.
3. The employee wants to ask an AI chatbot to summarize risks and draft a client response.
4. Instead of pasting the raw document, the employee opens Cloakroom.
5. Cloakroom detects sensitive values and shows what it found.
6. The employee clicks "Create AI-Safe Version."
7. Cloakroom replaces sensitive values with tokens and stores the mapping in a local encrypted vault.
8. The employee copies the AI-safe version and pastes it into the chatbot.
9. The chatbot returns useful output with tokens intact.
10. The employee pastes the AI response back into Cloakroom.
11. Cloakroom verifies the tokens and restores the original values locally.
12. IT sees an audit-safe summary proving the shield/restore happened without storing raw PII in logs.

## 6. Demo Data Set

The demo should ship with a built-in sample called "Customer Escalation."

The sample should include:

- A customer escalation memo in plain text or Markdown.
- A matching spreadsheet with customer rows and contract details.
- Optional DOCX version for document workflow.

### Required sensitive examples

PII:

- Person name: `Sarah Morgan`
- Email: `sarah.morgan@acmehealth.eu`
- Phone: `+44 20 7946 0182`
- Address: `15 Farringdon Street, London`
- Customer ID: `EU-CUST-88421`

GDPR-sensitive data:

- EU resident reference
- Health-adjacent customer context
- Personal contact details

Confidential company data:

- Customer name: `Acme Health`
- Contract value: `$2.4M`
- Pricing exception: `18 percent discount`
- Renewal date: `June 30, 2026`

Strategic/internal information:

- Project codename: `Project Lantern`
- Internal incident: `Q3 churn containment plan`
- Executive phrase: `pre-acquisition integration risk`

### Example source text

```text
Sarah Morgan at Acme Health emailed sarah.morgan@acmehealth.eu about the Project Lantern renewal.
The account is EU-CUST-88421 and includes a $2.4M contract with an 18 percent discount exception.
Her phone number is +44 20 7946 0182 and the account address is 15 Farringdon Street, London.
The team wants AI help summarizing the Q3 churn containment plan and pre-acquisition integration risk before the June 30, 2026 renewal meeting.
```

### Example AI-safe output

```text
[PERSON_00001] at [ORG_00001] emailed [EMAIL_00001] about the [PROJECT_00001] renewal.
The account is [CUSTOMER_ID_00001] and includes a [CONTRACT_VALUE_00001] contract with a [PRICING_TERM_00001] exception.
Her phone number is [PHONE_00001] and the account address is [ADDRESS_00001].
The team wants AI help summarizing the [STRATEGY_00001] and [STRATEGY_00002] before the [DATE_00001] renewal meeting.
```

## 7. Product Positioning For The Demo

Cloakroom should not be positioned as "redaction."

Recommended positioning:

- AI-safe work preparation
- Reversible anonymization
- Local trust boundary
- Encrypted restore vault
- Fail-closed restore verification

Avoid positioning:

- Full DLP replacement
- Network proxy
- Employee surveillance tool
- Cloud compliance platform
- Generic file redactor

## 8. Primary Demo UX

The demo should use one primary workflow:

> Shield for AI

This workflow should be available from the first screen with no setup burden.

### First screen

Purpose: Make the workflow obvious within 5 seconds.

Layout:

- Top-left: Cloakroom logo/name
- Top center: workspace selector, default `Demo Workspace`
- Top-right: local status indicators
- Main left pane: source content
- Main center rail: processing steps
- Main right pane: AI-safe output
- Bottom panel: vault, restore, and audit proof

Primary controls:

- `Paste Text`
- `Drop File`
- `Use Demo Sample`
- `Create AI-Safe Version`
- `Copy AI-Safe Text`
- `Restore AI Response`

Persistent status indicators:

- `Local vault active`
- `No original data sent`
- `Workspace expires in 24h`
- `Ready for AI` or `Review required`

### Empty state copy

```text
Drop a file or paste text to prepare it for AI.
```

The empty state should not say "configure detector" or "create policy." The user is here to make work safe for AI.

## 9. Step-By-Step User Experience

### Step 1: Add content

User options:

- Paste text from clipboard.
- Drag and drop a file.
- Select the built-in demo sample.

Immediate UI response:

- The source pane fills with the original content.
- The original content pane is labeled `Original - stays local`.
- Sensitive-looking values are not modified yet.
- The center rail shows the pipeline:
  - `Read content`
  - `Detect sensitive data`
  - `Replace with tokens`
  - `Lock local vault`
  - `Ready for AI`

### Step 2: Detect sensitive data

After content is added, Cloakroom scans it and shows a review table.

Detection groups:

- Personal data
- GDPR-sensitive data
- Company confidential
- Strategic information
- Financial and contract data
- Custom rules

Each row should show:

- Risk type
- Masked found value
- Token to be used
- Location
- Confidence
- Action

Example row:

| Risk type | Found value | Token | Location | Confidence | Action |
| --- | --- | --- | --- | --- | --- |
| Person | `Sarah M...` | `[PERSON_00001]` | Paragraph 1 | High | Shield |
| Email | `sarah...@...` | `[EMAIL_00001]` | Paragraph 1 | High | Shield |
| Strategy | `Project L...` | `[PROJECT_00001]` | Paragraph 1 | Rule match | Shield |

The found value should be masked by default. Users may reveal a single value if they need to verify it. Reveals should be local-only and never logged.

### Step 3: Explain what Cloakroom is doing

The UI must show progress in plain language:

- `Reading content locally`
- `Finding personal and confidential data`
- `Replacing sensitive values with reversible tokens`
- `Saving restore map to encrypted local vault`
- `Checking that no original sensitive values remain in AI-safe output`

The demo should visibly show each step completing.

### Step 4: Create AI-safe version

Button:

```text
Create AI-Safe Version
```

After click:

- Right pane fills with tokenized text.
- Header changes to `AI-safe version - safe to paste`.
- Button appears: `Copy AI-Safe Text`.
- The status badge shows `Safe to paste into AI`.

Summary metrics:

- `18 sensitive items replaced`
- `18 mappings stored locally`
- `0 original values in AI-safe output`
- `Encrypted vault updated`
- `Audit event created`

### Step 5: Show what leaves the machine

Dedicated proof panel:

Title:

```text
What the AI sees
```

Content:

- Only tokenized text.
- No raw names, emails, phone numbers, customer names, strategy names, or pricing terms.

Adjacent panel:

Title:

```text
What stays local
```

Content:

- Original sensitive values
- Token mapping
- Vault key
- Restore authority
- Audit metadata

This is the buyer proof moment. IT should be able to point to the screen and say: "The AI only sees this side."

### Step 6: Send to AI

The demo can use a simulated AI chatbot panel or a real browser/chatbot in a controlled environment.

Recommended for repeatable demos:

- Use a simulated AI response panel inside the demo.
- Label it clearly as `AI response simulation`.
- Optionally include a button `Open in ChatGPT` for live demos, but the core demo should not depend on external network or model behavior.

Example AI prompt:

```text
Summarize the risks in this escalation and draft a professional client response.
```

The AI-safe input should contain only tokens.

### Step 7: Restore AI response

User pastes the AI response into a restore pane.

Restore pane status:

- `17 known tokens found`
- `17 verified`
- `0 changed`
- `Ready to restore`

Button:

```text
Restore Original Values
```

After restore:

- Restored response appears.
- Header says `Restored locally`.
- Status says `No data sent online during restore`.

### Step 8: Show fail-closed protection

The demo must include one deliberate failure.

Scenario:

- The AI response changes `[PERSON_00001]` into `[PERSON_001]`.
- Cloakroom attempts restore.
- Cloakroom blocks restoration.

Failure state:

```text
Restore blocked
1 token was changed or invented.
Expected: [PERSON_00001]
Found: [PERSON_001]
No partial restore was created.
```

The screen should be calm and clear, not scary. The buyer should understand that Cloakroom refuses to guess.

## 10. IT Trust Center

The demo should include an IT-oriented tab called:

```text
Trust Center
```

Purpose: Show control, auditability, and local-first architecture.

Sections:

### Workspace status

- Workspace name
- Vault status
- TTL countdown
- Restore mappings count
- Last shield event
- Last restore event

### Local-only proof

- `Original values stored locally`
- `Vault encrypted`
- `Master key in macOS Keychain`
- `No cloud sync`
- `No telemetry`

### Audit-safe report

Show metadata only:

- Timestamp
- Workspace ID
- Action: shielded, restored, blocked
- File hash
- Counts by category
- Integrity status

Do not show:

- Original values
- Reversible tokens
- Raw filenames if filenames may contain sensitive data
- Clipboard contents

### Policy preview

Show rules in plain language:

- `Always shield PII`
- `Always shield customer names`
- `Always shield project codenames`
- `Always shield pricing terms`
- `Require review before AI-safe copy`
- `Expire vault after 24 hours`

## 11. Admin And Policy Demo Requirements

The demo should show that IT can define or review custom confidential data categories.

Minimum demo rules:

- Customer names
- Project codenames
- Contract values
- Pricing exceptions
- Strategy phrases

Example custom rule display:

| Rule | Example match | Token family | Status |
| --- | --- | --- | --- |
| Project codenames | `Project Lantern` | `[PROJECT_00001]` | Active |
| Pricing terms | `18 percent discount` | `[PRICING_TERM_00001]` | Active |
| Contract values | `$2.4M` | `[CONTRACT_VALUE_00001]` | Active |

## 12. UI Design Principles

The demo UI should be:

- Obvious
- Calm
- Local-first
- Visual
- Trustworthy
- Non-technical where possible
- Precise where security matters

The user should not need to understand cryptography.

The user should understand:

- Green means safe to paste.
- Lock means stays local.
- Token means reversible placeholder.
- Vault means restore is possible.
- Red means Cloakroom refused to guess.

## 13. Required Screens

### Screen 1: Shield for AI

Required:

- Source input pane
- Detection review table
- AI-safe output pane
- Status rail
- Copy AI-safe text button
- Workspace/vault status

### Screen 2: Restore

Required:

- AI response paste area
- Token verification summary
- Restore original values button
- Restored output pane
- Fail-closed error state

### Screen 3: Trust Center

Required:

- Workspace status
- Vault status
- TTL status
- Audit-safe event list
- Policy preview
- Local-only proof panel

### Screen 4: Demo Controls

Required for presenter:

- Load clean demo sample
- Load mutated-token failure sample
- Reset demo workspace
- Export audit-safe report

## 14. Functional Requirements

### FR1: Load demo sample

The demo must provide one-click sample content.

Acceptance criteria:

- User clicks `Use Demo Sample`.
- Original content appears.
- No external file setup is required.

### FR2: Detect sensitive content

Cloakroom must identify and categorize sensitive values.

Acceptance criteria:

- PII is detected.
- GDPR-relevant personal data is highlighted.
- Confidential business terms are detected through custom demo rules.
- Strategic phrases are detected through custom demo rules.
- Detected values are masked by default in the review UI.

### FR3: Create AI-safe output

Cloakroom must replace sensitive values with readable reversible tokens.

Acceptance criteria:

- AI-safe output contains no raw sensitive demo values.
- Tokens preserve enough context for AI reasoning.
- Summary counts match the detection review.
- User can copy the AI-safe output.

### FR4: Store restore mappings locally

Cloakroom must store mappings in a local encrypted vault.

Acceptance criteria:

- UI shows encrypted local vault status.
- Demo can restore only while the local workspace/vault is available.
- No original values are placed in audit logs.

### FR5: Restore AI response

Cloakroom must restore original values after verifying tokens.

Acceptance criteria:

- Known tokens are detected.
- Token integrity is checked.
- Original values are restored locally.
- Output is never partially restored.

### FR6: Block unsafe restore

Cloakroom must fail closed when tokens are changed, invented, or dropped.

Acceptance criteria:

- Mutated-token demo blocks restore.
- UI explains what happened.
- No partial restored output is created.

### FR7: Show IT proof

Cloakroom must provide a trust center view.

Acceptance criteria:

- IT can see what left the machine.
- IT can see what stayed local.
- IT can see audit-safe metadata.
- IT can see vault TTL and local-only status.

## 15. Non-Functional Requirements

### Demo clarity

- A first-time IT viewer should understand the core workflow in under 60 seconds.
- A non-technical employee should understand what button to press next.
- The UI should avoid jargon unless it is in the Trust Center.

### Performance

- Demo sample shield operation should complete in under 3 seconds.
- Restore operation should complete in under 2 seconds.
- UI progress states should appear even if processing completes quickly.

### Security posture

- Original values must remain local.
- Audit output must not contain original values.
- Demo should visibly distinguish local content from AI-safe content.
- Restore must fail closed on token mismatch.

### Reliability

- Demo reset should return the workspace to a known clean state.
- Demo should not depend on live AI availability.
- Presenter should be able to run the demo offline using the simulated AI response.

## 16. Current Code Reuse

Existing Cloakroom code can support much of the demo:

- Core anonymize/restore pipeline
- Token generator
- Encrypted vault
- Workspace manager
- Clipboard operations
- Gradio UI
- Textual TUI
- Swift menu bar scaffold
- Audit and sanitization report code
- Hallucination/mutated-token detection
- CSV/XLSX/DOCX/TXT/MD support
- PDF input conversion
- License/edition policy checks
- Wrapper state machine and IPC foundation

## 17. Demo-Specific Gaps To Build

### Gap 1: Polished demo UI

Current UI surfaces exist, but the demo needs a purpose-built "Shield for AI" experience with clear before/after/proof panels.

### Gap 2: Confidential and strategic information detection

Current code is strongest for PII. The demo needs custom rules for:

- Customer names
- Project codenames
- Contract values
- Pricing terms
- Strategy phrases

### Gap 3: IT Trust Center

Current reporting exists, but the demo needs an easy visual Trust Center that proves:

- What AI sees
- What stays local
- Vault status
- Audit-safe event history

### Gap 4: Demo reset and sample controls

Presenter controls are needed for repeatable demos:

- Reset workspace
- Load clean sample
- Load mutated-token failure sample
- Export audit-safe report

### Gap 5: Report safety hardening

The demo should not expose raw file paths or sensitive filenames in audit/report views.

### Gap 6: Packaged experience

For IT review, the demo should ideally run as:

- A local macOS app, or
- A polished local web app bound to `127.0.0.1`

The demo should not require the viewer to run terminal commands.

## 18. Recommended Implementation Approach

### Phase 1: Demo web UI

Build a polished local web UI first because it is fastest to iterate and easiest to show.

Deliverables:

- `Shield for AI` screen
- `Restore` screen
- `Trust Center` screen
- Built-in demo sample
- Mutated-token failure sample
- Demo reset

### Phase 2: Connect to existing engine

Use existing Python engine functions for:

- Detection
- Tokenization
- Vault persistence
- Restore
- Hallucination/mutation blocking
- Audit/report creation

### Phase 3: Add confidential demo rules

Add demo rule support for confidential/strategic categories.

Initial implementation can be deterministic pattern/dictionary matching for the sample.

### Phase 4: Package for IT review

Package as one of:

- Local web demo launched from script/app
- Mac menu bar app with embedded local UI
- Signed Mac app if timing allows

## 19. Success Criteria

The demo is successful if an IT reviewer can answer "yes" to all of these:

- I understand what problem Cloakroom solves.
- I can see exactly what data the AI receives.
- I can see that original values stay local.
- I can see that the output is still useful for AI.
- I can see how restoration works.
- I can see that Cloakroom fails closed instead of guessing.
- I can imagine employees actually using this.
- I can imagine IT deploying or piloting this.

## 20. Out Of Scope For This Demo

- Full enterprise DLP policy administration
- Network interception
- Browser extension
- Enterprise KMS
- Shared team vaults
- Cloud telemetry
- Live production license purchase flow
- Full legal/compliance certification
- Full mobile support
- Windows support

## 21. Open Questions

1. Should the demo be built first as a polished local web app or as a native Mac app?
2. Should live ChatGPT be part of the demo, or should the default demo use a simulated AI response?
3. Which confidential categories should be first-class in v1 versus demo-only?
4. Should IT be able to upload a list of confidential terms during the demo?
5. Should the demo show employee-level audit events, or should it stay workspace-level to avoid surveillance concerns?
6. Should report exports be part of the first demo or only shown in the Trust Center?

## 22. Recommended First Build

Build the first demo as a local browser-based app using the existing Python engine. It should run locally, bind only to `127.0.0.1`, and present the three-screen workflow:

1. `Shield for AI`
2. `Restore`
3. `Trust Center`

This gets the buyer story right quickly. After that, move the same workflow into the native Mac app surface.

