<!-- WRITER: ARCHITECT writes the questions; the AUTHOR answers with letters | copy to QUESTIONNAIRE_<date>.md | ONE batch, never a chat chain | delete this comment when sending -->
<!-- RULES: one question per ambiguity. Evidence = verbatim line + line number, every place that disagrees. 2-3 lettered options, cost INSIDE the option. DEFAULT = what the Architect does while OPEN; domain content has no default: the card stays BLOCKED/AUTHOR and nothing is written. Order by consequence, not by card id. Chat mode: <= 5 questions per call, current state first; a free-text reply is an answer (record as PROSE). Offer DOCX/PDF to a non-technical Author. -->
# Questionnaire <date> - {{PROJECT_NAME}}  (language: {{REPLY_LANG}})
Answer with ONE letter per question, or "skip". Nothing changes until you answer. Agents decide nothing of yours: domain content, money, secrets, commits, deletes.
Quotes come from: <file(s)>; numbers are line numbers.

## 1. <topic - the questions that change what the system records come first>
**Q1. <card / module id> - <ONE ambiguity>.**
`<file>:<line>`: "<verbatim>"   `<file>:<line>`: "<verbatim>" (they disagree)
 - A) <option> - cost: <what happens, e.g. the task becomes MANUAL / BLOCKED>  [DEFAULT]
 - B) <option> - cost: <...>
 - C) other: ______

## 2. Signature
**Q<last>. Who is answering?**
 - A) my own written confirmation (author confirmed)
 - B) <owner> answered for me (owner decided) - a clinical / legal sign-off still needs A
 - C) confirmed only for: ______

## Anything else?
One free line: anything not asked that the Author knows and the Architect should.

## What is NOT asked here
Technical choices the Architect settles alone: <where a file lives, naming, which tool runs it, ...>
