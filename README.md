# Epic Games Friends List Remover (Rich TUI)

> A fast, keyboard-driven terminal app to review your Epic friends, tick multiple entries with `X`, and remove them in one go — with a compact Rich UI that doesn’t stretch across your console.

---

<!--
  📸 Screenshot / GIF placeholder
  Replace the image below with your own screenshot or GIF.
  Put the image file in /docs (recommended) then update the src path.
-->
<p align="center">
  <img src="https://i.imgur.com/RReuSEY.png" alt="Epic Games Friends List Remover - Screenshot" width="760">
</p>

---

<p align="center">
  <img src="https://i.imgur.com/yRBJ6TE.png" alt="Epic Games Friends List Remover - Screenshot" width="760">
</p>

---

## ✨ Features

- **Simple login flow** — shows a device-auth link, then you press Enter when done.
- **Clean, compact UI** — Rich-powered table with a fixed, readable width.
- **Fast lookups** — resolves display names in **batches of 100** (handles odd totals like 246).
- **Keyboard controls**:
  - **↑ / ↓**: Move selection
  - **X**: Toggle friend selection
  - **Enter**: Confirm removal
  - **Q**: Cancel
- **Progress feedback** during removals.
- **Session cleanup** on exit.

---

## 🧰 Requirements

- **Python 3.8+**
- Packages: `requests`, `rich`, `readchar`

Install:
```bash
pip install --upgrade pip
pip install requests rich readchar
