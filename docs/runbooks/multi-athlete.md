# Runbook — Αθλητές εκτός του owner

**Version:** 1.0
**Date:** 2026-10-17
**Owner:** Zaf
**Trigger:** προσθήκη ή διαγραφή αθλητή· μήνυμα `⏸ <id> is not run today: …` στο Telegram του owner·
μήνυμα «Morning briefing not delivered»· αθλητής που λέει ότι δεν πήρε το πρωινό μήνυμα.

Κανόνες: ADR-0067 (D2 προσθήκη, D4 συγκατάθεση, D6 διαγραφή, D7 ετοιμότητα, D8 πρωινός κύκλος,
D9 Garmin, D10 Telegram). Ο owner δεν αλλάζει από τίποτα εδώ: τα στοιχεία του μένουν στο `.env`.

---

## 0. Πού τρέχουν οι εντολές

Όλες οι εντολές τρέχουν στο μηχάνημα της ρουτίνας, εκεί που τρέχει ο worker.

**Docker (προτεινόμενο).** Το `docker-compose.yml` δίνει ήδη στον worker τον φάκελο `/secrets` (volume
`titan-secrets`, χωριστό από τα δεδομένα και τα backups) με το κλειδί των token και το αρχείο
διαγραφών. Βάλε μπροστά από κάθε εντολή:

```bash
docker compose exec titan-worker python scripts/athletes.py list
```

**Τοπικά.** Ο worker (`python -m titan.worker`) και το `scripts/athletes.py` διαβάζουν τις ρυθμίσεις από
το περιβάλλον, όχι από το `.env`. Στο ίδιο τερματικό με τον worker, πριν από κάθε εντολή:

```bash
export TITAN_DATA_DIR=~/Documents/TITAN
export TITAN_TOKEN_KEY_FILE=~/.titan-secrets/athlete_token.key     # έξω από το TITAN_DATA_DIR
export TITAN_DELETION_RECORD_FILE=~/.titan-secrets/deletions.jsonl # έξω από δεδομένα και backups
export TITAN_MULTI_ATHLETE=1
export GARMIN_EMAIL=you@example.com                          # το δικό σου Garmin e-mail
```

Το `relogin` αρνείται να τρέξει χωρίς `GARMIN_EMAIL`: με αυτό αναγνωρίζει τον δικό σου λογαριασμό
και δεν τον δένει σε αθλητή (M0-13). Στο Docker το παίρνει από το `.env`.

Αρνείται επίσης όσο η βάση δεν ξέρει το όνομα του δικού σου λογαριασμού Garmin (ADR-0076). Το όνομα
γράφεται μόνο του σε κάθε σύνδεσή σου που διαβάζει το προφίλ σου στο Garmin. **Πριν από τον πρώτο
αθλητή,** τρέξε μία φορά το δικό σου sync (ή περίμενε ένα πρωινό σου) στη νέα έκδοση. Αν το `relogin`
γράψει `run the owner's Garmin sync first`, αυτό λείπει. Με `this is the owner's Garmin account` ο
αθλητής μπήκε με τον δικό σου λογαριασμό, ακόμα και με άλλο e-mail: δεν δένεται τίποτα.

Ο πρωινός κύκλος τρέχει τους άλλους αθλητές μόνο με `TITAN_MULTI_ATHLETE=1` (στο Docker, στο `.env`).
Χωρίς αυτό τρέχει μόνο ο owner.

**Μία φορά, πριν από τον πρώτο αθλητή:** το κλειδί που κρυπτογραφεί τα Garmin token των αθλητών.

```bash
python scripts/athletes.py new-key
```

Γράφει το αρχείο του `TITAN_TOKEN_KEY_FILE` με mode 0600 και αρνείται αν υπάρχει ήδη, γιατί ένα νέο
κλειδί θα έκανε κάθε αποθηκευμένο token άχρηστο. Κράτα ένα αντίγραφο του κλειδιού κάπου ασφαλές, όχι
μαζί με τα backups. Αν χαθεί, κάθε αθλητής ξανακάνει `relogin` (§4).

**Μόνο SQLite (ISO-5, D-112).** Η εφαρμογή τρέχει μόνο με SQLite: το `TITAN_DB_BACKEND=postgres`
σταματά την εκκίνηση (`get_database_manager`, ADR-0044). Όταν ανοίξει το PostgreSQL, πρώτα πρέπει το
`PostgreSQLAdapter.save_governance_decision` (`titan/core/persistence.py`) να γράφει το `athlete_id`
της απόφασης· σήμερα δεν το γράφει, άρα κάθε απόφαση θα καταγραφόταν στον owner.

