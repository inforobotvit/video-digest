# frontend

React 19 + Vite 7 + TypeScript. Статика для nginx из `../infra/`, ходит только в `/api/`.

```bash
npm install
npm run dev        # мок: результаты из ../n8n/fixtures, см. список на главной
npm run dev:api    # настоящий API через прокси на http://localhost (nginx из compose)
npm run gen:types  # src/types/result.ts из ../schemas/result.schema.json (файл коммитится)
npm run typecheck && npm run lint && npm test && npm run build
```

Маршруты: `/`, `/jobs/{id}`; глубина чтения страницы результата живёт в URL: `?depth=1|2|3` (по умолчанию 2).
Шрифты IBM Plex Sans / Mono самохостом в `public/fonts/` (OFL). Токены темы – `src/styles/tokens.css`, строки интерфейса – `src/strings.ts`.
