# PRD Generation Workflow

This document records the standard operating procedure for generating PRDs and implementation plans in the `prescient` project. 

Whenever asked to **write a PRD**, the AI assistant must follow this exact workflow:

## Phase 1: `superpowers:brainstorming`
Before writing anything, deeply brainstorm the requirement:
- Research the existing codebase to understand what's already built and how the new feature fits.
- Review related PRDs in `docs/prd/` to understand dependencies and boundaries.
- Identify open questions, design tradeoffs, and edge cases.
- Map out functional requirements, acceptance criteria, and non-goals.

## Phase 2: Write the PRD
Write the PRD into `docs/prd/` matching the established conventions:
- **Naming**: `{section}-{category}-{requirement-id}-{slug}-prd.md` (e.g., `04-data-r4-7-earnings-call-transcript-summarization-prd.md`)
- **Structure**: Follow the existing style — `# PRD: R{X}.{Y} Title`, then sections like Objective/Summary, Background, Functional Requirements (`R{X}.{Y}.{Z}`), code examples with Pydantic models/Python protocols, architecture diagrams in ASCII, Acceptance Criteria, Non-Goals, Open Questions, and optionally Product FAQ.
- **Tone**: Technical, deterministic, prescient-specific language (Claude boundaries, broker-free, network-free, etc.).

## Phase 3 (Optional): `sc:workflow` → Build Task List
If requested, generate a **step-by-step implementation plan** into `docs/superpowers/plans/` matching the style of the existing plans:
- **Naming**: `{date}-{requirement-id}-{slug}.md`
- **Structure**: Goal, PRD Check, File Structure (Modify/Create/Do Not Modify), then numbered Tasks with checkboxed Steps, bash verification commands, an Acceptance Checklist, and Assumptions.
- **TDD Flow**: Each task should follow a Test-Driven Development flow (failing tests → implementation → verification).