---

## 1. Προσθήκη αθλητή

Χρειάζονται: το όνομα, το προφίλ, το Telegram chat id του αθλητή, και ο αθλητής παρών για το Garmin.

1. Ο αθλητής ανοίγει το bot στο Telegram και παίρνει το chat id του από τον `@userinfobot`. Ένα chat
   ανήκει σε έναν αθλητή, και ποτέ δεν είναι το chat του owner.

   Το chat id γράφεται μόνο με ψηφία, όπως το δείχνει ο `@userinfobot` (D-107). Κρατιέται χωρίς
   μηδενικά μπροστά (`0123` γίνεται `123`)· `+`, `-`, `_`, κενά ανάμεσα ή δεκαδικά απορρίπτονται. Το
   chat ενός αθλητή είναι ιδιωτικό, άρα θετικός αριθμός· μόνο το `TELEGRAM_CHAT_ID` του owner μπορεί
   να είναι ομάδα (`-…`). Το `add` και το `chat` αρνούνται όσο το `TELEGRAM_CHAT_ID` είναι κενό, γιατί
   τότε δεν ελέγχεται αν το chat είναι του owner: τρέξε τις εντολές μέσα στο container, που διαβάζει
   το `.env`, ή όρισε το `TELEGRAM_CHAT_ID` στο shell.

2. Γράψε το προφίλ σε ένα αρχείο JSON με όλα τα πεδία:

   ```json
   {"birth_date": "1990-05-01", "sex": "F", "weight_kg": 58, "height_cm": 165, "max_hr": 190,
    "threshold_hr": 172, "training_phase": "BASE", "training_goal": "10K",
    "location_city": "Larissa", "location_country": "GR"}
   ```

   Στο Docker, γράψε το αρχείο μέσα στο container:
   `docker compose exec -T titan-worker sh -c "cat > /tmp/maria.json" < maria.json`, και στο `add`
   δώσε `--profile /tmp/maria.json`.

3. Πρόσθεσε τον αθλητή. Τυπώνει το νέο id (`a-` και 8 χαρακτήρες):

   ```bash
   python scripts/athletes.py add --name "Maria" --profile maria.json --chat 123456789
   ```

4. Σύνδεση με το Garmin, με τον αθλητή δίπλα σου. Ο αθλητής γράφει ο ίδιος e-mail, κωδικό και, αν
   ζητηθεί, τον κωδικό MFA. Ο κωδικός πάει μόνο στο Garmin· κρατιέται μόνο το κρυπτογραφημένο token.
   Στο Docker χρειάζεται `-it`, γιατί η εντολή ρωτά:

   ```bash
   python scripts/athletes.py relogin a-1234abcd
   docker compose exec -it titan-worker python scripts/athletes.py relogin a-1234abcd
   ```

   Ένας λογαριασμός Garmin δένεται σε έναν μόνο αθλητή· αν ανήκει ήδη σε άλλον, η εντολή αρνείται.

5. Ο αθλητής στέλνει στο δικό του chat `/consent` (διαβάζει το κείμενο) και μετά `/agree v1`.
   ⚠️ Το κείμενο v1 (`docs/consent/v1.md`) είναι προσχέδιο: όχι για πραγματικό αθλητή πριν το δει
   δικηγόρος.
   Τις εντολές τις ακούει ο `titan-worker` με `TITAN_MULTI_ATHLETE=1` (D-103). Στο log του worker
   φαίνεται `command_listener_started`· αν λέει `command_listener_not_started`, λείπει το
   `TELEGRAM_BOT_TOKEN`. ⚠️ Μην τρέχεις ταυτόχρονα το `python -m titan` με το ίδιο token: το
   Telegram δίνει τις εντολές μόνο σε έναν από τους δύο (σφάλμα 409), και αν μοιράζονται τη βάση η
   πρωινή ρουτίνα του owner φεύγει δύο φορές.

6. Έλεγχος:

   ```bash
   python scripts/athletes.py list
   ```

   Ένας έτοιμος αθλητής δείχνει `garmin=ok  chat=yes  consent=yes  ready=yes`. Ο πρωινός κύκλος
   ελέγχει κάθε λεπτό από τις 07:00 ως τις 23:59 UTC, οπότε τον τρέχει την ίδια μέρα αν έγινε έτοιμος
   μετά τις 07:00, αλλιώς στις 07:00, μετά τον owner.

