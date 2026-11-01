# ADR-0081: Το πρωινό μήνυμα λέει ποιες πύλες δεν μετρήθηκαν και όταν πιάσει lock, χωρίς ωμούς κωδικούς (SD-06)

**Status:** ✅ Accepted (2026-11-01· ο owner διάλεξε την επιλογή Α με κάρτα απόφασης, 06:01 UTC, αφού ο ανεξάρτητος έλεγχος Opus έδωσε VERDICT: PASS στον τρίτο γύρο, D-221)
**Αποδοχή:** 2026-11-01, 06:01 UTC, κάρτα απόφασης «Εγκρίνεις το ADR-0081 για το πρωινό μήνυμα (SD-06);» → «Α: λίστα και κείμενα», D-221
**Date:** 2026-11-01
**Author:** Claude (κείμενο, κατά αίτηση του owner, ADR-0078) / Zaf (Owner, Architect, αποφασίζει)
**Related:** ADR-0038 (decision rationale, «ένα template για κάθε πύλη»)· ADR-0069 §3 (H1 χωρίς πηγή →
UNKNOWN)· ADR-0073 (κλειστό μονοπάτι για ό,τι δεν μετρήθηκε)· ADR-0075 (εξαίρεση H1/H5 χωρίς μέτρηση:
«το μήνυμα γράφει UNKNOWN»)· ADR-0051 (ελλιπή δεδομένα)· ADR-0067 D3.4 (golden του owner)· ADR-0072
(αλλαγή Β μόνο με ADR Accepted)· έλεγχος SD (`docs/audits/2026-10-24-sd.md`, SD-06)·
`docs/audits/FINDINGS.md` (SD-06, XC-06, XB-18, XB-20)· CONTRACT 7.9 §13.

---

## Context

Το πρωινό μήνυμα Telegram έχει μία γραμμή «🧭 Why this decision». Τη γράφει το
`send_daily_coaching` από το `primary_reason` (`telegram_bot.py:1151-1152`). Το `primary_reason` περνά
αυτούσιο από το `_build_coaching_payload` (`daily_coach.py:1954`, `:1961`), και το φτιάχνει το
`_build_decision_rationale` (`governance_engine.py:1175`). Οι κωδικοί των locks **δεν** δείχνονται
αλλού στο μήνυμα. Ό,τι λείπει από αυτή τη γραμμή, ο owner δεν το βλέπει.

Ο έλεγχος SD βρήκε δύο κενά σε αυτή τη γραμμή (SD-06, HIGH, Κατηγορία Β). Τα επιβεβαίωσε test
(`test_h1_missing_is_unknown_and_told` στο `docs/audits/sd-2026-10-24/test_sd_gate_matrix.py.txt`,
αποτυγχάνει στο `28608d0`). Οι αριθμοί γραμμών παρακάτω ελέγχθηκαν ξανά στο `eff6752`.

| Κενό | Τι γίνεται σήμερα | Τεκμήριο |
|---|---|---|
| **1. Οι πύλες που δεν μετρήθηκαν χάνονται όταν πιάσει lock ή πύλη** | Κύρια αιτία είναι το πρώτο εύρημα TRIGGERED (`governance_engine.py:1298`). Αν δεν πιάσει τίποτα, το κείμενο προσθέτει «Not measured: …» για τις πύλες UNKNOWN (`:1299-1303`). Αν πιάσει οποιοδήποτε lock ή πύλη H1–H5, γράφεται μόνο η αιτία του (`:1305-1306`) και οι πύλες UNKNOWN δεν αναφέρονται | ανάγνωση κώδικα· test SD-06 |
| **1β. Η λίστα UNKNOWN δεν πιάνει όλες τις τιμές που λείπουν** | Το rationale βάζει UNKNOWN μόνο όταν η τιμή είναι `None` ή δεν γίνεται αριθμός (`:1191-1270`). Το `_check_hard_stops` (`:452-692`) μετρά ως «λείπει» και τιμές μη πεπερασμένες (NaN), baseline ≤ 0 και τιμές που δεν είναι αριθμοί, και βάζει `DATA_MISSING_CONSERVATIVE_Hn`. Τότε το lock μπαίνει, αλλά η πύλη Hn γράφεται CLEAR στο rationale | ανεξάρτητος έλεγχος Opus του ADR: `apply_constraints` με baseline HRV 0, HRV NaN, RHR NaN, TSB NaN, κόπωση `'abc'` → μπαίνουν τα `DATA_MISSING_Hn`, οι H1–H5 όλες CLEAR, κύρια αιτία `READINESS_2OF4_DOWNGRADE` |
| **2. Ωμοί κωδικοί lock στο μήνυμα** | Για κάθε lock το εύρημα παίρνει κείμενο από το `GATE_RATIONALE_TEMPLATES` (`:63-78`) μέσω του `_format_template` (`:1286-1295`). Όταν λείπει template, γυρνά ο ίδιος ο κωδικός (`:1142`: `GATE_RATIONALE_TEMPLATES.get(template_key, template_key)`), και αυτός γράφεται στο μήνυμα | ανάγνωση κώδικα· golden (παρακάτω) |

