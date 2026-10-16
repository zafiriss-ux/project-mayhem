# CHANGELOG

Μία γραμμή ανά PR που μπήκε στο `main`, από την αρχή του refactor (#874) και μετά, με τον τίτλο
του PR όπως είναι. Νεότερα πρώτα. Οι αλλαγές πριν από το #874 είναι στο [`CHANGES.md`](CHANGES.md)
(ιστορικό, δεν ενημερώνεται). Κανόνας: κάθε PR προσθέτει τη γραμμή του εδώ (ADR-0061).

## Επόμενη έκδοση

- #1010 (2026-10-16) fix: ο έλεγχος διαθεσιμότητας παπουτσιού δεν σκάει πια για παπούτσι που έχει χρησιμοποιηθεί (F8, D-069)
- #1009 (2026-10-16) fix: ρεκόρ με απόσταση ή χρόνο ≤ 0 απορρίπτεται με ValueError αντί για διαίρεση με το μηδέν (F10, D-068)
- #1008 (2026-10-16) fix: προπόνηση χωρίς παλμό διαβάζεται με avg_hr κενό αντί για 0 και ο browser δείχνει «—» (F7, D-067)
- #1007 (2026-10-16) fix: τρεις συνεχόμενες νύχτες με score ύπνου κάτω από 60 κάνουν τη μέρα EASY με 70% του όγκου (SV-16, ADR-0066, D-066)
- #1005 (2026-10-15) fix: στη φάση TAPER ένα TSB πάνω από +5 λέγεται «FRESH (taper)» αντί για DETRAINING (SV-13, D-064)
- #1004 (2026-10-10) fix: με παλιά ή άκυρα δεδομένα Garmin η προπόνηση που γίνεται EASY κρατά 70% του όγκου και το πολύ 45' (SV-22, D-063)
- #1003 (2026-10-10) fix: ο εβδομαδιαίος planner ακολουθεί τα km των 4 τελευταίων εβδομάδων του αθλητή, +10% το πολύ, 30 km χωρίς ιστορικό (SV-14, D-062)
- #1002 (2026-10-10) fix: η Κυριακή της εβδομάδας TAPER είναι EASY 8 km αντί για RACE 42,195 km (SV-13, D-061)
- #1001 (2026-10-10) fix: προπόνηση που υποβαθμίζουν 2of4, hard stop, VO2 ή fueling κρατά 70% του όγκου και το πολύ 60' (SV-04, ADR-0065, D-060)
- #1000 (2026-10-10) fix: η H2 δίνει REST όταν το HRV πέφτει 15 ms ή 30% κάτω από τη βάση, ό,τι έρθει πρώτο (SV-10, ADR-0064, D-059)
- #999 (2026-10-10) fix: το μεγάλο τρέξιμο 90'+ χωρίς επιβεβαιωμένο fueling μένει LONG_RUN, με υπενθύμιση για φαγητό ή τζελ στο πρωινό μήνυμα (SV-05, ADR-0063, D-058)
- #998 (2026-10-10) fix: το RED της πύλης έντασης δίνει ρητά 70% όγκο και το governance διαβάζει το 0,0 ως 0,0 (SV-20, ADR-0062, D-057)
- #997 (2026-10-10) fix: το HRV είναι ο μέσος όρος της νύχτας από το Garmin (`lastNightAvg`)· οι 28 τελευταίες νύχτες ξαναγράφονται μία φορά (SV-12, D-056)
- #996 (2026-10-10) fix: με λίγο ιστορικό, το πρωινό φέρνει 210 μέρες προπονήσεων από το Garmin, ώστε το TSB να μην πέφτει ψεύτικα κάτω από −50 (D-055)
- #995 (2026-10-10) fix: η κονσόλα δείχνει το ίδιο ACWR με το πρωινό (D-054)
- #994 (2026-10-10) test: τα goldens του DailyCoach βλέπουν το φορτίο των σεναρίων (SV-19, D-053)
- #993 (2026-10-10) fix: τρέξιμο ή ύπνος σε λάθος μονάδα αποθηκεύεται με σήμα ποιότητας (SV-17, D-052)
- #992 (2026-10-10) fix: το TSB μετρά κάθε μέρα, με τον τύπο του TrainingPeaks (SV-08, D-051)
- #991 (2026-10-10) fix: παλμός ηρεμίας και σκορ ύπνου που λείπουν μένουν κενά (SV-06, D-050)
- #990 (2026-10-10) fix: αιτιολόγηση στις ψευδείς ειδοποιήσεις Bandit και DevSkim (D-049)
- #989 (2026-10-10) fix: το SHA-1 του import CSV δηλώνεται ως μη κρυπτογραφικό (#44, D-049)
- #988 (2026-10-10) docs: οι ειδοποιήσεις ασφαλείας του code scanning μπαίνουν στο πλάνο (D-049)
- #987 (2026-10-10) fix: χωρίς σημερινό HRV η μέρα παίρνει ταβάνι EASY (SV-06, D-048)
- #986 (2026-10-10) fix: οι αριθμοί στρογγυλεύονται στα μηνύματα του Telegram (SV-07, D-047)
- #985 (2026-10-10) fix: η ημέρα REST μένει REST όταν μια πύλη ζητά EASY (SV-03, D-046)
- #984 (2026-10-10) fix: το ESI παίρνει τον καιρό της ημέρας (SV-21, D-045)
- #983 (2026-10-10) fix: το ACWR υπολογίζεται από τα φορτία της βάσης (SV-01, D-044)
- #982 (2026-10-10) fix: ο συντελεστής όγκου της πύλης έντασης εφαρμόζεται· soreness 3 όταν λείπει (SV-04, SV-09, D-043)
- #981 (2026-10-10) fix: η ρουτίνα παίρνει τη φάση από το προφίλ του αθλητή (SV-02, D-042)
- #980 (2026-10-10) test: έλεγχος με συνθετικούς αθλητές και αναφορά (εργασία 12, D-041)
- #979 (2026-10-10) fix: η φόρτωση του CS μετρά κάθε δοκιμή, ώστε το CS_CONFIDENCE_LOCK να μπορεί να σηκωθεί (D-040)
- #978 (2026-10-10) feat: χειροκίνητη καταχώρηση δοκιμής ταχύτητας για το Critical Speed (Telegram και κονσόλα, D-039)
- #977 (2026-10-09) fix: όταν μια πύλη κάνει την προπόνηση REST, η απόσταση και η διάρκεια γίνονται 0
- #976 (2026-10-09) feat(db): οι επιδόσεις CS διαβάζονται ανά αθλητή (εργασία 11, στάδιο 3)
- #975 (2026-10-09) feat(db): το log_cs_performance γράφει τον αθλητή (εργασία 11, στάδιο 2)
- #974 (2026-10-09) feat(db): στήλη athlete_id στο cs_performances, σχήμα v28 (εργασία 11, στάδιο 1)
- #973 (2026-10-09) refactor: ό,τι SQL έμενε στο database.py πάει στα repositories (εργασία 10)
- #972 (2026-10-09) refactor: το thread της πρωινής ρουτίνας βγαίνει από το DailyCoach (εργασία 9, ADR-0058 Phase C)
- #971 (2026-10-09) ci: το Docker smoke κατεβάζει τις εικόνες του Docker Hub από το mirror.gcr.io
- #970 (2026-10-09) refactor: το DailyCoach παίρνει το προφίλ του αθλητή ως αντικείμενο (εργασία 8, T5-117)
- #969 (2026-10-09) refactor: το _decision_pipeline χωρίζεται σε μία μέθοδο ανά βήμα (εργασία 7)
- #968 (2026-10-09) docs: ο έλεγχος με συνθετικούς αθλητές μπαίνει στο πλάνο ως εργασία 12
- #967 (2026-10-09) ci: Bandit, DevSkim και επιπλέον κανόνες ασφαλείας στο CodeQL
- #966 (2026-10-09) refactor: η αποθήκευση των δεδομένων Garmin βγαίνει από το DailyCoach (εργασία 6)
- #965 (2026-10-09) feat(worker): εβδομαδιαίο πλάνο κάθε Κυριακή, αποθηκευμένο στη βάση (D-020, schema v27)
- #964 (2026-10-09) fix: το όριο INV-24 μικραίνει και την απόσταση της προπόνησης
- #963 (2026-10-09) fix: οι μέρες χωρίς δεδομένα Garmin δεν γράφουν ψεύτικο ύπνο στη βάση
- #962 (2026-10-09) fix: ο glycogen παίρνει φορτίο από το Garmin και ανακάμπτει ρεαλιστικά
- #961 (2026-10-09) fix: τα ευρήματα του CodeQL (#22, #23, #24)
- #960 (2026-10-09) build(deps): Bump the python-minor-and-patch group with 2 updates
- #959 (2026-10-09) ci(deps): Bump actions/dependency-review-action from 4 to 5 in the github-actions group
- #958 (2026-10-09) ci: εργαλεία ασφάλειας για το δημόσιο repo (CodeQL, Dependency Review, SECURITY.md)
- #957 (2026-10-09) fix: παλμός ηρεμίας από το Garmin και ύπνος της σωστής νύχτας
- #956 (2026-10-09) fix: οι ειδοποιήσεις Telegram που δεν έφταναν ποτέ
- #955 (2026-10-09) test: tests που κλειδώνουν τη συμπεριφορά του DailyCoach (εργασία 5)

## v5.8.4

- #954 (2026-10-09) chore(release): έκδοση 5.8.4 (εργασία 4)
- #953 (2026-10-09) docs: έγγραφα που λένε την αλήθεια (εργασία 3)
- #952 (2026-10-09) docs: CHANGELOG.md και DECISIONS.md (εργασία 2)
- #951 (2026-10-09) docs(adr): ADR-0061 κανόνες εργασίας του owner (εργασία 1)
- #950 (2026-10-09) fix(worker): SIGTERM can no longer be lost while the worker sleeps
- #949 (2026-10-09) docs(progress): PRs #943–#948 and the decisions of 2026-10-09
- #948 (2026-10-09) fix(garmin): refuse a malformed TITAN_GARTH_TOKEN_KEY at construction (RBP-04, F-10)
- #947 (2026-10-09) feat(telegram): override nonces survive restarts (ADR-0060 D2)
- #946 (2026-10-09) fix(api): reject a JWT key pair that does not match when the app is built (RBP-04)
- #945 (2026-10-09) feat(worker): durable once-per-day morning routine (ADR-0060 D1, schema v26)
- #944 (2026-10-09) test: keep the test suite out of the real home folder
- #943 (2026-10-09) fix(launcher): stop the logging error loop that filled memory

## v5.8.3 (2026-10-09)

Περιλαμβάνει και την 5.8.2 (#937), για την οποία δεν βγήκε tag.

- #942 (2026-10-09) chore(release): version 5.8.3 for the exe fixes from the audit
- #941 (2026-10-09) fix(launcher): let TITAN.exe keep its Garmin session
- #940 (2026-10-09) fix(logging): record INFO events in titan.log and keep it in the data folder
- #939 (2026-10-09) fix(launcher): keep profile edits made in TITAN.exe
- #938 (2026-10-09) fix(api): only coaches may use the /coach/* health-data routes
- #937 (2026-10-09) fix(launcher): build TITAN.exe with a console window (v5.8.2)

## v5.8.1 (2026-10-08)

- #936 (2026-10-08) fix(launcher): start on Windows when Documents is unusable or there is no console

## v5.8.0 (2026-10-08)

- #935 (2026-10-08) ci(release): attach the zip when the Release was published from the web
- #934 (2026-10-08) docs(progress): record the 5 EUR Actions budget
- #933 (2026-10-08) docs(progress): record Zaf's decisions on #20, lockout keying and PostgreSQL
- #932 (2026-10-07) docs(progress): record where plan tasks #21-#24 stand
- #931 (2026-10-07) docs(registry): close TODO-P26-04c; lock per-athlete offset loading (T-PRA-32)
- #930 (2026-10-07) fix(telegram): audit /sync, /manual_entry and override before the effect (INV-22)
- #929 (2026-10-07) fix(api): same login failure for locked accounts; HttpOnly CSRF cookie (RBP-05)
- #928 (2026-10-07) feat(api): cap request body size before parsing (RBP-01)
- #927 (2026-10-07) fix(api): write the coach audit record before the action, fail closed (plan #21α, INV-22)
- #925 (2026-10-07) refactor(db): schema migration steps into their own module (plan #18ι)
- #924 (2026-10-07) ci: extend database.py-scoped gates and owners to titan/core/repositories (plan #18)
- #923 (2026-10-07) refactor(db): auth, lockout, RBAC and coach audit into AccessRepository (plan #18θ)
- #922 (2026-10-07) refactor(db): backups and integrity check into OperationsRepository (plan #18η)
- #921 (2026-10-07) refactor(db): sync, degraded mode and nutrition prefs into OperationsRepository (plan #18ζ)
- #920 (2026-10-07) refactor(db): threshold offsets and cold start into GovernanceRepository (plan #18ε2)
- #919 (2026-10-07) refactor(db): override log and governance decisions into GovernanceRepository (plan #18ε)
- #918 (2026-10-07) refactor(db): physiology SQL into PhysiologyRepository (plan #18δ)
- #917 (2026-10-07) refactor(db): training log SQL into TrainingRepository (plan #18γ)
- #916 (2026-10-07) ci: compose smoke test in GitHub Actions; restart both containers (#19)
- #915 (2026-10-07) refactor(db): personal bests and CS performances in TrainingRepository (#18)
- #914 (2026-10-07) test(e2e): worker killed and restarted on one SQLite file (#19)
- #913 (2026-10-07) refactor(db): repositories package; shoe SQL in TrainingRepository (#18)
- #912 (2026-10-07) test(e2e): legacy database upgrades to the current schema with data intact (#19)
- #911 (2026-10-07) refactor(profile): worker and console read one athlete profile (#17)
- #910 (2026-10-07) feat(release): Windows zip in the release workflow; one launcher version (#16)
- #909 (2026-10-07) feat(release): tagged releases to ghcr.io, pinned prod compose, rollback runbook (RE-01..04, T-PRA-09)
- #908 (2026-10-07) feat(worker): heartbeat healthcheck, scheduler watchdog, callback isolation (INV-23, T-PRA-22)
- #907 (2026-10-07) docs(adr): propose ADR-0060 durable worker state (needs Zaf's approval)
- #906 (2026-10-07) feat(backup): verified off-volume backups, retention and restore drill (T-PRA-08)
- #905 (2026-10-07) fix(coach): enforce an INVALID data-trust verdict (INV-24, T-PRA-24)
- #904 (2026-10-07) fix(telegram): fail closed when no trusted chat is configured (T-PRA-02)
- #903 (2026-10-07) fix(launcher): write GARMIN_EMAIL instead of GARMIN_USERNAME
- #902 (2026-10-07) Docs tell the truth: one ARCHITECTURE, one DEPLOYMENT_GUIDE, accurate README (task #10)
- #901 (2026-10-07) Fix Docker worker: morning routine never ran (wrong constructor arguments)
- #900 (2026-10-07) Fix flaky Hypothesis property test test_gap_flat_unchanged
- #899 (2026-10-07) Governance record: T-PRA mirror in TECHNICAL_DEBT.md, old reports archived (task #11)
- #898 (2026-10-07) Align dependencies: one source per set, dev tools out of runtime (task #8)
- #897 (2026-10-07) Remove names vulture reports as unused (task #9)
- #896 (2026-10-07) Single version source: titan.__version__ (task #7)
- #895 (2026-10-07) Move root diagnostic scripts to scripts/diagnostics (task #6)
- #894 (2026-10-07) Move the 12 root test files into tests/ (task #5)
- #893 (2026-10-07) PROGRESS.md: wave 0 complete
- #892 (2026-10-07) build(deps): Bump the python-minor-and-patch group across 1 directory with 18 updates
- #891 (2026-10-07) Complexity budget: align CI ceiling with canonical value 80
- #890 (2026-10-07) Require Python 3.12; garminconnect 0.3.5 closes PYSEC-2026-3467
- #889 (2026-10-07) build(deps): Bump pywin32 from 306 to 312
- #888 (2026-10-07) build(deps): Update setuptools requirement from >=61.0 to >=84.0.0
- #886 (2026-10-07) ci(deps): Bump the github-actions group across 1 directory with 4 updates
- #885 (2026-10-07) Remove tool-local .gitignore lines added by mistake in #884
- #884 (2026-10-07) CI: run dependency dry-run check before install (fix #879 regression)
- #883 (2026-10-07) Garmin token file: write owner-only (0600)
- #882 (2026-10-07) Dependabot: monthly grouped version updates for pip and GitHub Actions
- #881 (2026-10-07) deps: cryptography 50.0.2, pyjwt 2.15.1 (CVE fixes)
- #880 (2026-10-07) G-CI-04 (INV-03): scope PostgreSQLAdapter HRR/glycogen writes by athlete_id
- #879 (2026-10-07) CI: cut GitHub Actions cost (24 jobs → 6) with the same gates
- #878 (2026-10-07) Wave 0 (#1, #2): PROGRESS.md + pin test checks names, not versions
- #874 (2026-10-07) B-2 (INV-14) FK enforcement + B-8 (INV-25) schema forward guard
