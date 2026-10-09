# Cortex — security model

What Cortex defends against, how, and where each defence is checked. Every control below is held
by a test in the platform's suite — over four thousand of them are security tests — and the build
fails when one stops holding.

---

## Who it defends against

| Adversary | Starting point | What stops them |
| --- | --- | --- |
| An outsider on the network | No credentials | TLS at the edge; sessions bound to a client key; rate limits per client and per address |
| A thief with a token | An access token from a log or a proxy | The token is inert without the private key that signs each request's proof |
| An insider with an operator account | Legitimately signed in | Capabilities enforced server-side; every mutation recorded in a chain they cannot alter |
| A compromised dependency | Code running in the process | Egress refused at the socket *and* at the node; the database refuses what the application's login may not do |
| A compromised operational database credential | Rows of one datastore | The audit chain is on another instance, under another owner, signed with a key in neither |
| One tenant probing another | A valid session in tenant A | The tenant predicate is added by the persistence layer to every query, not by each query's author |

## Identity and sessions

* **Proof of possession.** Every request carries a DPoP proof signed by the client's private key;
  each proof's id is burned in a replay cache shared by every API process.
* **Assurance levels.** A password is level 1; a one-time code or a second factor is level 2; a
  hardware security key (WebAuthn, attestation verified against the FIDO Metadata Service) is
  level 3. Each capability states the level it needs, and a session below it is asked to step up
  rather than refused.
* **Passwords** are hashed with Argon2id. Failed attempts are counted before the password is
  checked and lock the account for a period that lapses on its own, and sign-in is rate limited
  per address across every API process.

## Authorisation

* **198 capabilities**, each with a risk tier, the archetypes that may ever hold it and the
  assurance it needs. A role is a set of grants; a grant can be scoped to an organisational
  subtree, to listed records or to labels.
* **Nobody grants what they do not hold**, and no role exceeds its archetype's ceiling — the same
  rules for the role editor, presets and every other path that creates a role.
* **Decisions are made against a policy version** asserted under lock before a privileged write
  commits, so a permission revoked mid-request is not exercised by the request already running.
* **Object-level checks are compiled into queries**, so a listing returns only the rows the
  session may see, and each row carries what the session may do to it.

## The audit trail

* **Every mutation is recorded, before it commits.** A write the chain cannot record is refused.
* **Append-only at three levels**: grants that withhold UPDATE and DELETE from the application,
  row triggers that refuse them, and event triggers that refuse dropping the tables or disabling
  the triggers. The application's login owns nothing it could switch off.
* **Hash-chained and signed.** Each record carries the hash of the one before it; checkpoints are
  signed with Ed25519 under a key held outside both datastores, and the key manifest records which
  key signed which checkpoint.
* **Verified on demand and at every start.** Verification fails at the first record whose hash or
  signature does not hold, and says which. Production refuses to start when the separation that
  makes the chain evidence does not hold.

## Data

* **Sensitive columns are sealed** with authenticated encryption under a key-encryption key the
  operator holds; tax identifiers are hashed for lookup and destroyed on erasure.
* **Erasure reaches everything**, the knowledge index included: passages, vectors and the answers
  that quoted them.
* **Personal data is masked before a model sees it**, and retrieval returns only what the asking
  session may read.
* **Webhook payloads withhold fields** the catalogue marks as not for receivers, and carry no
  free text an operator typed.

## The network

* **Egress is an allow-list**, enforced twice: by the application — resolving the name, refusing
  private ranges and the metadata service, and pinning the address it checked — and by a
  default-deny network policy, which still holds when the process has been subverted.
* **The deployment's controls are literals**: non-root, read-only root filesystem, every Linux
  capability dropped, no service-account token, the restricted Pod Security Standard. A value an
  operator can override on a command line is a default, not a control.

## Supply chain

Dependencies are installed from hash-pinned locks; the image is built from them alone, on base
images pinned by digest; a CycloneDX bill of materials is generated from the installed
environment and checked in the build; and every component is cross-referenced against known
advisories by an offline gate that fails on a blocking finding.

---

*Gonzalo Romero — sole author.*
