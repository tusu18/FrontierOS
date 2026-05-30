# Manual test — Browser-local Personal Memory Graph

The personal graph lives in IndexedDB (via Dexie) in the browser, so it must be
tested manually in a real browser session.

## Prerequisites
- Server running: `python run.py`
- Open: http://localhost:8000/app
- Sign in (or use an access code).

## Steps

1. **Save persists across refresh**
   - Go to **Daily Papers**.
   - Click **Save** on a paper.
   - Refresh the page (Cmd/Ctrl+R).
   - Go to **Settings → My Personal Memory**.
   - Expect: *Saved papers* count increased and persisted.

2. **Ignore deprioritizes**
   - On a paper card, click **Ignore**.
   - Go to **For You**.
   - Expect: the ignored paper is hidden / not shown in the feed.

3. **More like this changes ranking**
   - Click **More like this** on a paper whose topic you care about.
   - Refresh **For You**.
   - Expect: papers sharing that topic rank higher (look for the
     "matches your saved topics" reason chip).

4. **Export**
   - Settings → My Personal Memory → **Export JSON**.
   - Expect: a `researchradar-personal-memory.json` file downloads with
     `entities`, `edges`, `interactions` arrays.

5. **Clear**
   - Settings → My Personal Memory → **Clear memory** → confirm.
   - Expect: all counts reset to 0; saved/ignored state gone after refresh.

## Pass criteria
- [ ] Save persists after refresh
- [ ] Ignore hides/deprioritizes the paper
- [ ] More-like-this reorders the feed
- [ ] Export returns valid JSON
- [ ] Clear resets the graph
