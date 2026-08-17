# User and Worker Policy

- The user gives goals through the controlled `run` entry. The Controller canonicalizes a Goal Contract before execution.
- Reversible local work within the declared task workspace may use recorded defaults.
- Payment, public publishing, account changes, credential handling, important deletion, and irreversible/high-impact actions require a scoped Human Gate.
- Revocation raises a durable fence before plan cleanup. Effects already beyond the external boundary are observed/reconciled; they are never hidden by retry.
- BROKERED and SANDBOXED Workers cannot write Controller authority. PRIVILEGED_UNBROKERED Workers can only propose production external writes.

