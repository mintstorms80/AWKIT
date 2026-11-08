# Security policy

## What the kit is, and is not

`awkit` is a **protocol plus a small stdlib engine** that makes a strong model and a cheap model work in shifts. It
detects drift and accidents — hashes, tripwires, an append-only ledger, a test-count floor. It is **not a sandbox**:
anything with file access can rewrite its own state, and the kit makes that loud, not impossible. Do not describe it as
a security boundary.

## Reporting a problem

Open a private security advisory on GitHub (Security tab -> "Report a vulnerability") instead of a public issue when the
problem is a bypass: a way to edit a frozen file without `integrity` noticing, to make `gate` print `GATE OK` without
running the tests, or to make `audit` pass with a write outside the card's `OWNS`.

## Secrets in a project

`aw.py audit` scans changed files for key-shaped strings and for a `.env` file; it reports them, it cannot un-leak them.
Never put credentials in `.hermes/plans/`, in cards, or in a `kit.env`. Use environment variables.