**Locks χωρίς template σήμερα.** Το `apply_constraints` προσθέτει 17 κωδικούς στο `applied_locks`
(`governance_engine.py:1374-1563`). Όλοι είναι στο `CANONICAL_LOCK_CODES` (`thresholds.py:216-237`).
Από αυτούς, οκτώ δεν έχουν template:

| Κωδικός | Πού μπαίνει |
|---|---|
| `INTENSITY_GATE_RED` | `governance_engine.py:1374` |
| `INTENSITY_GATE_YELLOW` | `:1376` |
| `HARD_STOP_SAFETY_GATES` | `:1410` |
| `DATA_MISSING_CONSERVATIVE_H2` | `:1413` |
| `DATA_MISSING_CONSERVATIVE_H3` | `:1415` |
| `DATA_MISSING_CONSERVATIVE_H4` | `:1417` |
| `DATA_MISSING_CONSERVATIVE_H5` | `:1419` |
| `DATA_VOID_CONSERVATIVE` | `:1468` |

Δύο ακόμη κωδικοί δεν φτάνουν ποτέ στο rationale:

- `FAIL_SAFE_LOCK`: είναι στο `CANONICAL_LOCK_CODES`, αλλά ο κώδικας τον γράφει μόνο ως action σε
  event (`:158`) και δεν τον προσθέτει στα locks.
- `GOVERNANCE_EXCEPTION_FAIL_CLOSED` (`:1622`): προστίθεται στο μονοπάτι της εξαίρεσης, όπου δεν
  χτίζεται rationale. Δεν είναι στο `CANONICAL_LOCK_CODES` (μικρό εύρημα του ελέγχου SD).

Οι άλλοι εννέα κωδικοί έχουν template.

**Πόσο συχνά, στα golden του owner.** Μέτρησα στο `eff6752` τα πρωινά των τεσσάρων σεναρίων του
`tests/fixtures/daily_coach_golden/`: 47 μηνύματα. Τα 26 γράφουν ως αιτία μόνο
`DATA_MISSING_CONSERVATIVE_H2`. Επιπλέον, κάθε πρωινό στα golden έχει τουλάχιστον ένα lock
(`CS_CONFIDENCE_LOCK` πάντα) και τουλάχιστον μία πύλη UNKNOWN (H1 πάντα, αφού τα σενάρια δεν έχουν
`/injury`). Άρα σε κανένα από τα 47 μηνύματα δεν φαίνεται ποιες πύλες δεν μετρήθηκαν. Από τα 21
που δεν δείχνουν ωμό κωδικό, τα 20 ξεκινούν με πύλη που έπιασε (H4 ή H2) και 1 με το CS lock.

**Γιατί έχει σημασία.** Το ADR-0075 άφησε τις H1 και H5 χωρίς ταβάνι όταν δεν μετρήθηκαν, με το
επιχείρημα ότι «το σύστημα το δείχνει με τη λέξη UNKNOWN στο μήνυμα». Αυτό ισχύει μόνο τα πρωινά
χωρίς lock και χωρίς πύλη που έπιασε. Το «Not measured: …» είναι ο τρόπος με τον οποίο το μήνυμα
δείχνει το UNKNOWN του ADR-0075. Η αλλαγή αφορά τα πρωινά του owner, άρα είναι Κατηγορία Β και θέλει αυτό το ADR Accepted
πριν από τον κώδικα (ADR-0072).

## Options

### Επιλογή Α (προτείνεται): το rationale λέει πάντα τις πύλες που δεν μετρήθηκαν· κάθε lock έχει ανθρώπινο κείμενο

