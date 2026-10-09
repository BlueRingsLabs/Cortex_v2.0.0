# Security

## Reporting a vulnerability

Please do not open a public issue. Report it privately through this repository's
**Security → Report a vulnerability** page.

Reports about the SDKs and examples here, and about the Cortex platform itself, are equally
welcome. You will have an acknowledgement within one business day and an assessment with a
remediation plan within five. There is no bug bounty and no legal threat: a report that makes
Cortex safer is welcome from anyone.

## What the SDKs guarantee

Each SDK refuses a delivery unless its signature is a valid Standard Webhooks v1 signature over
the exact bytes received, under the endpoint's secret — during a rotation Cortex signs under
both the old and the new, and either verifies — with a timestamp within five minutes of the
receiver's clock. The comparison is constant-time. Every SDK is tested against the same
deliveries the platform's own signing code produced, including the forgeries it must refuse
([`sdk/vectors.json`](sdk/vectors.json)).
