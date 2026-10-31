# RUNBOOK_DR — Αντίγραφα ασφαλείας και επαναφορά

Καλύπτει το AGENTS §8.10 (DR-01..04) για την εγκατάσταση Docker ενός αθλητή (ADR-0057).
Για τη διάγνωση μιας χαλασμένης βάσης και για το χειροκίνητο αντίγραφο (`scripts/backup.sh`), δες το
[`runbooks/database-recovery.md`](runbooks/database-recovery.md).

## Στόχοι

| | Στόχος | Πώς τον πιάνουμε |
|---|---|---|
| **RPO** (μέγιστη απώλεια δεδομένων) | ≤ 24 ώρες | Ο `titan-worker` παίρνει ένα αντίγραφο σε κάθε κύκλο: μία φορά στην εκκίνηση και μετά κάθε μέρα στις 07:00 UTC, πριν την πρωινή ρουτίνα. |
| **RTO** (χρόνος μέχρι να ξαναδουλέψει) | ≤ 4 ώρες | Η επαναφορά παρακάτω είναι 4 εντολές και διαρκεί λίγα λεπτά. Το όριο αφήνει χρόνο για διάγνωση. |

**Υπεύθυνος:** ο ιδιοκτήτης και διαχειριστής της εγκατάστασης (Zaf).
**Κλιμάκωση:** δεν υπάρχει δεύτερο πρόσωπο. Αν η επαναφορά αποτύχει, **μην σβήσεις τίποτα**: κράτα το `titan_core.db.before-restore` και όλα τα αρχεία `*.db.corrupt`, και δοκίμασε το αμέσως προηγούμενο αντίγραφο.

## Πού είναι τα αντίγραφα (DR-01)

- Docker: στο volume **`titan-backups`**, στη διαδρομή `/backups` του `titan-worker` (`TITAN_BACKUP_DIR=/backups`). Η βάση είναι σε ξεχωριστό volume (`titan-data`, `/data`), οπότε η αλλοίωση ή το σβήσιμο του ενός δεν παίρνει μαζί και το άλλο.
- Τα δύο volumes είναι στον ίδιο δίσκο του host. Για προστασία από χάλασμα του δίσκου ή του μηχανήματος, βγάλε περιοδικά ένα αντίγραφο έξω από το μηχάνημα (βλ. «Αντίγραφο εκτός μηχανήματος»).
- Αν δεν οριστεί `TITAN_BACKUP_DIR`, ο worker γράφει δίπλα στη βάση (`<TITAN_DATA_DIR>/backups`) και καταγράφει warning `backup_same_volume`.
- Τοπικά (launcher ή `python -m titan`, χωρίς worker) **δεν παίρνονται αυτόματα αντίγραφα**.

Όνομα αρχείου: `titan_YYYY-MM-DD.db`, ένα την ημέρα (UTC).

## Έλεγχος και διατήρηση (DR-02)

Κάθε νέο αντίγραφο ελέγχεται αμέσως με `PRAGMA integrity_check`, και το `user_version` του πρέπει να είναι ίδιο με της ζωντανής βάσης.

- **Επιτυχία:** log INFO `db_backup_created`, με `size_bytes` και `"integrity": "ok"`.
- **Αποτυχία:** το αρχείο μετονομάζεται σε `titan_YYYY-MM-DD.db.corrupt`, γράφεται log CRITICAL `db_backup_failed` και αυξάνεται ο μετρητής `titan_backup_failure_total`. Το αποτυχημένο αντίγραφο δεν μετράει ποτέ ως έγκυρο.

Διατήρηση από το `.env`:

```bash
BACKUP_RETENTION_DAILY_DAYS=7     # τα 7 πιο πρόσφατα ημερήσια
BACKUP_RETENTION_WEEKLY_COUNT=4   # + το πιο πρόσφατο από καθεμία από τις 4 προηγούμενες εβδομάδες
```

## Έλεγχος επαναφοράς (DR-03)