---

## 2. Διαγραφή αθλητή

Η διαγραφή δεν αναιρείται. Πρώτα η εξαγωγή, αν ο αθλητής θέλει τα δεδομένα του:

```bash
python scripts/athletes.py export a-1234abcd --out a-1234abcd.json   # αρχείο 0600
python scripts/athletes.py remove a-1234abcd                         # ζητά να γράψεις το id
```

Το `remove` γράφει πρώτα μια γραμμή στο αρχείο διαγραφών (`TITAN_DELETION_RECORD_FILE`: μόνο id και
ώρα), μετά σβήνει κάθε γραμμή του αθλητή σε κάθε πίνακα με `athlete_id`, σε μία συναλλαγή, και μετά
τον φάκελο του token του. Χωρίς `TITAN_DELETION_RECORD_FILE` αρνείται και δεν σβήνει τίποτα.
Μαζί σβήνονται οι χρήστες API του αθλητή και τα refresh token τους. Η εξαγωγή δεν έχει hash κωδικών.
Αν το `remove` γράψει `Delete of … failed`, δεν σβήστηκε καμία γραμμή αλλά η εγγραφή διαγραφής
έμεινε: διόρθωσε την αιτία και τρέξε `python scripts/athletes.py reapply-deletions` (το κάνει και ο
worker στην εκκίνηση). Αν γράψει ότι ο φάκελος του token δεν σβήστηκε, οι γραμμές σβήστηκαν· σβήσε
τον φάκελο `garmin/<id>/` με το χέρι (D-108).

Στο Docker η εξαγωγή γράφεται μέσα στο container, και το `remove` ρωτά, οπότε θέλει `-it`:

```bash
docker compose exec titan-worker python scripts/athletes.py export a-1234abcd --out /tmp/a-1234abcd.json
docker compose cp titan-worker:/tmp/a-1234abcd.json .
docker compose exec -it titan-worker python scripts/athletes.py remove a-1234abcd
```

- **Μετά από `/stop`:** ο αθλητής παγώνει αμέσως (καμία κλήση, κανένα μήνυμα). Ο worker τον σβήνει
  μόνος του 30 ημέρες μετά. Για να γίνει τώρα: `python scripts/athletes.py purge-expired`.
- **Μετά από restore backup:** ο worker ξανασβήνει μόνος του, στην εκκίνηση, όσους γράφει το αρχείο
  διαγραφών. Με το χέρι: `python scripts/athletes.py reapply-deletions`.
- Το αρχείο εξαγωγής περιέχει προσωπικά δεδομένα: δώσ' το στον αθλητή και σβήσ' το.

---

## 3. Ένας αθλητής δεν πήρε μήνυμα

### Βήμα 1 — Τι λέει το `list` για σήμερα

```bash
python scripts/athletes.py list
```

| Στήλη | Σημαίνει | Τι κάνεις |
|---|---|---|
| `ready=no (consent: none current)` | Δεν έχει συγκατάθεση, ή έστειλε `/stop` | Ο αθλητής στέλνει `/consent` και `/agree v1` (§1.5). Μέσα στις 30 ημέρες μετά το `/stop` μπορεί να ξαναδώσει |
| `ready=no (no profile)` ή όνομα πεδίου | Λείπει ή είναι άκυρο πεδίο του προφίλ | Σβήσε και πρόσθεσε ξανά τον αθλητή με σωστό προφίλ (§2, §1) |
| `ready=no (garmin: no account bound)` | Δεν έγινε ποτέ `relogin` | §1.4 |
| `ready=no (garmin: token missing)` ή `token expired` | Το token δεν υπάρχει ή το Garmin το απέρριψε | §4 |
| `ready=no (telegram: no chat bound)` | Δεν υπάρχει chat | Σβήσε και πρόσθεσε ξανά τον αθλητή με το σωστό `--chat` |
| `ready=no (telegram: chat id not in canonical form, …)` | Το chat γράφτηκε πριν το D-107 σε άλλη μορφή (`01001`, `+1001`) και μπορεί να φτάνει σε άλλο chat· ο αθλητής δεν τρέχει | Ξαναδέσε το chat: `python scripts/athletes.py chat <id> --chat <ψηφία>`· συγκατάθεση και δεδομένα μένουν |
| `ready=no (telegram: chat is the owner's, …)` | Το chat του αθλητή είναι το `TELEGRAM_CHAT_ID` του owner | Ξαναδέσε το σωστό chat του αθλητή με `athletes.py chat` |
| `ready=yes  today=not started` | Είναι έτοιμος, αλλά ο κύκλος δεν τον έτρεξε σήμερα. Μετά τις 12:00 UTC καμία μέρα δεν ξεκινά (`worker_routine_too_late`)· ξεκινά αύριο στις 07:00 | Βήμα 2 |
| `today=attempt N not delivered` | Ξεκίνησε και δεν παραδόθηκε, ή τρέχει τώρα· η επόμενη προσπάθεια ξεκινά 15 λεπτά μετά την προηγούμενη, ως 3 φορές τη μέρα | Βήμα 2 |
| `today=left after 3 attempts` | Τρεις αποτυχίες· η μέρα έκλεισε και ο owner πήρε «Morning briefing not delivered» | Βήμα 2. Αύριο ξαναδοκιμάζει μόνος του |
| `today=delivered` | Το Telegram δέχτηκε το μήνυμα | Ο αθλητής να ελέγξει ότι έχει ανοίξει το bot και δεν το έχει μπλοκάρει· αλλιώς το chat id είναι λάθος (§1.1) |

