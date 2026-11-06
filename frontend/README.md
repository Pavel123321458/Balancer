# Интерфейс Balancer

Запускается вместе с остальными сервисами через Docker Compose. Для разработки отдельно запустите API и worker, затем из этого каталога выполните `pnpm install --frozen-lockfile` и `pnpm dev`. Требуются Node.js 24 и pnpm 11. Если API использует другой адрес, задайте `BALANCER_API_TARGET` перед запуском Vite.

`pnpm build` проверяет TypeScript и собирает статический frontend. В Compose Nginx раздаёт сборку и проксирует запросы `/api/` в FastAPI.