Αλλάζει μόνο το κείμενο του `primary_reason` και το `reason` των ευρημάτων των locks. Δεν αλλάζει
καμία πύλη, κανένα όριο, κανένα lock, η επιλογή της προπόνησης, το ταβάνι ή ο όγκος.

1. **Οι πύλες που δεν μετρήθηκαν, και όταν πιάσει lock ή πύλη.** Η λίστα `not_measured`
   υπολογίζεται μία φορά, πριν από την επιλογή της κύριας αιτίας, ως **ένωση** δύο πηγών:
   - οι πύλες H1–H5 με κατάσταση UNKNOWN στο rationale·
   - κάθε Hn για την οποία το `applied_locks` έχει `DATA_MISSING_CONSERVATIVE_Hn` (n = 2…5).

   Χωρίς διπλότυπα, με τη σειρά H1→H5. Έτσι το μήνυμα ονομάζει και τις τιμές που το
   `_check_hard_stops` μέτρησε ως «λείπει» (NaN, baseline ≤ 0, μη αριθμός), ακόμη κι όταν το
   εύρημα της πύλης γράφει CLEAR (κενό 1β). Πάλι αλλάζει μόνο κείμενο: η κατάσταση των ευρημάτων δεν
   αλλάζει. Η δεύτερη πηγή δεν αγγίζει το μονοπάτι χωρίς TRIGGERED, γιατί κάθε `DATA_MISSING_*` είναι
   ήδη εύρημα TRIGGERED. Το κείμενο είναι το ίδιο με το μονοπάτι CLEAR:
   - Χωρίς lock (όπως σήμερα, χωρίς καμία αλλαγή):
     `No governance lock triggered: training proceeds as planned. Not measured: H1, H5.`
   - Με lock ή πύλη που έπιασε (νέο): `<αιτία του πρώτου TRIGGERED> Not measured: H1, H2, H3.`
   - **Σειρά:** πρώτα η κύρια αιτία, όπως επιλέγεται σήμερα (πρώτο TRIGGERED· η σειρά προτεραιότητας
     είναι το XC-06 και μένει εκτός). Μετά ένα κενό και το `Not measured: …` με τελεία στο τέλος.
     Οι πύλες γράφονται με τη σειρά H1, H2, H3, H4, H5, χωρισμένες με «, ».
   - Αν η λίστα είναι άδεια, δεν προστίθεται τίποτα.
   - Το `actionable_guidance` δεν αλλάζει.
2. **Ανθρώπινο κείμενο για κάθε lock.** Μπαίνουν templates για τους οκτώ κωδικούς του πίνακα και για
   το `FAIL_SAFE_LOCK`, ώστε κάθε κωδικός του `CANONICAL_LOCK_CODES` να έχει template. Τα κείμενα
   είναι στα αγγλικά, όπως όλο το μήνυμα. Δεν γράφουν αριθμούς ορίων, ώστε να μη διαφωνήσουν ποτέ με
   το `thresholds.py`. Προτεινόμενα κείμενα (το PR αλλάζει μόνο ορθογραφία· αλλαγή νοήματος θέλει
   νέα έγκριση). Τα `INTENSITY_GATE_*` βγαίνουν από τον intensity governor
   (`intensity_governor.py:69-180`: drift, glycogen debt, ACWR, readiness, κόπωση), όχι από το VLG.
   Στο YELLOW ο governor βάζει ζώνη ≤ 3 και όγκο 0,8· στο RED ζώνη ≤ 2, όγκο 70 % και EASY
   (`:152-161`).

   | Κωδικός | Κείμενο |
   |---|---|
   | `INTENSITY_GATE_RED` | `Intensity gate RED (recovery/load signals): session limited to easy, volume reduced.` |
   | `INTENSITY_GATE_YELLOW` | `Intensity gate YELLOW: intensity capped and volume reduced.` |
   | `HARD_STOP_SAFETY_GATES` | `A hard-stop safety gate triggered: session reduced or replaced by rest.` |
   | `DATA_MISSING_CONSERVATIVE_H2` | `HRV or its baseline not available: easy-ceiling safety mode applied.` |
   | `DATA_MISSING_CONSERVATIVE_H3` | `Resting HR or its baseline not available: easy-ceiling safety mode applied.` |
   | `DATA_MISSING_CONSERVATIVE_H4` | `Training stress balance (TSB) not available: easy-ceiling safety mode applied.` |
   | `DATA_MISSING_CONSERVATIVE_H5` | `Fatigue entry missing or not a number: moderate ceiling applied.` |
   | `DATA_VOID_CONSERVATIVE` | `No fresh Garmin data for too long: zone ceiling applied.` |
   | `FAIL_SAFE_LOCK` | `A safety check could not run: conservative lock applied.` |

