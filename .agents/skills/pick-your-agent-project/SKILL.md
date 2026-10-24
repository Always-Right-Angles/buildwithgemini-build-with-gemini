---
name: pick-your-agent-project
description: Interactively help a workshop participant decide on and design what agent to build. Use when the user is choosing a project, brainstorming an agent idea, says "I don't know what to build" or "what should I make", OR asks to design/plan/"help me design"/"help me make"/"help me build" a specific agent idea (e.g. "help me design a travel planner agent", "help me make a recipe assistant", "design my agentic application") BEFORE any code is scaffolded — this is the planning/brief step, not implementation. Also use when they want to check whether their idea will actually exercise the workshop's Google tools (memory/sessions, function tools, storage + A2UI, image generation, code sandbox). Guides a domain choice and a tool-coverage gut-check, then writes a short project brief. Don't use for implementing or coding the agent itself (that comes after the brief).
---

# Pick your agent project

Help a workshop participant choose *what* agent to build for the rest of the lab.
Your job is to run a short, interactive brainstorm (aim for 5-10 minutes of
back-and-forth), land on a concrete idea, sanity-check that it will exercise the
Google tools the workshop teaches, and hand them a short **project brief** they
can build against.

This is a *facilitation* task, not a build task. Do NOT write agent code, scaffold
a project, or install anything here. Just help them decide.

## The one idea to convey: the tools define the shape

The scariest version of "what should I build?" is a blank page. It isn't blank.
The tools this workshop teaches implicitly define the *shape* of a good project.
Reverse-engineer from the tools and the design gets easy:

| The tool they'll learn | ...means the agent should have |
| --- | --- |
| Sessions & Memory | something worth **remembering** about the user (preferences, history) |
| Function tools | something real it can **do or look up**, not just chat |
| Storage + A2UI | a **collection/catalog** of things that render nicely as cards/tables |
| Image generation | a domain where **generating a visual** is useful |
| Code sandbox | an occasional need to **compute** something |

So the archetype is: *a stateful conversational agent with a catalog of things it
can show you, act on, and generate visuals for.* (That's why the sample
"marketplace / greenhouse" agent was chosen — it hits every tool naturally.)

The participant is NOT limited to a marketplace. Any domain works as long as it
clears the minimum bar below. Encourage a domain they actually care about — looser
guardrails, more fun, more motivation.

## The tool-coverage gut-check

Walk them through these five questions about their idea. Frame them as prompts,
not a test:

1. **Memory** — What does it remember about *you* between turns/sessions?
2. **Tools** — What can it actually *do* or *fetch* (a real action or lookup)?
3. **Catalog** — What collection of things does it have? (renders great as cards/tables)
4. **Visuals** — What image could it generate for you?
5. **Compute** — Does it need to calculate or run code? If so, the code sandbox fits; if not, skip it.

**Minimum bar (must clear to be a good project):** solid answers to **#1 and #2**.
Everyone builds these. If an idea can't say what it remembers
or what it *does*, it's a chatbot, not an agent — nudge them to reshape it.

**Also recommended:** #3 and #4. The lab walks everyone through storage, A2UI, and
image generation, so it helps if the idea has a catalog and something to visualize.
**Agent-specific:** #5. Only plan on the sandbox if the idea needs to compute
something. If their idea only clears the minimum, that's fine — just tell them
which parts of the lab will be a natural fit and which won't.

## How to run the brainstorm

Ask a few questions at a time and adapt — don't dump the whole checklist at once.

1. **Seed a domain.** Ask what they're into (a hobby, a job pain, a game, a
   domain they know well). If they're stuck, offer the menu below as inspiration.
2. **Shape it into the archetype.** Restate their idea as "a conversational agent
   that helps someone [do X] with a collection of [Y]." Get them to a one-liner.
3. **Run the gut-check.** Go through the five questions. Fill in answers together.
4. **Check the minimum bar.** Confirm #1 and #2 are solid. If not, tweak the idea
   (usually: give it a real action, or something to remember) rather than
   discarding it.
5. **Map the stretch menu.** Tell them which agent-specific and stretch options
   (code sandbox, a live external API like Maps, video with Omni, Cloud Trace) fit
   their domain — this is what they'll reach for after the recommended steps are done.
6. **Write the spec file.** Save the brief as `project_brief.md` in the workspace
   (format below) — the build step points `agents-cli` at this file.

Keep them moving. Perfect is the enemy of started — if they have a viable idea
that clears the bar, lock it in and let them refine while building.

## Domain menu (inspiration, not a menu to pick from exactly)

Offer these only if they're stuck. Each is known to exercise the tools well:

- Travel concierge (remembers your prefs; looks up/plans trips; itinerary cards)
- Personal chef / recipe agent (dietary memory; recipe lookup; dish images)
- Fantasy character or party builder (remembers your party; stat lookups; portraits)
- Real-estate / apartment finder (budget & prefs memory; listing search; listing cards)
- Collector game, Pokemon-style (your collection; catch/trade actions; creature art)
- D&D dungeon master (campaign memory; dice/rules; scene images)
- Workout / gear coach (goals memory; plan lookup; progress calc in sandbox)
- Plant-care / greenhouse shop (the sample — care history; inventory; plant images)

## Output: write the spec file

When the brief is filled in, **write it to a file named `project_brief.md`** in the
workspace (don't just print it to chat). The build step points `agents-cli` at
this file, so it's the handoff between deciding and building. Use this format:

```
# My agent: <name>
One-liner: A conversational agent that helps <who> <do what> with a catalog of <what>.

Tool coverage:
- Memory: <what it remembers>
- Tools: <the real action(s)/lookup(s)>
- Catalog/UI: <collection to render as cards/tables, or "n/a">
- Image gen: <what visual, or "n/a">
- Sandbox: <what computation, or "n/a">

Recommended for every project: memory, storage, tools, image generation, A2UI
Agent-specific / stretch (pick what fits): <e.g. code sandbox for calculations, a live external API like Maps, video with Omni, Cloud Trace>
```

## After you write the brief: STOP

Writing `project_brief.md` is the end of this skill. Do **not** build, scaffold,
install, or write any agent code — and do **not** *offer or ask* to ("want me to
build it now?", "shall I implement this?", "ready to scaffold?"). Offering to
build is still going off-script: the lab has the participant build the agent
incrementally in the steps that follow, and jumping ahead defeats the point.

End your turn by telling them the brief is saved and to continue with the next
step of the lab (they can edit `project_brief.md` first if they'd like). Then stop.
