"""Canonical operational blocker identifiers shared by training components."""

FD_ISOLATION_BLOCKER_CODE = "anonymous_unlinked_inherited_fd_runner"
FD_ISOLATION_BLOCKER_DETAIL = (
    "operazione MLX bloccata: isolamento post-validazione non FD-safe; "
    "serve un runner privato che consumi esclusivamente file descriptor read-only "
    "anonimi/unlinked ereditati"
)
SCIENTIFIC_EXECUTION_CLOSED_CODE = "scientific_download_baseline_execution_closed"
SCIENTIFIC_EXECUTION_CLOSED_DETAIL = (
    "esecuzione scientifica chiusa: download candidati, baseline e fine-tuning "
    "restano fail-closed anche dopo l'isolamento FD"
)