3. **Άγνωστος κωδικός.** Το `_format_template` δεν γυρνά ποτέ μόνο τον κωδικό. Για κωδικό χωρίς
   template γυρνά γενική πρόταση με τον κωδικό: `Safety rule applied ({code}).` Το `_format_template`
   καλεί `.format()`, άρα η εναλλακτική περνά ρητά `code=template_key`.
   Τα H1–H5 έχουν πάντα template, άρα η εναλλακτική πρόταση πιάνει μόνο μελλοντικά locks που θα
   μπουν χωρίς template. Το test 3 του σχεδίου ελέγχου το εμποδίζει έτσι κι αλλιώς.
4. **Τι δεν αλλάζει.**
   - Το `governance_outcomes` (`locks_applied_json` και όλες οι στήλες, `repositories/governance.py:221`).
   - Τα structured events (`APPLY_CONSTRAINTS` και τα events των πυλών).
   - Το `governance_locks_applied` και η σειρά του.
   - Το πεδίο `gate` και το `status` των ευρημάτων.
   - Το `operator_console.py:190`, που χτίζει τα δικά του ευρήματα από τα locks της βάσης.
   - Το `actionable_guidance` και το εναλλακτικό κείμενό του (`:1161`).

   Αλλάζει μόνο το `reason` των ευρημάτων των locks, που σήμερα είναι ο ίδιος ο κωδικός. Το
   `decision_rationale` δεν αποθηκεύεται στη βάση, άρα δεν χρειάζεται migration.

**Παράδειγμα πρωινού (από το golden `garmin_outage`).** Το Garmin δεν συνδέεται. Λείπουν HRV, RHR και
TSB, και δεν υπάρχει `/injury`. Η προπόνηση βγαίνει EASY.
- Σήμερα: `Why this decision: DATA_MISSING_CONSERVATIVE_H2`
- Με την Α: `Why this decision: HRV or its baseline not available: easy-ceiling safety mode applied. Not measured: H1, H2, H3, H4.`

Η προπόνηση, τα locks και η βάση μένουν ίδια.

**Η περίπτωση του ελέγχου SD.** Τα δεδομένα είναι κανονικά, δεν υπάρχει `/injury`, και το CS δεν
είναι βαθμονομημένο.
- Σήμερα: `Critical speed confidence below threshold; recalibration required.` Το μήνυμα δεν λέει ότι
  η H1 δεν μετρήθηκε.
- Με την Α: προστίθεται `Not measured: H1.`

### Επιλογή Β: ξεχωριστή γραμμή στο μήνυμα, όχι μέσα στο rationale

Μία νέα γραμμή στο `send_daily_coaching`, π.χ. `❔ Not measured: H1, H5`, από νέο πεδίο του payload.
Θα ήταν πιο ορατό, αλλά:

- Αλλάζει τρία σημεία αντί για ένα: rationale, payload και `contracts.py`, και το Telegram.
- Τα πρωινά χωρίς lock θα έλεγαν το ίδιο πράγμα δύο φορές, εκτός αν αλλάξει και το μονοπάτι CLEAR,
  που σήμερα είναι σωστό και έχει tests (`test_unmeasured_gates_unknown.py:79-86`).
- Η πληροφορία φεύγει από το `decision_rationale`, το αρχείο της εξήγησης του ADR-0038.

Απορρίπτεται. Η Α κρατά μία πηγή για την εξήγηση και την ίδια διατύπωση και στα δύο μονοπάτια.

### Επιλογή Γ: πλήρης αναδιάταξη του rationale με σειρά σπουδαιότητας

Η κύρια αιτία επιλέγεται με προτεραιότητα, π.χ. hard stop, μετά ελλιπή δεδομένα, μετά αποτυχία
αποθήκευσης, μετά CS. Το rationale γράφει όλα τα locks με τη σειρά. Λύνει μαζί το SD-06 και το XC-06,
αλλά:

