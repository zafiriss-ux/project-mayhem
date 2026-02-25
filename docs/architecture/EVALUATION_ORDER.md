\# TITAN OS — Evaluation Order



\## Core Principle

Safety precedes load.

Load precedes intensity.

Intensity precedes performance projection.



---



\## Execution Order (Hard Hierarchy)



1\. Injury Risk Gate

2\. Volume Load Gauge (VLG)

3\. Adaptive Priority Lock (APL)

4\. Session Generator

5\. Sustainability Score (Output Layer)



---



\## Hard Stops



\- Injury Risk = High → No intensity allowed

\- Composite Load = Critical → Force recovery / deload

\- Autonomic instability → Intensity cap



---



\## Confidence Flags



Every module must expose:

\- confidence\_score (0–1)

\- data\_stability\_flag

\- override\_flag (if user forces bypass)



---



\## Override Policy



Overrides are:

\- Logged

\- Counted

\- Penalized in sustainability score



No silent bypass allowed.

