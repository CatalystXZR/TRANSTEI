# Backup y restore

> **Pregunta que responde:** ¿cómo respaldo y restauro sin pisar el proyecto equivocado?
> **Dueño:** `datos` · **Verificado:** 2026-10-29 · **Método:** lectura de `scripts/`
> **Caduca si:** cambian los scripts o el destino (local ↔ nube).
> **Re-verificar con:** `head -30 scripts/backup_pgdump.sh scripts/restore_drill.sh`

---

## 1. Los dos scripts no son intercambiables

| Script | Destino | Requisito | Sirve para |
|---|---|---|---|
| `scripts/restore_drill.sh` | **Local** | contenedor `supabase_db_TRANSTEI` corriendo | backup + restore de prueba + conteos |
| `scripts/backup_pgdump.sh` | **Nube** | `DATABASE_URL` en `backend/.env` con el ref del proyecto | backup `pg_dump` sin restore |

🟢 `backup_pgdump.sh:25-27` **aborta** si la URL no contiene el ref del proyecto en la nube.
Por eso **no sirve para la base local**, aunque el checklist antiguo lo ofrecía como alternativa.

---

## 2. Backup + restore drill local (recomendado)

```bash
make restore-drill        # o ./scripts/restore_drill.sh
```

Qué hace (`scripts/restore_drill.sh`):

1. `pg_dump` de `nucleo`, `public` y `auth` → `backups/transtei_drill_<fecha>.sql`.
2. Crea una base temporal `transtei_restore_drill` con `btree_gist` y `pgcrypto`.
3. Restaura el dump.
4. Verifica **6 conteos**: empresas, clientes, viajes, facturas, pagos, auditoría.
5. Marca `restore_ok` si existen viajes y auditoría.
6. Elimina la base temporal. **El backup se conserva** en `backups/`.

`backups/` está en `.gitignore` (`.gitignore:26`).

---

## 3. Limitación conocida (RA-05)

El drill verifica que el restore **no esté vacío**, pero **no compara antes/después**:

- No guarda los conteos del origen.
- No detecta filas perdidas ni duplicadas.
- No prueba que la aplicación funcione contra la base restaurada.
- `restore_ok` sólo exige que exista al menos un viaje y un registro de auditoría.

**Mejora pendiente:** capturar conteos del origen y compararlos con el destino; fallar
el drill si difieren. Dueño: `datos`. Registrado en `docs/arquitectura/deuda.md`.

---

## 4. Restore real (procedimiento)

1. Autorización explícita del dueño/gerencia. Un restore real **sobrescribe datos**.
2. Backup del estado actual **antes** de restaurar.
3. Restaurar en una base temporal primero y validar conteos y aplicación.
4. Recién entonces reapuntar la aplicación.
5. Registrar en `docs/orquestacion/registro.md`: fecha, motivo, archivo usado, conteos antes/después.

**Nunca** borres el backup anterior hasta que el nuevo restore esté validado.

---

## 5. Backup en la nube (`backup_pgdump.sh`)

```bash
bash scripts/backup_pgdump.sh
```

- Lee `backend/.env` (variable `DATABASE_URL`).
- Verifica que el destino sea el proyecto correcto y aborta si detecta refs ajenos.
- Escribe un `.sql` en `backups/`.
- **No** restaura ni verifica.

🟡 El proyecto en la nube no fue verificado en esta sesión (puede estar pausado).
El plan Free pausa proyectos tras 7 días sin uso.

---

## 6. Qué NO es un backup

- Un `git commit` del código: no incluye datos.
- Un dump sin restore probado: no es un backup hasta que restaurarlo funciona.
- Un backup en `backups/` sin copia fuera de la máquina: se pierde con el disco.