- Αλλάζει την κύρια αιτία σε πολλά πρωινά.
- Θέλει απόφαση του owner για τη σειρά, που είναι ξεχωριστό ερώτημα (XC-06).
- Κάνει το diff των golden πολύ μεγαλύτερο και δυσκολότερο να ελεγχθεί.

Απορρίπτεται για τώρα. Το XC-06 ακολουθεί τη σειρά του πλάνου με δικό του ADR. Η Α δεν το δυσκολεύει:
το `Not measured: …` μένει στο τέλος, όποια κι αν είναι η κύρια αιτία.

### Επιλογή Δ: μόνο τα templates, χωρίς το «Not measured» στα πρωινά με lock

Διορθώνει τους ωμούς κωδικούς, αλλά αφήνει το κύριο κενό: με lock, ο owner δεν μαθαίνει ότι η H1 ή η
H5 δεν μετρήθηκαν. Αυτό είναι ακριβώς ό,τι υποθέτει το ADR-0075. Απορρίπτεται.

## Decision

**Επιλογή Α**, όπως είναι γραμμένη παραπάνω. Ο owner τη διάλεξε με κάρτα απόφασης (2026-11-01, 06:01 UTC,
βλ. «Απόφαση του owner» στο τέλος).

Ένα PR κώδικα, με τα tests του σχεδίου ελέγχου παρακάτω. Τα fingerprints των golden
του owner αλλάζουν μόνο μετά από έγκρισή του (ADR-0067 D3.4).

## Εκτός πεδίου

- **XC-06:** η σειρά σπουδαιότητας της κύριας αιτίας. Η κύρια αιτία μένει «το πρώτο TRIGGERED»
  (`governance_engine.py:1298`).
- **XB-18:** η διάρκεια σε λεπτά και η μέγιστη ζώνη (`max_zone`) στο μήνυμα. Η γραμμή «Today» μένει
  όπως είναι.
- **SD-17 (νέο εύρημα, HIGH, διαδρομή governance):** στο rationale η κατάσταση ανά πύλη γράφει CLEAR
  για NaN, baseline ≤ 0 ή μη αριθμό, ενώ η πύλη έχει μετρήσει την τιμή ως «λείπει» και έχει βάλει
  `DATA_MISSING_CONSERVATIVE_Hn`. Αυτό συγκρούεται με το ADR-0069 §3 (ό,τι δεν μετρήθηκε δεν γράφεται
  CLEAR). Η Α διορθώνει μόνο τι λέει το μήνυμα (σημείο 1, δεύτερη πηγή)· τα `status` των ευρημάτων
  μένουν όπως είναι. Το SD-17 καταγράφεται στο register και ακολουθεί τη σειρά του πλάνου.
- **XB-20:** το electrolyte alert που υπολογίζεται αλλά δεν δείχνεται.
- Τα ονόματα των πυλών στο `Not measured` (π.χ. «injury» αντί για «H1»). Μένουν οι κωδικοί H1–H5,
  όπως στο μονοπάτι CLEAR και στο ADR-0075.
- Το `actionable_guidance` για locks χωρίς δική τους οδηγία. Σήμερα παίρνουν γενικό ανθρώπινο κείμενο
  (`:1161`), όχι ωμό κωδικό.
- Το μονοπάτι της εξαίρεσης (`GOVERNANCE_EXCEPTION_FAIL_CLOSED`, `:1590-1624`), όπου δεν χτίζεται
  rationale, και η προσθήκη αυτού του κωδικού στο `CANONICAL_LOCK_CODES`.
- Οποιαδήποτε αλλαγή σε πύλη, όριο, ταβάνι ή επιλογή προπόνησης.

## Consequences (της Α)

- **Θετικά:**
  - Κάθε πρωινό μήνυμα λέει ποιες πύλες H1–H5 δεν μετρήθηκαν, με ή χωρίς lock, εκτός από το μονοπάτι
    του exception (`governance_engine.py:1590-1624`), όπου δεν φτιάχνεται rationale (εκτός πεδίου). Η
    υπόθεση του ADR-0075 («το μήνυμα γράφει UNKNOWN») ισχύει πια σε κάθε άλλη περίπτωση.
  - Κανένας ωμός κωδικός lock δεν φτάνει στον owner.
  - Ολοκληρώνεται το «ένα template για κάθε πύλη» του ADR-0038, και το φυλάει test.
