"""
Collaboration support for Reggie! Next (Block C - B1).

Layout (see _workspace/docs/refactor-add-features-2026_07/BLOCK_C_B1_PROTOCOL_SPEC.md):

    protocol.py   message schemas, validation and framing (no sockets)
    identity.py   host certificate, fingerprints, join code encode/decode
    auth.py       handshake nonce, key derivation, HMAC proof, lockout
    transport.py  TLS server/client, reader/writer threads, rate limiters
    discovery.py  LAN UDP broadcast probe/offer
    upnp.py       SSDP + SOAP port mapping
    session.py    roster, roles, kick/ban, chat relay, host-side authorisation
    sync.py       snapshot, op encode/apply, ref map, presence
    files.py      manifest, chunking, path/extension validation, staging

The first six modules exist so far (phases 2-3). `protocol.py`, `identity.py`
and `auth.py` are deliberately free of sockets and Qt so they can be unit-tested
headlessly; `transport.py`, `discovery.py` and `upnp.py` own sockets but no Qt,
and are tested over real loopback sockets.

Security invariants that apply to every module here (spec section 1.3):

1. JSON only for network data - never pickle/eval/exec/marshal.
2. No executable content is ever transferred (no .py/.pyc/.dll/.exe/... and no
   archives). Plugin *code* never crosses the wire; only enable/disable state.
3. Every network-derived path is validated: reject absolute paths and '..'
   components, join under the intended root, abspath, verify the root prefix,
   then check an extension allowlist. Write to staging, then atomically move.
4. Every authorisation decision is made host-side.
5. Every frame is length-prefixed with a hard cap; every message is
   schema-validated before any field is used.
6. Secrets are compared with hmac.compare_digest, never ==.
7. Non-LAN connections are TLS; only LAN discovery may be plaintext, and it
   carries no secret.
"""
