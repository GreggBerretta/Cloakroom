# Cloakroom Killer Demo — Setup Guide

For a Cloakroom teammate getting the demo running on their own Mac for the first time. Total setup time: about 15 minutes.

Once the demo is running, the [Cloakroom Demo Runbook](Cloakroom_Demo_Runbook.md) covers the presenter flow.

---

## What you need

- A Mac running macOS (Cloakroom does not support Windows or Linux yet).
- Terminal access — Spotlight (`Cmd+Space`) → type "Terminal" → Enter.
- About 15 minutes the first time. After that, launching the demo is one command.

---

## Step 1 — Install Homebrew (skip if you already have it)

Homebrew is how we install everything else. In Terminal, paste this and press Enter:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Follow the prompts. When it finishes, close Terminal and open it again so the new command is available.

To check it worked: `brew --version` should print a version number.

---

## Step 2 — Install `git` and `uv`

`git` downloads the code. `uv` is the Python package manager Cloakroom uses.

```bash
brew install git uv
```

To check it worked: `git --version` and `uv --version` should each print a version number.

---

## Step 3 — Get the code

Pick a folder where Cloakroom should live. The example below puts it under your home folder.

```bash
cd ~
git clone https://github.com/GreggBerretta/Cloakroom.git
cd Cloakroom
```

> **As of right now, the killer-demo work lives on a feature branch, not on `main`.** Once the team merges it, this extra step goes away. Until then, run:
>
> ```bash
> git checkout feature/demo-rules-and-il-entities
> ```
>
> If `git checkout` says the branch doesn't exist, the merge has happened — you're already good and can skip this step.

---

## Step 4 — Install Python dependencies

This downloads everything Cloakroom needs. It can take 3–5 minutes the first time.

```bash
uv sync --extra dev
uv run python -m ensurepip
```

You'll see lots of `Downloading…` lines. That's normal.

---

## Step 5 — Install language models

Cloakroom needs language models to recognize names, addresses, phone numbers, and so on.

```bash
uv run python -m spacy download en_core_web_lg
uv run python -m spacy download he_core_news_sm
```

If the Hebrew model fails to download (it's hosted by a third party that occasionally has hiccups), the multilingual fallback is also fine for the demo:

```bash
uv run python -m spacy download xx_ent_wiki_sm
```

---

## Step 6 — Sanity check

Run the test suite to confirm everything is wired up. You should see a line like `324 passed` near the end:

```bash
uv run pytest -q
```

If you see a different number that says `passed`, that's fine — teammates may have added tests since this guide was written. If you see anything red (`FAILED`, `ERROR`), stop here and message the team before going further. Don't try to "fix" it yourself.

---

## Step 7 — Launch the demo

```bash
uv run cloakroom demo
```

Your default browser will open to `http://127.0.0.1:8765/` and you'll see the Cloakroom demo UI.

To stop the demo, press `Ctrl+C` in the Terminal window where you started it.

That's it. From now on, launching the demo is just `uv run cloakroom demo` from inside the `~/Cloakroom` folder.

---

## What you can try in the demo

### The three bundled samples

Use the **sample switcher** in the demo to load:

1. **English Customer Escalation** — A customer-success memo with a name, email, phone number, address, contract value, pricing exception, customer ID, project codename, and strategy phrases. This is the canonical demo input the PRD is built around.

2. **Hebrew / Israeli sample** — Hebrew text containing an Israeli ID number (`Teudat Zehut`), Israeli phone, address, and Israeli bank account.

3. **Mixed (English + Hebrew)** — Both languages in one document. Good for showing right-to-left rendering and that token namespaces don't collide between languages.

### Your own input

You can also:

- **Paste your own text** directly into the source pane on the left.
- **Drag and drop a file** onto the source pane (`.txt` or `.md`).
- **Click the file picker** in the source pane to load a local `.txt` or `.md` file.

> ⚠️ **Don't paste real customer, employee, or production data into the demo.** This setup is a self-contained demo workspace meant for sample text only. A real production deployment is configured differently.

### Supported file types

For the demo workflow specifically, paste/upload supports `.txt` and `.md`. The wider Cloakroom engine also handles `.csv`, `.xlsx`, `.docx`, and `.pdf` (input-only), but those run from the command line, not from this demo UI.

---

## The three screens

1. **Shield for AI**
   Paste or load text on the left, click **"Create AI-Safe Version"**. You'll see:
   - The original on the left (labeled "stays local").
   - The tokenized AI-safe version on the right (labeled "safe to paste").
   - A detection-review table showing what was found, what it became, and where.
   - Two proof panels: "What the AI sees" / "What stays local".

2. **Restore**
   Paste an AI response (still containing the tokens) into the restore pane and click **"Restore Original Values"** — your original text comes back.
   The **"Load Failure Sample"** button shows what happens when an AI mutates a token (e.g., `[PERSON_00001]` → `[PERSON_001]`). Cloakroom blocks the restore instead of guessing, with a calm error message.

3. **Trust Center**
   Workspace status, vault status, mapping counts, audit-safe report rows, policy preview. Useful for showing IT-side audiences the proof story.

---

## Presenter controls (bottom of screen)

- **Use Demo Sample** — Loads the currently selected sample text.
- **Load Failure Sample** — Loads the canned mutated AI response so you can demo the fail-closed path.
- **Reset Demo** — Returns the workspace to a known clean state. Use this between practice runs.
- **Export Audit JSON** — Saves the audit-safe report as JSON for IT-style review.

---

## If something goes wrong

| Problem | Fix |
|---|---|
| `command not found: uv` | Run `brew install uv` and open a new Terminal window. |
| `command not found: brew` | Step 1 didn't finish. Re-run the Homebrew installer. |
| `spacy.cli.download` errors | Your Wi-Fi may have hiccupped mid-download. Re-run the same `spacy download` command. |
| Browser doesn't open automatically | Open `http://127.0.0.1:8765/` manually in any browser. |
| `Address already in use` on port 8765 | Run `uv run cloakroom demo --port 8766` (or any free port). |
| Demo UI looks broken | Try Chrome instead of Safari, or resize the window. |
| Demo seems "stuck" on Shield | Wait 30 seconds — the very first run loads language models. After that it's fast. |
| Anything else | Screenshot the screen, copy the Terminal output, ping the team. |

---

## Quick reference (after first-time setup)

To run the demo on any future day:

```bash
cd ~/Cloakroom
uv run cloakroom demo
```

To stop: `Ctrl+C` in the Terminal window.

To get the latest version of the code:

```bash
cd ~/Cloakroom
git pull
uv sync --extra dev
```