- **Ουδέτερα:**
  - Η βάση, τα events, τα locks και η απόφαση μένουν ίδια.
  - Το `governance_golden.json` δεν αλλάζει: είναι σενάριο χωρίς lock, με όλες τις πύλες CLEAR.
- **Αρνητικά:**
  - Το μήνυμα μακραίνει: το `Not measured: …` προσθέτει ως ~34 χαρακτήρες, και όπου ένας ωμός
    κωδικός γίνεται πρόταση, άλλους ~30.
  - Όταν η κύρια αιτία είναι `DATA_MISSING_CONSERVATIVE_Hn`, η πύλη Hn αναφέρεται δύο φορές, στην
    αιτία και στο `Not measured`. Είναι σκόπιμη απλοποίηση: ο κανόνας μένει ένας και ίδιος σε όλα τα
    πρωινά.
  - Η H1 θα γράφεται `Not measured` σχεδόν κάθε πρωί, όσο ο owner δεν χρησιμοποιεί το `/injury`. Αυτή
    είναι η εξαίρεση του ADR-0075, που τώρα φαίνεται.
- **CONTRACT 7.9 §13:** η αλλαγή δεν χαλαρώνει καμία πύλη. Δεν αγγίζει τον υπολογισμό, τα όρια ή τα
  ταβάνια. Αλλάζει μόνο κείμενο, και δείχνει περισσότερα από όσα δείχνει σήμερα.

## Επίπτωση στα golden (`tests/fixtures/daily_coach_golden`)

Στο `eff6752` μέτρησα σε όλα τα πρωινά των τεσσάρων σεναρίων ποιες πύλες είναι UNKNOWN και ποια είναι η
κύρια αιτία. Τα πρωινά αυτά είναι 54 κλήσεις του rationale σε 6 tests και 47 μηνύματα στα αρχεία.
Κάθε πρωινό έχει lock και τουλάχιστον μία πύλη UNKNOWN, άρα **αλλάζει η γραμμή «Why this decision» σε
όλα τα μηνύματα και των τεσσάρων σεναρίων**. Τίποτε άλλο στα αρχεία δεν πρέπει να αλλάξει (events,
πίνακες, άλλες γραμμές του μηνύματος).

| Σενάριο | Μηνύματα | Σήμερα | Με την Α (παράδειγμα) |
|---|---|---|---|
| `garmin_outage` | 7 | 7 × `DATA_MISSING_CONSERVATIVE_H2` | `HRV or its baseline not available: … Not measured: H1, H2, H3[, H4].` |
| `persistence_failure` | 5 | 5 × `DATA_MISSING_CONSERVATIVE_H2` | ίδιο σχήμα, `H1, H2, H3[, H4]` |
| `three_weeks_weekly_plan` | 21 | 7 × ωμός κωδικός, 13 × TSB, 1 × CS | ωμός → template + `Not measured`· TSB και CS + `Not measured: H1.` |
| `two_weeks_worker` | 14 | 7 × ωμός κωδικός, 6 × TSB, 1 × HRV | ωμός → template + `Not measured: H1, H2[, H3][, H4][, H5].`· TSB/HRV + `Not measured: H1, H5.` |

- **Θέλουν έγκριση του owner:** και τα τέσσερα fingerprints του `_DAILY_COACH_DAYS` στο
  `tests/test_owner_baseline.py`. Το PR δείχνει στον owner, πριν από το merge, ένα πρωινό από κάθε
  σενάριο πριν και μετά. Δείχνει επίσης ότι το diff αγγίζει μόνο τη γραμμή «Why this decision».
  Τα fingerprints ενημερώνονται με σχόλιο έγκρισης, όπως έγινε για το D-218.
- **Δεν αλλάζει:** το `_GOVERNANCE` fingerprint (`governance_golden.json`).

## Σχέδιο ελέγχου (tests)

Πρώτα γράφονται τα tests που αποτυγχάνουν πριν από την αλλαγή:

1. **Lock + πύλη που δεν μετρήθηκε.** Στο επίπεδο του `GovernanceEngine.apply_constraints`: χωρίς
   `injury_flag`, με κανονικές HRV, RHR και TSB, με κόπωση της ημέρας δηλωμένη
   (`subjective_fatigue_measured=True`, ώστε η H5 να μην είναι UNKNOWN), και με ένα lock (π.χ.
   `CS_CONFIDENCE_LOCK`). Το
   `primary_reason` τελειώνει σε `Not measured: H1.` Αποτυγχάνει σήμερα. Είναι η μεταφορά του
   `test_h1_missing_is_unknown_and_told` στα tests του repo.