Το «σήμερα» είναι η μέρα UTC. Όταν ένας αθλητής δεν είναι έτοιμος, ο owner παίρνει μία φορά την ημέρα
το `⏸ <id> is not run today: <λόγος>.` με τον ίδιο λόγο που δείχνει το `list`.

Χωρίς `TELEGRAM_BOT_TOKEN` τίποτα δεν στέλνεται, και η μέρα δεν γράφεται `delivered` (D-107): μένει
`attempt N not delivered`, ξαναδοκιμάζεται και μετά τις 3 φορές κλείνει, με warning
`telegram_fallback_delivery_preview` στα logs. Ειδοποιήσεις συστήματος για έναν αθλητή (αποτυχία
εγγραφής, Garmin χωρίς sync πάνω από 26 ώρες, βάση που δεν διαβάζεται, degraded mode) πηγαίνουν στο
chat του owner με το id του αθλητή· ο αθλητής παίρνει μόνο ένα σύντομο μήνυμα ότι η σημερινή
προπόνηση είναι συντηρητική.

### Βήμα 2 — Τα logs του worker

```bash
docker compose logs titan-worker | grep "a-1234abcd" | tail -30
```

Ο worker γράφει στο stderr, οπότε τοπικά τα logs είναι στο τερματικό του worker. Κάθε γραμμή του
worker έχει στο τέλος τα πεδία της, π.χ. `athlete_id=a-1234abcd reason=consent: none current`.

| Γεγονός | Σημαίνει |
|---|---|
| `scheduler_athlete_not_ready` | Δεν ήταν έτοιμος· το `reason` είναι ο λόγος του Βήματος 1 |
| `worker_routine_killed` | Η διεργασία του ξεπέρασε το `WORKER_ROUTINE_BUDGET_S` και σταμάτησε |
| `worker_routine_child_died` | Η διεργασία του τερμάτισε με σφάλμα· το traceback είναι λίγο πιο πάνω |
| `worker_routine_left` (CRITICAL) | Τρεις αποτυχίες· η μέρα έκλεισε |
| `worker_routine_resend_stored` | Ξαναστάλθηκε η απόφαση που είχε ήδη φτιαχτεί, με τα όριά της· τα δεδομένα της μέρας δεν άλλαξαν. Ο αθλητής βλέπει ότι μπορεί να επαναλαμβάνει προηγούμενο μήνυμα |
| `worker_routine_inputs_changed` | Τα δεδομένα της μέρας άλλαξαν μετά την πρώτη απόφαση· η μέρα υπολογίστηκε ξανά με τις πύλες και η νέα απόφαση αντικατέστησε την παλιά |
| `worker_routine_resend_capped` | Ο νέος υπολογισμός δεν έβγαλε απόφαση· στάλθηκε η παλιά το πολύ EASY με 45 λεπτά |
| `worker_routine_delivery_unrecorded` (CRITICAL) | Το μήνυμα στάλθηκε, η καταγραφή απέτυχε και μετά τις επαναλήψεις· ο worker δεν το ξαναστέλνει και ξαναδοκιμάζει την καταγραφή σε κάθε κύκλο. Μετά από επανεκκίνηση μπορεί να σταλεί μία φορά ακόμα |
| `worker_routine_too_late` | Μετά τις 12:00 UTC καμία μέρα δεν ξεκινά (D-109) |
| `athlete_garmin_token_expired` | Το token απορρίφθηκε σήμερα· ο αθλητής είναι σε παύση από τώρα (§4) |
| `connect_token_key_unusable` | Το κλειδί των token λείπει ή δεν είναι ασφαλές (§4, τελευταία παράγραφος) |
| `connect_token_key_mismatch` (CRITICAL) | Το κλειδί είναι έγκυρο αλλά δεν είναι αυτό που κρυπτογράφησε το token· το token μένει (§4, τελευταία παράγραφος) |
| `connect_token_check_failed` | Δίκτυο, timeout ή σφάλμα 5xx του Garmin στον έλεγχο του token· το token μένει, ο αθλητής δεν μπαίνει σε παύση και ο επόμενος κύκλος ξαναδοκιμάζει (§4) |

