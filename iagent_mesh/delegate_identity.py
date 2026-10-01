"""A ``kind="delegate"`` `Initiator` from a client-credentials token — the SDK-side half of
``[[delegate-credential-gap-model-y]]``: no mint path existed for a delegate identity, so real
calls 401'd at the BFF gateway. Keycloak client-credentials per delegate is the mint (that's
ordinary OAuth2, out of scope here); this module is what turns the MINTED token into the
`Initiator` the rest of the SDK already knows how to admit or refuse.

WHY A SIBLING MODULE, NOT A FLAG ON `service_identity.mint_token`. That module's whole job stops
at "here is a token" — it never constructs an `Initiator` and never will, because a service
identity IS the bare token (`kind="service"` needs nothing further from the claims). A delegate
needs one more thing out of the SAME token before it is usable: WHO it acts for. Folding "then
decode it and build a delegate Initiator" into the mint function under a parameter would give one
function two return shapes depending on a flag — the exact divergence `service_identity.py`'s own
docstring records fixing once already, when two separately-maintained mints turned out to read
different env contracts under one name. Sibling function, not a parameter.

ON_BEHALF_OF STAYS PROVENANCE, NEVER A GATE INPUT, once the `Initiator` exists — see that field's
own docstring in `interfaces.py`. What THIS module refuses is a different question, asked at a
different time: whether a delegate `Initiator` can be MINTED AT ALL from a token whose
on-behalf-of claim never arrived. That is a minting / Keycloak protocol-mapper misconfiguration,
not an authorization decision, and it is refused HERE, once, before construction — nothing
downstream ever reads the claim's value to decide anything, and this module does not either; it
only checks the claim's PRESENCE.

WHY THIS IS A SEPARATE FAILURE FROM `Initiator`'s OWN VALIDATION. `Initiator` already raises
(pydantic `ValidationError`) if you hand it `kind="delegate"` with `on_behalf_of=None` — that
check has existed since the write half shipped and stays exactly as strict. What it cannot do is
say WHERE the empty value came from: a caller who mistyped a literal, or a token that never
carried the claim at all, land in the same `ValidationError` with no way to tell them apart. This
module's `DelegateCredentialRefused` is raised BEFORE `Initiator` is ever constructed, naming the
token as the source, so the fix a reader reaches for is "check the protocol mapper", not "read
pydantic's traceback".

DECODES WITHOUT VERIFYING THE SIGNATURE, ON PURPOSE. `transport_auth.verify_bearer` verifies a
signature because it is checking an INBOUND bearer token that arrived over the wire, from a
caller this process has no other reason to trust. This function's caller is different: it just
minted the token itself, via `service_identity.mint_token`, straight from Keycloak over TLS.
Re-verifying a signature against a token this process obtained one line earlier would be
checking its own homework; the only new information in the token, from this function's point of
view, is which claims Keycloak actually populated.
"""
from __future__ import annotations

import os
from typing import Optional

from .interfaces import Initiator

# No __all__, deliberately — same convention as service_identity.py, which this module is the
# sibling of: identity is an argument, so each caller imports this module directly
# (`from iagent_mesh.delegate_identity import delegate_initiator_from_token`) rather than finding
# a mint-adjacent name loose at the package root.


class DelegateCredentialRefused(RuntimeError):
    """A client-credentials token could not yield a delegate `Initiator`.

    Distinct from `service_identity.ServiceTokenError` (that names a MINT failure — Keycloak
    unreachable or a non-200) and from `Initiator`'s own `ValidationError` (that names a
    CONSTRUCTION failure against values already in hand). This is the third, narrower case in
    between: the token minted successfully and decodes, but does not carry what a delegate needs
    — the token existed; what it was told to carry did not.
    """


def _delegate_subject_claim() -> str:
    return os.getenv("DELEGATE_SUBJECT_CLAIM", "sub")


def _delegate_on_behalf_of_claim() -> str:
    return os.getenv("DELEGATE_ON_BEHALF_OF_CLAIM", "on_behalf_of")


def _claim_or_none(claims: dict, key: str) -> Optional[str]:
    value = claims.get(key)
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def delegate_initiator_from_token(
    token: str,
    *,
    subject_claim: Optional[str] = None,
    on_behalf_of_claim: Optional[str] = None,
) -> Initiator:
    """Build a `kind="delegate"` `Initiator` from a client-credentials access token.

    Refuses with `DelegateCredentialRefused`, naming which claim was the problem, when: the token
    cannot be decoded; the delegate's own subject claim is absent or blank; or the
    on-behalf-of claim is absent or blank. That last case is the one item 2 of the overnight
    order names directly — a delegate minted without an `on_behalf_of` claim must be refused
    HERE, not reach `Initiator(...)` and fail there as an unattributed `ValidationError`.

    ``subject_claim`` defaults to `DELEGATE_SUBJECT_CLAIM` (env, default ``"sub"``) — the
    standard JWT subject, which is what Keycloak populates for the client-credentials grant's own
    service-account identity. This is deliberately NOT `USER_ENTITLEMENT_CLAIM`: that claim names
    a HUMAN caller's identity for the read boundary's bearer-token path
    (`transport_auth._entitlement_claim`), a different population reached a different way, and
    reusing its name here would make one env var mean two unrelated things depending on which
    code path read it.

    ``on_behalf_of_claim`` defaults to `DELEGATE_ON_BEHALF_OF_CLAIM` (env, default
    ``"on_behalf_of"``) — configurable for the same reason: a deployment's Keycloak protocol
    mapper names its claims however it names them, and this module must not guess a literal that
    happens to match this SDK's own examples.
    """
    import jwt  # PyJWT

    try:
        # Not a live gap — closed by construction, permanently, not pending a fix: this token
        # was just minted by this SDK's own caller (client-credentials), never received off the
        # wire, so there is no third party's signature here to check. A WIRE token's signature is
        # `transport_auth.verify_bearer`'s job; this decodes a token this process just made.
        claims = jwt.decode(token, options={"verify_signature": False})
    except Exception as exc:  # noqa: BLE001
        raise DelegateCredentialRefused(
            f"delegate token undecodable: {type(exc).__name__}: {exc}"
        ) from exc

    subject_key = subject_claim or _delegate_subject_claim()
    behalf_key = on_behalf_of_claim or _delegate_on_behalf_of_claim()

    subject = _claim_or_none(claims, subject_key)
    if subject is None:
        raise DelegateCredentialRefused(
            f"delegate token carries no usable {subject_key!r} claim — refusing to mint a "
            f"delegate Initiator with no subject to admit or refuse at any boundary"
        )

    on_behalf_of = _claim_or_none(claims, behalf_key)
    if on_behalf_of is None:
        raise DelegateCredentialRefused(
            f"delegate token carries no usable {behalf_key!r} claim — refusing to mint a "
            f"delegate Initiator with nobody named accountable. This is the SDK-side gap named "
            f"in [[delegate-credential-gap-model-y]]: a delegate minted without this claim used "
            f"to reach Initiator construction and fail there as an unattributed ValidationError; "
            f"the fix is the token's own minting (a Keycloak protocol mapper), not this caller's"
        )

    try:
        return Initiator(subject=str(subject), kind="delegate", on_behalf_of=str(on_behalf_of))
    except ValueError as exc:  # pragma: no cover — the two checks above make this unreachable
        raise DelegateCredentialRefused(
            f"token claims failed Initiator validation despite passing this module's own "
            f"checks: {exc}"
        ) from exc