2. **Λείπει η HRV.** Το `primary_reason` δεν είναι ο σκέτος κωδικός. Είναι το template του
   `DATA_MISSING_CONSERVATIVE_H2` και μετά `Not measured: …`, με το H2 μέσα. Αποτυγχάνει σήμερα.
2β. **Τιμή NaN με άλλο lock μπροστά (κενό 1β).** HRV NaN, και ένα lock που μπαίνει πριν από το
   `DATA_MISSING_CONSERVATIVE_H2` (π.χ. `READINESS_2OF4_DOWNGRADE` ή `INTENSITY_GATE_YELLOW`). Το
   `primary_reason` περιέχει `Not measured:` με το `H2` μέσα, ενώ το εύρημα H2 μένει CLEAR (SD-17,
   εκτός πεδίου). Αποτυγχάνει σήμερα. Παραλλαγές με παραμέτρους: baseline HRV 0 (H2), RHR NaN (H3),
   TSB NaN (H4), κόπωση `'abc'` (H5).
3. **Κάθε κωδικός του `CANONICAL_LOCK_CODES` έχει template** στο `GATE_RATIONALE_TEMPLATES`.
   Αποτυγχάνει σήμερα για τους εννέα κωδικούς του σημείου 2 της Α.
4. **Κάθε κωδικός που προσθέτει το `apply_constraints` είναι στο `CANONICAL_LOCK_CODES`.** Το test
   σαρώνει τα `applied_locks.append("…")` του `governance_engine.py`. Περνά σήμερα· φυλάει ώστε νέο
   lock να μην ξεφύγει από το test 3.
5. **Άγνωστος κωδικός.** Το `_format_template("SOME_NEW_LOCK")` περιέχει τον κωδικό και **δεν** είναι
   ίσο με αυτόν.
5β. **Χωρίς αριθμούς στα νέα templates.** Κανένα από τα εννέα νέα templates αυτού του ADR δεν περιέχει
   ψηφίο, ώστε να μη διαφωνεί ποτέ με το `thresholds.py`. Τα δύο εγκεκριμένα templates που έχουν ήδη
   ψηφία ως όνομα κανόνα («2 of 4» στο `READINESS_2OF4_DOWNGRADE`, «VO2» στο `VO2_ELIGIBILITY_GATE`)
   μένουν όπως είναι.
6. **Τίποτε άλλο δεν αλλάζει.** Για τις ίδιες εισόδους, τα `session_type`, `max_zone`,
   `volume_modifier`, `governance_locks_applied` και τα `gate`/`status` των ευρημάτων μένουν ίδια.
   Τα tests του μονοπατιού CLEAR (`test_unmeasured_gates_unknown.py:79-86`) περνούν χωρίς αλλαγή.
7. **Τέλος της αλυσίδας.** Από το rationale μέχρι το κείμενο του `send_daily_coaching`, η γραμμή «Why
   this decision» περιέχει `Not measured:` όταν πιάνει lock. Οι κάτω παύλες των κωδικών στην
   εναλλακτική πρόταση γίνονται escape (το ήδη υπάρχον `test_telegram_markdown_escape.py` καλύπτει
   τον μηχανισμό).

Τα golden τρέχουν πριν και μετά, και το diff ελέγχεται όπως λέει η προηγούμενη ενότητα. Τρέχουν τα
blocking gates του CI: `ruff` και ολόκληρο το `pytest`.

## Απόφαση του owner

Ο owner διάλεξε την **επιλογή Α** στην κάρτα «Εγκρίνεις το ADR-0081 για το πρωινό μήνυμα (SD-06);» (2026-11-01, 06:01 UTC). Ισχύουν τα σημεία της Α και η λίστα «Εκτός πεδίου» όπως είναι γραμμένα παραπάνω. Ένα PR κώδικα, με τα tests του σχεδίου που αποτυγχάνουν πριν, και με τα golden του owner πριν και μετά· οι νέες τιμές των golden χρειάζονται την έγκριση του owner πριν από το merge (ADR-0067 D3.4).
