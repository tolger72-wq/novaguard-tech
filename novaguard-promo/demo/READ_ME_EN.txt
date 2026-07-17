═══════════════════════════════════════════════════════════
  NOVAGUARD PROMO ENGINE — DEMO PACKAGE
═══════════════════════════════════════════════════════════

Everything in this folder is for demo/presentation purposes.

QUICK START (without backend, visual demo only):
─────────────────────────────────────────────────────────
1. Double-click novaguard-admin.html → Admin panel opens
2. Double-click novaguard-display.html → Big screen opens
   (Move this screen to a second monitor/TV, go fullscreen - F11)

Both screens work even without a backend connection — they show
"Demo Mode", tabs can be browsed, button animations work.


RUNNING THE FULL SYSTEM (real data + automatic draws):
─────────────────────────────────────────────────────────
1. Docker Desktop must be installed (docker.com/products/docker-desktop)
2. Open a terminal, go into the novaguard-promo folder
3. Run these commands:

   cp .env.example .env
   ./quickstart.sh

4. After a few minutes the system is ready:
   - API:        http://localhost:8000
   - API Docs:   http://localhost:8000/docs
   - Admin Panel: open admin.html, click "Connect"
   - Display:    open display/display.html, enter the API
                 address in the "Operator" panel, click Connect

5. quickstart.sh automatically loads 10 demo players and 3 sample
   draws — you'll see them immediately in the admin panel.


FILE GUIDE:
─────────────────────────────────────────────────────────
novaguard-admin.html      → Admin panel (single file, double-click)
novaguard-display.html    → Big screen / TV (single file, double-click)
ornek-sertifika.pdf       → A real draw certificate example
novaguard-promo/          → Full source code (backend + tests)

  novaguard-promo/README.md         → Technical documentation
  novaguard-promo/quickstart.sh     → One-command setup
  novaguard-promo/branding.json     → Casino logo/name/color settings
  novaguard-promo/scripts/          → Casino integration examples
  novaguard-promo/tests/            → 38 automated tests (all passing)


FOR QUESTIONS:
─────────────────────────────────────────────────────────
README.md explains API usage, casino integration, and the
tax declaration flow in detail.

═══════════════════════════════════════════════════════════

═══════════════════════════════════════════════════════════
  MOVING VIA USB / FLASH DRIVE — RUNNING WITHOUT INTERNET
═══════════════════════════════════════════════════════════

If you want to put this project on a USB drive and run it on a
computer with no internet (including the casino's own server),
there are TWO STAGES:

STAGE 1 — Preparation (ONLY ONCE, on a computer with internet)
─────────────────────────────────────────────────────────
1. On a computer that has Docker Desktop installed and internet
   access, open the novaguard-promo folder
2. In the terminal, run:

     python3 prepare_offline_package.py

3. This takes a few minutes and creates a folder called
   "docker-images"
4. Copy the WHOLE novaguard-promo folder (including docker-images)
   onto the USB drive


STAGE 2 — Running (on the target computer, NO INTERNET NEEDED)
─────────────────────────────────────────────────────────
1. Copy the novaguard-promo folder from the USB onto the computer
2. Docker Desktop must be installed on that computer (this
   installation step also needs internet, but AFTER it's
   installed, NovaGuard itself runs without internet)
3. In the terminal, inside the folder, run:

     python3 load_offline_images.py

4. The system starts automatically — you can open admin.html and
   display.html as usual


SUMMARY — WHAT NEEDS INTERNET, WHAT DOESN'T?
─────────────────────────────────────────────────────────
✓ admin.html / display.html / kiosk.html  → NEVER needs internet
✓ Installing Docker Desktop                → Needs internet ONLY the first time
✓ prepare_offline_package.py               → NEEDS INTERNET (only once, on the prep computer)
✓ load_offline_images.py                   → NO INTERNET NEEDED (on the target computer)
