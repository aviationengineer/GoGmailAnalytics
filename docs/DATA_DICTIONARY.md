# Data Dictionary

## contacts — one row per resolved person

| Column | Type | Description | Source / calculation |
|---|---|---|---|
| contact_id | TEXT | Stable ID (`C000001…`, ranked by message count) | resolution |
| full_name | TEXT | Best display name seen | Gmail headers |
| primary_email | TEXT | Most-used address | Gmail headers |
| alternate_emails | JSON | Other addresses merged into this person | resolution |
| company | TEXT | Derived from email domain (consumer domains excluded) | domain parse |
| industry | TEXT | Reserved for user curation | — |
| relationship_category | TEXT | Controlled taxonomy (Family/Friend/Professional/…) | categorizer |
| relationship_subcategory | TEXT | Finer taxonomy, extensible | categorizer |
| relationship_strength | INT | 1–6 from volume + reciprocity | analytics |
| importance | TEXT | High/Medium/Low (proxy by rank until curated) | analytics |
| first_communication | TIMESTAMP | Earliest message | MIN(emails.date) |
| last_communication | TIMESTAMP | Latest message | MAX(emails.date) |
| communication_count | INT | Messages involving this person | count |
| incoming_count / outgoing_count | INT | Direction split vs the mailbox owner | count |
| thread_count | INT | Distinct threads | count distinct |
| communication_frequency | TEXT | Daily…Annual/Rare/Dormant from msgs/year | analytics |
| current_status | TEXT | Active/Maintained/Dormant from recency | analytics |
| primary_topics | JSON | Top subject keywords | nlp |
| health_score | FLOAT | 0–100 explainable score | 30% recency + 25% frequency + 20% strength + 15% importance + 10% responsiveness |
| health_band | TEXT | Strong/Healthy/Maintain/At risk/Dormant | score bands |
| follow_up_required | BOOL | Whether a follow-up row exists | analytics |
| merge_confidence / merge_reason | FLOAT/TEXT | Why addresses were merged | resolution |
| source | TEXT | `Gmail (<account>)` | ingestion |

## communications — one row per message

communication_id, contact_id (best linked person), thread_id, email_id,
date, communication_type, direction, subject, participants (JSON), topic,
account.

## email_threads — one row per thread

thread_id, account, first/last_message_date, message_count, participants
(JSON), participant_count, subject, duration_days.

## organizations — one row per email domain

organization_id, organization_name, domain, first/last_contact,
contact_count, communication_count.

## topics / career_history / follow_up / data_quality / sync_state

- **topics**: topic, mentions, contact_count.
- **career_history**: contact_id, company, role, relationship
  (recruiter/job_opportunity), first/last_seen, evidence_count, confidence.
- **follow_up**: contact_id, last_contact_date, days_since_contact,
  importance, relationship_strength, historical_frequency,
  follow_up_priority (P1–P3), recommended_action, reason.
- **data_quality**: metric, value, threshold, status, checked_at.
- **sync_state**: per-target Sheets sync watermarks and counters.
