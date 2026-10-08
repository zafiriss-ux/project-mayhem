# RUNBOOK_ROLLBACK — Εκδόσεις, αναβάθμιση και επιστροφή

Καλύπτει το AGENTS §8.9 (RE-01..04) για την εγκατάσταση Docker ενός αθλητή.

## Πώς βγαίνει μια έκδοση (RE-01, RE-02)

1. Η έκδοση υπάρχει μόνο στο `pyproject.toml` (`version = "X.Y.Z"`). Το `titan.__version__` τη διαβάζει από εκεί.
2. Άλλαξε την έκδοση με PR στο `main` και κάνε merge.
3. Βάλε tag στο commit του `main` και στείλ' το:
   ```bash
   git tag -a vX.Y.Z -m "Release vX.Y.Z" <commit>
   git push origin vX.Y.Z
   ```
   Χωρίς git: στη σελίδα Releases → «Draft a new release» → «Choose a tag», γράψε `vX.Y.Z` → «Create new tag on publish», target `main` → «Publish release». Το workflow προσθέτει μετά το zip σε αυτό το Release.
4. Το workflow `Release` (`.github/workflows/release.yml`) ελέγχει ότι το tag είναι ίδιο με την έκδοση του `pyproject.toml` και ότι το commit είναι στο `main`. Μετά φτιάχνει τα `ghcr.io/zafiriss-ux/titan-api:vX.Y.Z` και `ghcr.io/zafiriss-ux/titan-worker:vX.Y.Z` και ανοίγει το GitHub Release.

Commit χωρίς tag δεν πάει ποτέ σε παραγωγή.

## Ρύθμιση του server (μία φορά)

Οι εικόνες είναι ιδιωτικές, όπως και το repo. Ο server χρειάζεται ένα GitHub token μόνο με δικαίωμα `read:packages`:

```bash
echo <token> | docker login ghcr.io -u zafiriss-ux --password-stdin
```

Στο `.env` του server γράψε την έκδοση που τρέχει:

```bash
TITAN_VERSION=vX.Y.Z
```

Όλες οι εντολές παρακάτω χρησιμοποιούν και τα δύο αρχεία compose. Για συντομία:

```bash
alias titan='docker compose -f docker-compose.yml -f docker-compose.release.yml'
```

## Ποια έκδοση τρέχει

```bash
titan images
grep TITAN_VERSION .env
```

Οι προηγούμενες εκδόσεις: `git tag --sort=-v:refname | head` ή η σελίδα Releases του repo.

## Αναβάθμιση

1. Κράτα αντίγραφο της βάσης **πριν** την αναβάθμιση. Το αυτόματο backup του worker τρέχει αφού η νέα έκδοση έχει ήδη αλλάξει το σχήμα, οπότε δεν κάνει για επιστροφή:
   ```bash
   titan exec titan-worker python -c "import sqlite3; s=sqlite3.connect('/data/titan_core.db'); d=sqlite3.connect('/backups/pre-upgrade-vX.Y.Z.db'); s.backup(d); d.close()"
   ```
2. Άλλαξε το `TITAN_VERSION` στο `.env` στη νέα έκδοση.
3. `titan pull && titan up -d`
4. Επιβεβαίωσε (βλ. «Έλεγχος»).

## Επιστροφή σε προηγούμενη έκδοση (RE-03)

1. Βρες την προηγούμενη έκδοση (βλ. «Ποια έκδοση τρέχει»).
2. Έλεγξε αν η νέα έκδοση άλλαξε το σχήμα της βάσης. Σύγκρινε την έκδοση σχήματος της βάσης με αυτή που περιμένει η παλιά έκδοση:
   ```bash
   titan exec titan-worker python -c "import sqlite3; print(sqlite3.connect('/data/titan_core.db').execute('PRAGMA user_version').fetchone()[0])"
   TITAN_VERSION=<παλιά> titan run --rm --no-deps titan-worker python -c "from titan.core.database import SCHEMA_VERSION; print(SCHEMA_VERSION)"
   ```
3. **Ίδιος αριθμός:** άλλαξε το `TITAN_VERSION` στην παλιά έκδοση, και μετά `titan pull && titan up -d`.
4. **Διαφορετικός αριθμός:** η παλιά έκδοση δεν πρέπει να ανοίξει τη νέα βάση. Οι μεταβάσεις σχήματος πάνε μόνο μπροστά, και ο έλεγχος που θα σταματούσε μια παλιά έκδοση (INV-25, T-PRA-25) δεν υπάρχει ακόμα. Η επιστροφή των δεδομένων γίνεται **με επαναφορά του αντιγράφου**:
   ```bash
   titan stop titan-api titan-worker
   titan run --rm --no-deps --entrypoint sh titan-worker -c \
     "cp /data/titan_core.db /data/titan_core.db.before-rollback && \
      cp /backups/pre-upgrade-vX.Y.Z.db /data/titan_core.db && \
      rm -f /data/titan_core.db-wal /data/titan_core.db-shm"
   ```
   Μετά άλλαξε το `TITAN_VERSION` στην παλιά έκδοση και τρέξε `titan up -d`. Ό,τι γράφτηκε μετά την αναβάθμιση χάνεται. Το επόμενο Garmin sync ξαναφέρνει όσα υπάρχουν ακόμα στο Garmin. Τα υπόλοιπα βήματα επαναφοράς είναι στο `docs/RUNBOOK_DR.md`.
5. Επιβεβαίωσε.

## Έλεγχος

```bash
curl -f http://localhost:8000/readyz
titan exec titan-worker python scripts/worker_healthcheck.py
titan ps    # και τα δύο containers: healthy
```

## Δοκιμή

Το RE-03 θέλει αυτή η επιστροφή να δοκιμάζεται σε κάθε κλείσιμο φάσης, με καταγραφή του αποτελέσματος. Δεν έχει δοκιμαστεί ακόμα σε staging, γιατί δεν έχει βγει ακόμα έκδοση με tag. Η πρώτη δοκιμή γίνεται με το πρώτο release.
