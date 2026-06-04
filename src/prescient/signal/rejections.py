from __future__ import annotations

from prescient.signal.models import RejectionDetail, RejectionReason, RejectionStage


_REJECTION_MESSAGES: dict[RejectionReason, str] = {
    RejectionReason.THEME_NOT_CONFIGURED: "Target is not in a configured strategy theme.",
    RejectionReason.EARNINGS_DATE_UNCERTAIN: (
        "Target earnings date is missing or outside the allowed earnings window."
    ),
    RejectionReason.INSUFFICIENT_PEERS_REPORTED: (
        "Not enough same-theme peers have reported in the required window."
    ),
    RejectionReason.PEER_SIGNAL_TOO_WEAK: (
        "Reported peer signal does not meet the minimum ratio or average score thresholds."
    ),
    RejectionReason.CONFLICTING_NEWS: (
        "Target has conflicting major news that blocks deterministic strategy review."
    ),
    RejectionReason.TARGET_ALREADY_OVEREXTENDED: (
        "Target has already moved beyond the allowed pre-earnings run-up threshold."
    ),
    RejectionReason.TARGET_TOO_ILLIQUID: "Target does not meet liquidity requirements.",
    RejectionReason.OPTIONS_TOO_ILLIQUID: (
        "Options chain does not meet liquidity requirements."
    ),
    RejectionReason.MISSING_DATA: "Required structured data is missing and must not be guessed.",
    RejectionReason.TARGET_EVENT_INVALIDATES_PEER_COMPARISON: (
        "Target has an invalidating event that breaks peer comparison."
    ),
}


def build_rejection_details(
    reasons: list[RejectionReason],
    stage: RejectionStage,
) -> list[RejectionDetail]:
    seen: set[RejectionReason] = set()
    details: list[RejectionDetail] = []

    for reason in reasons:
        if reason in seen:
            continue
        seen.add(reason)
        details.append(
            RejectionDetail(
                reason=reason,
                stage=stage,
                message=_REJECTION_MESSAGES[reason],
            )
        )

    return details
