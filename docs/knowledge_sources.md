# Updating knowledge and dealer-location data

`CFC_Co_Bay_FAQ.md` is a source document, not a file that the chatbot reads on
every customer message.  Keeping it outside the runtime prompt prevents an
unreviewed edit from becoming an immediate customer-facing claim.

## Markdown FAQ lifecycle

1. Edit `CFC_Co_Bay_FAQ.md`. Keep one FAQ per Markdown table row and retain a
   question column plus an answer column.
2. If the table headers or file path change, update
   `config/data_sources/markdown_mapping.json`; this maps source columns and
   defaults without application-code changes.
3. Stage the configured source with `POST /admin/catalog/import-markdown`.
   The endpoint creates a checksum-addressed import batch; it does not publish
   anything.
4. Inspect it with
   `GET /admin/catalog/import-batches/CFC/{batch_id}/records`. Reject unsafe,
   outdated, duplicate, or incomplete rows with
   `POST /admin/catalog/import-batches/CFC/{batch_id}/review-record` before
   approving the batch.
5. Approve the remaining records with
   `POST /admin/catalog/import-batches/CFC/{batch_id}/approve`, then publish
   only after business/technical review with
   `POST /admin/catalog/import-batches/CFC/{batch_id}/publish`.

Publishing is an atomic CFC knowledge-snapshot change: the new approved batch
becomes the active CFC catalog and the prior source-backed CFC snapshot is
deactivated. Use the existing publication rollback endpoint if review finds a
problem. Re-importing unchanged content is idempotent; editing the file creates
a new checksum batch for review.

The legacy FAQ has broad agricultural claims but no reliable routing metadata.
The importer therefore defaults it to generic `faq` and `MEDIUM` risk in the
mapping. It is quarantined by default; do not bulk-publish it until each claim
has been reviewed and, where needed, given proper category/risk metadata.

## Administrative-area and dealer lookup data

`config/normalization/administrative_areas.json` is the configurable gazetteer
for province, district, ward, or commune records. Each row can contain a
canonical name, unaccented aliases, parent province, and optional authoritative
latitude/longitude centroid. Add or correct localities there; application code
does not contain a list of business areas.

Dealer records come from the CRM warmer (`cfc:dealers:locations`). A customer
can receive up to three entries only when their CRM address exactly matches the
configured locality, or when both the requested area and CRM dealer records
have coordinates that support distance ordering. A parent-province text match
alone is not called "nearest". When no such evidence exists, the conversation
stores `dealer_search_status=NO_CONFIRMED_MATCH` and the reply says that no
record has been confirmed rather than claiming that data are being updated.

## Support contacts and hotline

`config/business/support_contacts.json` is the customer-facing contact
directory. It is page-scoped and contains the approved people, roles, phone
numbers, company hotline, workflow-to-purpose mapping, and contact-request
markers. Contact details are selected and rendered deterministically after LLM
generation; names and numbers are never delegated to the model.

For CFC, price workflows route to the configured sales contact, agriculture
workflows choose one configured agronomist consistently for the same customer,
and a direct request for a phone number is routed by its configured markers.
The company hotline is included when the selected purpose enables it. ZEO does
not inherit CFC contacts.

To update a person or phone number, edit this JSON and restart the worker. Keep
contact IDs stable when only changing a name/title/number; changing route lists
changes which customers are assigned to each contact. Startup validates page
codes, workflow names, referenced contact IDs, duplicate IDs, and Vietnamese
phone formats, so invalid contact data fails before a message can be sent.