Αν δεν υπάρχει καμία γραμμή για τον αθλητή, έλεγξε ότι το `TITAN_MULTI_ATHLETE=1` είναι στο
περιβάλλον του worker (§0) και ότι ο worker τρέχει (`docker compose ps`).

---

## 4. Λήξη του Garmin token

**Συμπτώματα:** `garmin=expired` (ή `missing`) στο `list`, `athlete_garmin_token_expired` ή
`connect_relogin_required` στα logs, και το `⏸ <id> is not run today: garmin: token expired.` στον
owner. Ο worker δεν κάνει ποτέ login με κωδικό για άλλον αθλητή, οπότε ο αθλητής μένει σε παύση ώσπου
να ξανασυνδεθεί. Ο owner και οι άλλοι αθλητές δεν επηρεάζονται.

Το token σβήνεται μόνο όταν το Garmin το απορρίπτει (401). Αν τα logs γράφουν
`connect_token_check_failed`, το Garmin ή το δίκτυο δεν απάντησε: το token μένει, το `list` λέει
ακόμα `garmin=ok` και δεν χρειάζεται `relogin`· ο επόμενος κύκλος ξαναδοκιμάζει (D-108).

**Λύση:** με τον αθλητή παρόντα,

```bash
python scripts/athletes.py relogin a-1234abcd
python scripts/athletes.py list            # garmin=ok  ready=yes
```

Αν η μέρα δεν έχει παραδοθεί και είναι μετά τις 07:00 UTC, ο επόμενος κύκλος τον τρέχει την ίδια
μέρα. Αν θέλει τα δεδομένα του αμέσως, στέλνει `/sync` στο chat του.

**Αν τα logs γράφουν `athlete_garmin_account_is_owners`:** ο αθλητής ήταν δεμένος στον δικό σου
λογαριασμό Garmin. Η σύνδεσή σου το είδε και τον σταμάτησε (`garmin=expired`), χωρίς να γράψει το
όνομα στα logs (ADR-0076 σημείο 6). Το `relogin` στον ίδιο λογαριασμό αρνείται. Έλεγξε με τον αθλητή
ποιος είναι ο δικός του λογαριασμός Garmin, και κάνε `relogin` μαζί του με αυτόν. Το
`owner_garmin_account_name_changed` λέει ότι άλλαξε το όνομα του δικού σου λογαριασμού: αν δεν το
άλλαξες εσύ, έλεγξε ότι το `.env` δείχνει στον δικό σου λογαριασμό.

**Αν το `list` λέει `garmin=ok` αλλά τα logs γράφουν `connect_token_key_unusable` ή
`connect_token_key_mismatch`:** το πρόβλημα είναι
το κλειδί, όχι το token. Το token δεν σβήνεται γι' αυτό. Έλεγξε ότι το `TITAN_TOKEN_KEY_FILE` είναι
ορισμένο, ότι το αρχείο υπάρχει έξω από το `TITAN_DATA_DIR` και ότι έχει mode 0600
(`chmod 600 <αρχείο>`). Αν το κλειδί χάθηκε, δεν ξαναβρίσκεται: σβήσε το αρχείο, αν έμεινε άκυρο, τρέξε
`new-key` και κάνε `relogin` σε κάθε αθλητή. Με `connect_token_key_mismatch` το `TITAN_TOKEN_KEY_FILE`
δείχνει σε άλλο κλειδί από αυτό που έγραψε τα token: βάλε πίσω το σωστό κλειδί· αν δεν υπάρχει πια,
`relogin` στον αθλητή.