Αντιγράφει το πιο πρόσφατο αντίγραφο σε προσωρινό φάκελο, το ανοίγει και ελέγχει το `integrity_check`, ότι το `user_version` είναι ίσο με το `SCHEMA_VERSION` του κώδικα, και ότι υπάρχουν οι βασικοί πίνακες. Το αρχικό αρχείο δεν αγγίζεται.

```bash
docker compose exec titan-worker python scripts/restore_drill.py
# {"backup_dir": "/backups", "ok": true, "backup": "titan_2026-10-16.db", "user_version": 32, "tables": 27}
```

Exit code 0 σημαίνει επιτυχία και 1 αποτυχία. Τρέχει σε κάθε κλείσιμο φάσης μαζί με:

```bash
python -m pytest tests/ -k db_integrity -v
```

Το αποτέλεσμα καταγράφεται στο κλείσιμο της φάσης. Αντίγραφο που δεν έχει ελεγχθεί με επαναφορά δεν είναι αντίγραφο.

## Επαναφορά (Docker)

1. Βρες ποιο αντίγραφο θα χρησιμοποιήσεις και έλεγξέ το:
   ```bash
   docker compose run --rm --no-deps --entrypoint ls titan-worker -l /backups
   docker compose run --rm --no-deps titan-worker python scripts/restore_drill.py
   ```
   Το `restore_drill.py` ελέγχει πάντα το πιο πρόσφατο αντίγραφο. Αν αυτό έχει πρόβλημα, πάρε το προηγούμενο από τη λίστα και βάλε το όνομά του στο βήμα 3.
2. Σταμάτησε τις υπηρεσίες ώστε να μη γράφει τίποτα στη βάση:
   ```bash
   docker compose stop titan-api titan-worker
   ```
3. Κράτα την τωρινή βάση και βάλε στη θέση της το αντίγραφο (άλλαξε την ημερομηνία):
   ```bash
   docker compose run --rm --no-deps --entrypoint sh titan-worker -c \
     "cp /data/titan_core.db /data/titan_core.db.before-restore && \
      cp /backups/titan_2026-10-06.db /data/titan_core.db && \
      rm -f /data/titan_core.db-wal /data/titan_core.db-shm"
   ```
4. Ξεκίνα και επιβεβαίωσε:
   ```bash
   docker compose up -d
   curl -f http://localhost:8000/readyz
   ```

Τα δεδομένα μετά την ώρα του αντιγράφου χάνονται (έως 24 ώρες). Το επόμενο Garmin sync ξαναφέρνει όσα είναι ακόμα διαθέσιμα στο Garmin.

Αθλητές που διαγράφηκαν μετά την ώρα του αντιγράφου (ADR-0067 D2.7, D-097): ο worker τους ξανασβήνει
στην εκκίνηση από το `TITAN_DELETION_RECORD_FILE`, πριν τρέξει οτιδήποτε. Για να το κάνεις με το χέρι
πριν ξεκινήσει ο worker:
```bash
docker compose run --rm --no-deps titan-worker python scripts/athletes.py reapply-deletions
```

## Αντίγραφο εκτός μηχανήματος

```bash
docker compose run --rm --no-deps --entrypoint tar titan-worker -C /backups -czf - . > titan-backups-$(date -u +%F).tgz
```

Κράτα το `.tgz` σε άλλο μέσο (cloud drive, εξωτερικό δίσκο).

## Γνωστά όρια

- Σε λειτουργία πολλών αθλητών (`TITAN_MULTI_ATHLETE=1`) ο scheduler παίρνει ένα αντίγραφο την ημέρα, στον πρώτο του κύκλο της ημέρας UTC· μετά από επανεκκίνηση μπορεί να πάρει ένα ακόμα (D-099).
- Δεν υπάρχει αυτόματη αποστολή εκτός μηχανήματος. Είναι χειροκίνητη, με την εντολή πιο πάνω.
