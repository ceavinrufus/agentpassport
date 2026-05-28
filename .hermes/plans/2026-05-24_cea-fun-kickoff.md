# cea.fun — Kickoff Plan

## Goal
Initialize the cea.fun project: repo, design system, and build Game 1 (Spend Indonesia's Budget).

## Assumptions
- Domain: cea.fun (already owned or to be registered)
- Stack: Next.js 14 App Router + Tailwind + Vercel + Supabase
- Repo: github.com/ceavinrufus/cea-fun (to be created)
- Build order: Game 1 → Game 2 → Game 3

---

## Phase 1 — Repo & Project Init

### Steps
1. Create GitHub repo `ceavinrufus/cea-fun` (public)
2. Scaffold Next.js 14 app:
   ```bash
   npx create-next-app@latest cea-fun \
     --typescript --tailwind --app --src-dir --import-alias "@/*"
   ```
3. Clean boilerplate — remove default page content
4. Set up folder structure:
   ```
   src/
     app/
       page.tsx              ← homepage / game hub
       games/
         spend-budget/
           page.tsx
         token-price/
           page.tsx
         prompt-archaeology/
           page.tsx
     components/
       ui/                   ← shared UI primitives
       games/                ← per-game components
     lib/
       utils.ts
   public/
     games/                  ← static assets per game
   ```
5. Init git, push to GitHub
6. Connect to Vercel — import repo, auto-deploy on push

---

## Phase 2 — Design System

### Decisions to make
- **Font**: Something playful but readable — suggest `Space Grotesk` (headings) + `Inter` (body)
- **Colors**: Dark base (like neal.fun) — near-black bg, bright accent per game
  - Spend Budget: 🟢 Indonesian green/red palette
  - Token Price: 🔵 cool blue
  - Prompt Archaeology: 🟣 purple/violet
- **Game card layout**: Grid on homepage, each card has: emoji, title, tagline, "Play →" CTA

### Deliverables
- `tailwind.config.ts` — custom theme (colors, fonts)
- `src/app/globals.css` — base styles
- `src/app/page.tsx` — homepage with game cards
- `src/components/ui/GameCard.tsx` — reusable card component

---

## Phase 3 — Game 1: Spend Indonesia's Budget

### Mechanic (detailed)

**Premise:** You have Rp 3,300,000,000,000,000 (3,300 Trillion). Spend it all.

**Gameplay loop:**
1. Grid of purchasable items, each with a name, icon/image, and price
2. Click item to buy (+1), click again to buy more, long-press or right-click to sell
3. Real-time counter at top: budget remaining (animated drain)
4. Item quantity badges update instantly
5. End condition: budget ≤ 0 → end screen
6. End screen: summary of what you "built/bought" + share button

**Items list (v1, ~20 items):**

| Item | Price (Rp) | Category |
|---|---|---|
| Nasi Padang (1 portion) | 30,000 | 🍚 Food |
| Indomie (1 pack) | 3,500 | 🍜 Food |
| Grab ride (Jakarta cross-city) | 80,000 | 🚗 Transport |
| KRL monthly pass | 350,000 | 🚆 Transport |
| Free school meals (1 child, 1 year) | 1,080,000 | 🏫 Education |
| Beasiswa LPDP (1 person) | 500,000,000 | 🎓 Education |
| Puskesmas (1 community clinic) | 2,000,000,000 | 🏥 Health |
| RS Type C (1 hospital) | 50,000,000,000 | 🏥 Health |
| MRT extension (1 km) | 600,000,000,000 | 🚇 Infrastructure |
| Toll road (1 km) | 100,000,000,000 | 🛣️ Infrastructure |
| F-16 fighter jet | 900,000,000,000 | ✈️ Defense |
| KRI frigate | 2,500,000,000,000 | ⚓ Defense |
| Bansos (1 family, 1 year) | 3,600,000 | 💰 Social |
| Free wifi (1 village) | 50,000,000 | 📡 Digital |
| Starlink terminal | 7,800,000 | 📡 Digital |
| IKN land plot (1 ha) | 10,000,000,000 | 🏙️ IKN |
| IKN Presidential Palace | 900,000,000,000 | 🏙️ IKN |
| PSN (1 national strategic project) | 5,000,000,000,000 | 🏗️ Mega |
| Subsidi BBM (1 year) | 170,000,000,000,000 | ⛽ Subsidy |
| Bayar utang negara | 800,000,000,000,000 | 💸 Debt |

**Scoring / end screen:**
- Show count of each item bought
- One-liner summary e.g. "You fed 3M kids for a year, bought 2 jets, and still owed debt."
- Share button: copies text card to clipboard

**No backend needed for v1** — pure client state. Supabase only if leaderboard added later.

### Files to create
- `src/app/games/spend-budget/page.tsx` — main game page
- `src/components/games/spend-budget/ItemGrid.tsx` — purchasable items grid
- `src/components/games/spend-budget/BudgetCounter.tsx` — animated top counter
- `src/components/games/spend-budget/EndScreen.tsx` — result + share
- `src/lib/spend-budget/items.ts` — item data + prices

---

## Phase 4 — Game 2: Token Price is Right

### Mechanic (detailed)

**Premise:** Paste any text. Guess what it costs to run on GPT-4o, Claude 3.5 Sonnet, and Gemini 1.5 Pro.

**Gameplay loop:**
1. Textarea — paste any text
2. Model selector (multi-select, default: all 3)
3. Player enters cost guess (slider or input, range $0.00001 – $1.00)
4. Hit "Submit Guess"
5. Reveal: actual cost per model (calculated client-side via tokenizer)
6. Score = inverse of percentage error (100% = exact, 0% = way off)
7. Leaderboard: most expensive texts ever submitted (Supabase)

**Tokenizer approach (no API calls):**
- Use `tiktoken-wasm` or `js-tiktoken` for GPT-4o (cl100k)
- Approximate Claude + Gemini with same token count ± small multiplier
- Prices hardcoded (updated manually when pricing changes)

**Pricing table (as of 2025):**

| Model | Input $/1M tokens | Output $/1M tokens |
|---|---|---|
| GPT-4o | $2.50 | $10.00 |
| Claude 3.5 Sonnet | $3.00 | $15.00 |
| Gemini 1.5 Pro | $1.25 | $5.00 |

(Output = 0 for "how much to read this text" mode)

### Files to create
- `src/app/games/token-price/page.tsx`
- `src/components/games/token-price/TextInput.tsx`
- `src/components/games/token-price/GuessSlider.tsx`
- `src/components/games/token-price/CostReveal.tsx`
- `src/lib/token-price/tokenizer.ts` — js-tiktoken wrapper
- `src/lib/token-price/pricing.ts` — model pricing constants

---

## Phase 5 — Game 3: Prompt Archaeology (deferred)

Needs:
- Curated image dataset (Midjourney/Flux images + known prompts)
- OpenAI embeddings API call on submission
- Supabase to store scores

Plan this separately once Games 1–2 are live.

---

## Open Questions
- [ ] Is cea.fun domain registered? Who holds it?
- [ ] Supabase project created? Or create during Game 2 build?
- [ ] Public or private GitHub repo?
- [ ] Want a leaderboard from Day 1, or add post-launch?
- [ ] Items list for Spend Budget — any must-haves or removals?

---

## Build Order Summary

```
Week 1   Phase 1 + 2   Repo init, design system, homepage
Week 2   Phase 3       Game 1: Spend Indonesia's Budget
Week 3   Phase 4       Game 2: Token Price is Right
Later    Phase 5       Game 3: Prompt Archaeology
```
