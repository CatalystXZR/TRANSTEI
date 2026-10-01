# Actualizar a Supabase Pro (backups automáticos)

> Estado actual: plan **Free**. No incluye backups automáticos. Para producción
> real se recomienda subir a Pro (~US$25/mes), que activa backups diarios y PITR.

## Pasos para "llegar y cargar"

1. Entrar a https://supabase.com/dashboard/project/luzxxhgozpqsxnwfookb/settings/billing
2. **Upgrade to Pro** → ingresar método de pago
3. Ir a **Database → Backups**:
   - Verificar que aparezcan **backups diarios automáticos** (retención 7 días en Pro)
   - Opcional: activar **PITR** (Point-in-Time Recovery) si se requiere recuperar a un minuto exacto
4. Configurar retención según necesidad (a mayor retención, mayor costo)

## Mientras tanto (plan Free)

- Ejecutar backups manuales con el script seguro:
  ```bash
  bash scripts/backup_pgdump.sh
  ```
  Genera un `.sql` en `backups/` (ignorado por git) y **verifica** que el destino sea
  el proyecto TRANSTEI antes de exportar.
- Recordar: el plan Free **pausa el proyecto tras 7 días sin uso**; se reactiva desde el dashboard.

## Qué NO cambia al subir a Pro

- `DATABASE_URL`, claves API y el código no cambian.
- El bucket `respaldos` sigue igual.
- Solo se habilitan features de infraestructura (backups, más recursos, sin pausa).

## Restaurar un backup (si fuera necesario)

```bash
psql "postgresql://postgres.luzxxhgozpqsxnwfookb:<password>@aws-0-sa-east-1.pooler.supabase.com:5432/postgres" < backups/transtei_AAAAAMMDD_HHMMSS.sql
```
> Verificar SIEMPRE el ref `luzxxhgozpqsxnwfookb` antes de restaurar.
