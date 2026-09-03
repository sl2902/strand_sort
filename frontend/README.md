# Strand Sort — Frontend

React + Vite + TypeScript + Tailwind UI for volunteers to scan donations, review
flagged items, and browse/edit inventory.

## Setup

```bash
cd frontend
npm install
cp .env.example .env   # adjust VITE_API_BASE_URL if the API isn't on localhost:8000
npm run dev
```

The dev server runs on `http://localhost:5173` and talks to the FastAPI backend at
`VITE_API_BASE_URL` (default `http://localhost:8000/api/v1`). Start the backend
separately with `uvicorn strand_sort.main:app --reload`.

## Notes

- Camera capture (`getUserMedia`/`MediaRecorder`) requires HTTPS or `localhost` —
  fine for local dev, but the deployed demo URL needs to be served over HTTPS for
  video recording to work (file upload still works over plain HTTP).
- `npm run build` runs `tsc -b` before bundling, so it doubles as a type-check.
